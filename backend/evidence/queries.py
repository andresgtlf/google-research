"""Query construction for the evidence-retrieval layer.

The mission this file encodes: GitLab Foundation cares about the DISCOUNTED
STREAM of earnings over a working life, not a one-year bump. That means
"does the effect persist" is not a refinement of retrieval, it is retrieval
(see the persistence family below, which always runs).

Design principle: one broad full-text query is measurably bad. Against the
real index, `q="cash transfer" Kenya earnings` ranked "What's Behind Her
Smile? Health, Looks, and Self-Esteem" as the SECOND result — an off-topic
paper matched on loose keyword overlap. So this module never builds one
query; it builds a SET of narrow, mostly title-scoped queries and leaves
recall to the caller's union of results across queries and sources. Each
query buys precision; the union buys recall.

Every family below is a plain function that turns extracted fields into zero
or more `EvidenceQuery` objects. `build_queries` concatenates them in a fixed
priority order (mission-critical families first), deduplicates, and caps the
total so a run can never fan out into hundreds of HTTP calls. Vocabulary and
text-normalization helpers live in `query_terms.py`, split out to keep this
file focused on the six families themselves.
"""

import logging
from collections.abc import Sequence

from ..schemas import Extraction, Population
from .base import EvidenceQuery
from .query_terms import (
    CAUSAL_DESIGN_TERMS,
    INCOME_OUTCOME_TERMS,
    WOMEN_TERMS,
    YOUTH_TERMS,
    clean_terms,
    extract_mechanism_phrases,
    or_group,
    population_focus,
    quote,
    split_label_terms,
    subject_groups,
    year_start,
)

logger = logging.getLogger(__name__)

# Hard ceiling on emitted queries. Families 1-4 are mission-critical and are
# built first, so trimming (a plain slice) drops family 5/6 entries first.
MAX_QUERIES = 12

# Regional expansion is a scarcity fallback, not a primary family, so it is
# capped hard: at most this many pre-declared contexts get their own queries.
REGIONAL_EXPANSION_MAX_CONTEXTS = 2


# ── Query families ──────────────────────────────────────────────────────────


def _family_intervention_country(
    interventions: Sequence[str], country: str, covered_venues: Sequence[str]
) -> list[EvidenceQuery]:
    """1. Intervention x country, title-scoped — the precision family.

    Title-scoped so a study must actually be ABOUT this intervention in this
    country, not merely mention both terms somewhere in a long abstract. When
    the caller knows which venues are actually covered, restricting to them
    trims exactly the kind of off-topic noise a broad query lets through
    (see the module docstring's self-esteem-paper example).
    """
    country_term = _clean_country(country)
    terms = split_label_terms(interventions)
    if not country_term or not terms:
        return []

    venues = tuple(covered_venues)
    return [
        EvidenceQuery(
            terms=f"{quote(term)} {quote(country_term)}",
            scope="title",
            mode="exact",
            year_start=year_start(),
            venues=venues,
            label=(
                f"'{term}' in {country_term}, title-scoped — precision match "
                "to avoid the off-topic overlap a broad full-text search lets "
                "through"
            ),
        )
        for term in terms
    ]


def _clean_country(country: str) -> str:
    cleaned = clean_terms([country])
    return cleaned[0] if cleaned else ""


def _family_income_outcome(
    interventions: Sequence[str], country: str
) -> list[EvidenceQuery]:
    """2. Intervention x income outcome — the core mission query.

    Evidence must measure income (earnings/wages/profits/revenue), not an
    adjacent outcome retrieved on topic overlap alone, so this family always
    ANDs the intervention against the income-outcome vocabulary explicitly.
    It also biases toward causal designs (mirroring research_prompt.py
    Section B's "Core query" pattern), because this is the one family
    broad enough in scope that it needs that bias to stay precise.
    """
    terms = split_label_terms(interventions)
    if not terms:
        return []

    country_term = _clean_country(country)
    country_bit = f" {quote(country_term)}" if country_term else ""
    causal_bit = or_group(CAUSAL_DESIGN_TERMS)
    return [
        EvidenceQuery(
            terms=(
                f"{or_group(terms)} {or_group(INCOME_OUTCOME_TERMS)} "
                f"{causal_bit}{country_bit}"
            ),
            scope="all",
            mode="stemmed",
            year_start=year_start(),
            label=(
                "intervention x income outcome — core mission query: does "
                "this evidence actually measure earnings, not an adjacent "
                "outcome like enrollment or empowerment"
            ),
        )
    ]


def _family_mechanism(mechanism_text: str) -> list[EvidenceQuery]:
    """3. Mechanism — tests the note's claimed causal pathway.

    Two "training" programs can work through skill acquisition or through
    job-matching, with different evidence bases; this family searches on the
    pathway itself, not just the intervention label.
    """
    phrases = extract_mechanism_phrases(mechanism_text)
    if not phrases:
        return []

    return [
        EvidenceQuery(
            terms=or_group(phrases),
            scope="all",
            mode="stemmed",
            year_start=year_start(),
            label=(
                "mechanism — tests the note's claimed causal pathway rather "
                "than just the intervention label"
            ),
        )
    ]


# A trimmed subset of LONG_RUN_SIGNALS for use in QUERY STRINGS.
#
# LONG_RUN_SIGNALS has ~15 entries, which is right for scoring already-retrieved
# text (cheap, and recall is free) but wrong for a query: OR-ing all of them
# produced a 200-character term blob that OpenAlex answered with HTTP 429 on
# every live run. The lifetime-earnings query was therefore the one query
# reliably failing — precisely the one that must not. These four cover the same
# literature, since a paper measuring persistence almost always says at least one
# of them, and papers are also reached by the other query families.
PERSISTENCE_QUERY_TERMS: tuple[str, ...] = (
    "long-term",
    "long-run",
    "follow-up",
    "persistence",
)


def _family_persistence(interventions: Sequence[str]) -> list[EvidenceQuery]:
    """4. Persistence / long-run — the lifetime-earnings query.

    Always emitted, with or without an intervention to cross it against,
    because "does the effect last" is the mission, not a refinement of it. A
    program showing +20% at year 1 that fades to zero by year 3 is nearly
    worthless for lifetime earnings; this family is what finds out.
    """
    terms = split_label_terms(interventions)
    long_run = or_group(PERSISTENCE_QUERY_TERMS)
    query_terms = f"{or_group(terms)} {long_run}".strip() if terms else long_run

    return [
        EvidenceQuery(
            terms=query_terms,
            scope="all",
            mode="stemmed",
            year_start=year_start(),
            label=(
                "persistence / long-run — the lifetime-earnings query: a "
                "one-year bump is nearly worthless for this mission, so this "
                "family always runs"
            ),
        )
    ]


def _family_subject(extraction: Extraction) -> list[EvidenceQuery]:
    """5. Subject — what the note is ABOUT, in the literature's vocabulary.

    The other families all search on the intervention label, so two notes with
    the same label search identically no matter who they serve or what field
    they operate in. This family is the only one that asks about the subject
    itself, and it was the missing piece behind the CodePath miss: nothing in
    that run's retrieval mentioned STEM, college, degree or underrepresented.

    Two shapes, both measured against econlit (see `query_terms.py`'s
    `SUBJECT_VOCABULARY` note). The first — subject groups AND-ed with the
    country, full-text scoped — put the target paper at position 1. The second
    crosses the subject with the income vocabulary, so the family still
    anchors on the mission when a note names no country.

    Full-text scope, not title scope: title-scoped variants of these queries
    collapsed to the same 28-row set regardless of the terms added, ranking the
    target at 16 rather than 1.
    """
    groups = subject_groups(extraction)
    if not groups:
        return []

    subject_bits = " ".join(or_group(terms) for _name, terms in groups)
    country_term = _clean_country(extraction.country)
    queries: list[EvidenceQuery] = []

    if country_term:
        queries.append(
            EvidenceQuery(
                terms=f"{subject_bits} {quote(country_term)}",
                scope="all",
                mode="stemmed",
                year_start=year_start(),
                label=(
                    "subject x country — what the note is about, translated "
                    "into the vocabulary the literature actually uses"
                ),
            )
        )

    queries.append(
        EvidenceQuery(
            terms=f"{subject_bits} {or_group(INCOME_OUTCOME_TERMS)}",
            scope="all",
            mode="stemmed",
            year_start=year_start(),
            label=(
                "subject x income outcome — keeps the subject search anchored "
                "on earnings rather than on education outcomes alone"
            ),
        )
    )
    return queries


def _family_regional_expansion(
    interventions: Sequence[str], regional_contexts: Sequence[str]
) -> list[EvidenceQuery]:
    """5. Regional expansion — scarcity fallback only.

    Only built when the note pre-declares expansion contexts, and only for
    the first `REGIONAL_EXPANSION_MAX_CONTEXTS` of them, since this family
    exists to fill gaps rather than to run by default.
    """
    terms = split_label_terms(interventions)
    regions = clean_terms(regional_contexts)[:REGIONAL_EXPANSION_MAX_CONTEXTS]
    if not terms or not regions:
        return []

    return [
        EvidenceQuery(
            terms=f"{quote(term)} {quote(region)}",
            scope="title",
            mode="exact",
            year_start=year_start(),
            label=(
                f"regional expansion — '{term}' in {region}, used only as a "
                "scarcity fallback when in-country evidence is thin"
            ),
        )
        for region in regions
        for term in terms
    ]


def _family_population(
    interventions: Sequence[str], population: Population
) -> list[EvidenceQuery]:
    """6. Population-specific — pre-specified heterogeneity cuts.

    Built only when the note itself signals a youth or women focus, because
    the Foundation's heterogeneity cuts are pre-specified, not fished for.
    """
    terms = split_label_terms(interventions)
    if not terms:
        return []

    youth_focused, women_focused = population_focus(population)
    queries: list[EvidenceQuery] = []
    if youth_focused:
        queries.append(
            EvidenceQuery(
                terms=f"{or_group(terms)} {or_group(YOUTH_TERMS)}",
                scope="all",
                mode="stemmed",
                year_start=year_start(),
                label=(
                    "population: youth — pre-specified heterogeneity cut "
                    "flagged by the note's stated population"
                ),
            )
        )
    if women_focused:
        queries.append(
            EvidenceQuery(
                terms=f"{or_group(terms)} {or_group(WOMEN_TERMS)}",
                scope="all",
                mode="stemmed",
                year_start=year_start(),
                label=(
                    "population: women — pre-specified heterogeneity cut "
                    "flagged by the note's stated population"
                ),
            )
        )
    return queries


# ── Public entry point ──────────────────────────────────────────────────────


def _dedupe(queries: Sequence[EvidenceQuery]) -> list[EvidenceQuery]:
    """Drop queries identical on (terms, scope, mode), preserving order."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[EvidenceQuery] = []
    for query in queries:
        key = (query.terms, query.scope, query.mode)
        if key in seen:
            continue
        seen.add(key)
        unique.append(query)
    return unique


def build_queries(
    extraction: Extraction,
    covered_venues: Sequence[str] = (),
    uncovered_venues: Sequence[str] = (),
) -> list[EvidenceQuery]:
    """Build the full set of narrow queries for one concept note.

    Never raises and never returns an empty list: the persistence family
    (4) always produces at least one query, with or without an intervention
    to cross it against. Families are concatenated in priority order
    (1-4 before 5-6) so capping at `MAX_QUERIES` trims the scarcity-fallback
    and heterogeneity-cut families first.
    """
    if uncovered_venues:
        logger.debug(
            "evidence retrieval has no source covering %d venue(s): %s",
            len(uncovered_venues),
            ", ".join(uncovered_venues),
        )

    families: list[list[EvidenceQuery]] = [
        _family_intervention_country(
            extraction.intervention_types, extraction.country, covered_venues
        ),
        _family_income_outcome(extraction.intervention_types, extraction.country),
        _family_mechanism(extraction.mechanisms_to_affect_income),
        _family_persistence(extraction.intervention_types),
        _family_subject(extraction),
        _family_regional_expansion(
            extraction.intervention_types, extraction.regional_expansion_contexts
        ),
        _family_population(extraction.intervention_types, extraction.population),
    ]
    if extraction.source_format == "next_ladder_intake":
        # Put channel searches first so generic income families cannot crowd them out.
        subject = " ".join([extraction.summary, extraction.mechanisms_to_affect_income,
                            " ".join(extraction.intake.financial_impact_channels)]).lower()
        channels = [("benefit", "benefits enrollment financial impact"),
                    ("debt", "debt relief financial distress causal impact"),
                    ("bankruptcy", "bankruptcy access financial outcomes"),
                    ("legal", "legal assistance costs randomized"),
                    ("cost", "cost savings household financial wellbeing")]
        intake_queries = [EvidenceQuery(terms=terms, country=extraction.country,
                          rationale="Next Ladder intake financial-impact channel")
                          for keyword, terms in channels if keyword in subject]
        families.insert(0, intake_queries)
    ordered = [query for family in families for query in family]
    return _dedupe(ordered)[:MAX_QUERIES]
