"""Score and rank retrieved candidates against the lifetime-earnings mission.

Retrieval finds candidates; this module decides which of them are worth a
reviewer's or the research agent's attention. Two mission facts drive the
weights below:

- Measured income effects are the primary evidence unit. A candidate that
  demonstrably measures no income outcome is presumptively off-mission.
- Lifetime earnings is an APPROXIMATION layered on those measured effects, not
  a competing evidence standard. Persistence evidence therefore earns a real
  bonus but stays SUBORDINATE to direct relevance: most credible RCTs in this
  literature carry only 1-2 year horizons, and weighting long-run on par with
  income would let a long-run study of a different intervention outrank a
  directly on-point two-year RCT. Rigor, not rigidity.

Two guards exist because live runs found both failure modes. Neither is
optional, and both are pinned by tests:

- The off-mission penalty applies only where there is enough abstract text to
  judge (`_has_judgeable_text`). econlit populates `abstract` for ~7% of rows,
  so penalizing "no income word found" would rank on metadata completeness
  rather than relevance and demote exactly the on-point titles that enrichment
  is about to fill in. Missing is UNKNOWN, not ABSENT.
- A topical relevance gate (`_matches_topic`) demotes candidates with no
  connection to the intervention or country. Income and follow-up wording is
  generic enough on its own that unrelated papers cleared every other check.
"""

import logging
import math
import re
from collections.abc import Iterable
from dataclasses import replace

from ..schemas import Extraction
from .base import Candidate, INCOME_OUTCOME_SIGNALS, LONG_RUN_SIGNALS
from .query_terms import subject_groups

logger = logging.getLogger(__name__)

# ── Vocabulary ───────────────────────────────────────────────────────────

# Distinct from queries.CAUSAL_DESIGN_TERMS (which is phrased for building
# search-engine query strings): this is the literal set of design words this
# module looks for in already-retrieved title/abstract text.
CAUSAL_DESIGN_SIGNALS: tuple[str, ...] = (
    "randomized",
    "RCT",
    "experiment",
    "regression discontinuity",
    "difference-in-differences",
    "instrumental variable",
)

# Statuses that mean "no replication package", used to keep a blank or
# explicitly-negative status from scoring as if a package existed.
_NO_REPLICATION_STATUSES: frozenset[str] = frozenset(
    {"", "none", "n/a", "na", "not available", "unavailable", "no"}
)

# ── Weights (named, tunable, reviewable) ────────────────────────────────

# Income outcomes are the primary evidence unit, so this is the largest
# positive weight.
WEIGHT_INCOME_OUTCOME = 3.0

# Applied ONLY when there is enough text to actually judge the outcome — see
# `_has_judgeable_text`. econlit returns an empty abstract for ~93% of rows, so
# scoring "no income signal found" as off-mission would penalize a study for
# the *index's* incompleteness rather than for its own content, and would
# demote exactly the on-point titles enrichment is about to fill in. A
# demotion, not an annihilation: a genuinely off-mission paper should sink
# below on-mission ones without being made unrankable.
WEIGHT_NO_INCOME_PENALTY = -2.0

# Deliberately SUBORDINATE to the income weight, not equal to it.
#
# Lifetime earnings is an approximation built on top of measured income
# effects, not a separate evidence standard. Persistence evidence is a bonus
# dimension — valuable, and reported explicitly as persist/decay/grow — but it
# must never outrank direct relevance. Most credible RCTs in this literature
# only carry 1-2 year horizons; weighting long-run on par with income would let
# a long-run study of a *different* intervention outrank a directly on-point
# two-year RCT, starving the evidence base of its most relevant studies to
# satisfy a horizon preference. Rigor, not rigidity.
WEIGHT_LONG_RUN = 1.5

WEIGHT_CAUSAL_DESIGN = 1.5

# Sized to sink an off-topic paper below on-topic ones even when it carries a
# strong citation count, without making it unrankable — the agent may still have
# reason to look at it, and it stays visible with the reason stated.
WEIGHT_OFF_TOPIC_PENALTY = -4.0

WEIGHT_COUNTRY_MATCH = 1.0
WEIGHT_REGION_MATCH = 0.5

# An unstated country is UNKNOWN, not a mismatch — the same rule that governs a
# missing abstract, and the same midpoint reasoning as `_NO_PEER_RELEVANCE`.
#
# Domestic studies rarely name their own country: NBER w30227 is a US randomized
# trial whose abstract says "Black and Hispanic workers", "elite colleges" and
# "STEM fields" and never once says "United States". Awarding the country bonus
# only on an explicit mention therefore penalised exactly the domestic evidence
# a US concept note most needs, while rewarding comparative and international
# papers for naming a country in passing. Half credit keeps a genuine match
# ahead of an unknown one without treating silence as disqualifying.
WEIGHT_COUNTRY_UNSTATED = 0.5

# The strongest free credibility signal available (openICPSR etc.).
WEIGHT_REPLICATION = 1.0

# Dampened via log1p so raw citation count — which structurally favors old
# papers over the recent long-run follow-ups this mission needs — cannot
# dominate the score. See `_citation_score`.
WEIGHT_CITATIONS = 0.35

WEIGHT_FULL_TEXT = 0.3
WEIGHT_SOURCE_AGREEMENT = 0.3

# The source's own match-quality signal, rank-normalized (see
# `_normalize_relevance`) rather than used raw.
WEIGHT_RELEVANCE = 1.0

DEFAULT_LIMIT = 25

# Candidate with no peer in its source group to rank against: neither a
# strong nor a weak signal, so it gets the midpoint rather than an edge value.
_NO_PEER_RELEVANCE = 0.5


def _text_blob(candidate: Candidate) -> str:
    return f"{candidate.title} {candidate.abstract}".lower()


def _any_signal(text: str, signals: Iterable[str]) -> bool:
    return any(signal.lower() in text for signal in signals)


# A title alone is roughly 10-15 words and routinely omits the outcome measured
# ("Subsidizing Vocational Training for Disadvantaged Youth in Colombia" says
# nothing about earnings, yet it is squarely on-mission). Below this much text
# we treat a missing income signal as unknown rather than as absent.
_MIN_JUDGEABLE_CHARS = 200


def _has_judgeable_text(candidate: Candidate) -> bool:
    """True when there is enough text to conclude an outcome is really absent.

    Guards the off-mission penalty against the dominant failure mode of the
    corpus: econlit populates `abstract` for only ~7% of rows, so most
    candidates arrive as title-only. Penalizing those would rank on metadata
    completeness instead of on relevance.
    """
    return len(candidate.abstract.strip()) >= _MIN_JUDGEABLE_CHARS


def _matched_signal(text: str, signals: Iterable[str]) -> str:
    """First matching signal, for a human-readable score note."""
    for signal in signals:
        if signal.lower() in text:
            return signal
    return ""


def _citation_score(citations: int | None) -> float:
    """Log-dampened, `None`-safe citation contribution."""
    if citations is None or citations <= 0:
        return 0.0
    return math.log1p(citations)


_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "with", "that", "this", "from", "into", "their",
        "through", "other", "such", "which", "them", "then", "than", "ают",
        "support", "services", "program", "programs", "programme", "project",
        "increase", "increases", "increasing", "improve", "improves",
        "improving", "better", "access", "based", "using", "more", "most",
        "people", "households", "beneficiaries", "participants",
    }
)

# Short tokens carry no topical information ("job" is fine, "of" is not) and
# matching them would defeat the gate.
_MIN_TOPIC_TOKEN_CHARS = 4


# Country names as they appear in this literature, with the demonyms and
# abbreviations a paper is at least as likely to use. Used for two questions
# that must be answered separately: "does this candidate name the TARGET
# country" and "does it name SOME OTHER country" — because the answer "neither"
# is the common case for domestic work and must not be scored as a mismatch.
#
# Not exhaustive, and does not need to be: an unlisted country simply leaves a
# candidate in the "no country stated" bucket, which is the neutral outcome.
COUNTRY_VOCABULARY: dict[str, tuple[str, ...]] = {
    "united states": ("united states", "u.s.", "u.s.a.", "usa", "american", "americans"),
    "united kingdom": (
        "united kingdom", "u.k.", "britain", "british", "england", "scotland", "wales",
    ),
    "canada": ("canada", "canadian"),
    "australia": ("australia", "australian"),
    "india": ("india", "indian"),
    "kenya": ("kenya", "kenyan"),
    "uganda": ("uganda", "ugandan"),
    "tanzania": ("tanzania", "tanzanian"),
    "ethiopia": ("ethiopia", "ethiopian"),
    "ghana": ("ghana", "ghanaian"),
    "nigeria": ("nigeria", "nigerian"),
    "south africa": ("south africa", "south african"),
    "rwanda": ("rwanda", "rwandan"),
    "malawi": ("malawi", "malawian"),
    "zambia": ("zambia", "zambian"),
    "colombia": ("colombia", "colombian"),
    "mexico": ("mexico", "mexican"),
    "brazil": ("brazil", "brazilian"),
    "peru": ("peru", "peruvian"),
    "chile": ("chile", "chilean"),
    "argentina": ("argentina", "argentine", "argentinian"),
    "bangladesh": ("bangladesh", "bangladeshi"),
    "pakistan": ("pakistan", "pakistani"),
    "indonesia": ("indonesia", "indonesian"),
    "philippines": ("philippines", "filipino"),
    "vietnam": ("vietnam", "vietnamese"),
    "china": ("china", "chinese"),
    "japan": ("japan", "japanese"),
    "germany": ("germany", "german"),
    "france": ("france", "french"),
    "spain": ("spain", "spanish"),
    "italy": ("italy", "italian"),
    "netherlands": ("netherlands", "dutch"),
    "sweden": ("sweden", "swedish"),
    "norway": ("norway", "norwegian"),
    "denmark": ("denmark", "danish"),
    "turkey": ("turkey", "turkish"),
    "jordan": ("jordan", "jordanian"),
    "morocco": ("morocco", "moroccan"),
}


def _mentions(text: str, terms: Iterable[str]) -> bool:
    """Whole-word containment test.

    Plain substring matching is unsafe for the short terms used here: "uk"
    matches "Ukraine", "stem" matches "system" and "ecosystem". Lookarounds
    rather than `\\b` because several terms end in a period ("u.s.").
    """
    lowered = text.lower()
    for term in terms:
        if re.search(rf"(?<!\w){re.escape(term.lower())}(?!\w)", lowered):
            return True
    return False


def _country_aliases(country: str) -> tuple[str, ...]:
    key = country.strip().lower()
    return COUNTRY_VOCABULARY.get(key, (key,) if key else ())


def _country_state(candidate: Candidate, extraction: Extraction) -> str:
    """One of "match", "other", or "unstated"."""
    text = _text_blob(candidate)
    target = extraction.country.strip().lower()
    if not target:
        return "unstated"
    if _mentions(text, _country_aliases(target)):
        return "match"
    for name, aliases in COUNTRY_VOCABULARY.items():
        if name != target and _mentions(text, aliases):
            return "other"
    return "unstated"


def _subject_terms(extraction: Extraction) -> tuple[str, ...]:
    """The note's subject in the literature's vocabulary (see query_terms)."""
    return tuple(term for _name, group in subject_groups(extraction) for term in group)


def _matches_subject(candidate: Candidate, extraction: Extraction) -> bool:
    """Whether the candidate is about the same SUBJECT as the note.

    `_topic_tokens` deliberately excludes the project title and intended
    outcomes because their raw words ("urban", "youth", "skills") matched
    almost everything. The curated subject vocabulary does not have that
    problem — "underrepresented", "STEM" and "degree completion" are specific
    — so it is safe to gate on here, and it is what lets an on-point study that
    shares no INTERVENTION word with the note still clear the gate.
    """
    terms = _subject_terms(extraction)
    if not terms:
        return False
    if _mentions(candidate.title, terms):
        return True
    hits = sum(1 for term in terms if _mentions(candidate.abstract, [term]))
    return hits >= _MIN_ABSTRACT_TOPIC_HITS


def _topic_tokens(extraction: Extraction) -> frozenset[str]:
    """Content words describing WHAT this project does, for the topic gate.

    Drawn from the intervention types and the claimed mechanism only. The
    project title and intended outcomes were tried here first and made the gate
    useless: they contribute generic words ("urban", "youth", "skills") that
    appear in a huge share of social-science abstracts, so almost everything
    matched.
    """
    parts: list[str] = list(extraction.intervention_types)
    parts.append(extraction.mechanisms_to_affect_income)
    blob = " ".join(p for p in parts if p).lower()
    tokens = re.findall(r"[a-záéíóúñü]+", blob)
    return frozenset(
        t
        for t in tokens
        if len(t) >= _MIN_TOPIC_TOKEN_CHARS and t not in _STOPWORDS
    )


# A title is short and almost entirely topical, so one hit there is meaningful.
# An abstract is long enough that a single incidental hit proves nothing, so it
# takes two distinct topic words to clear the gate.
_MIN_ABSTRACT_TOPIC_HITS = 2


def _matches_topic(candidate: Candidate, extraction: Extraction) -> bool:
    """True when the candidate is plausibly about this project's subject.

    Deliberately still permissive — the gate exists to drop candidates with no
    topical connection at all, not to second-guess relevance, which is the
    research agent's job once it has read the paper. Live runs showed the cost of
    being too permissive: a BMC Psychiatry study of an online resilience program
    and a Lancet violence-prevalence estimate both reached the top eight for a
    youth-training concept note, on generic income and follow-up wording plus one
    incidental keyword.

    A country match used to satisfy this gate on its own. It cannot: a country
    is not a topic. For a US concept note that rule admitted every US paper in
    the index, which is how an acid-rain mortality study and three
    consumption-inequality papers reached the top of the CodePath candidate
    list while a directly on-point STEM-education RCT fell outside the cap.
    """
    title = candidate.title.lower()
    abstract = candidate.abstract.lower()

    if _matches_subject(candidate, extraction):
        return True

    tokens = _topic_tokens(extraction)
    if not tokens:
        # Nothing to match against; do not penalize on absent input.
        return True
    if any(token in title for token in tokens):
        return True
    hits = sum(1 for token in tokens if token in abstract)
    return hits >= _MIN_ABSTRACT_TOPIC_HITS


def _has_replication_package(candidate: Candidate) -> bool:
    if candidate.replication_url:
        return True
    return candidate.replication_status.strip().lower() not in _NO_REPLICATION_STATUSES


def _normalize_relevance(candidates: list[Candidate]) -> list[float]:
    """Rank-normalize `relevance` within each candidate's source group.

    Different sources score relevance on different scales — econlit returns
    roughly 0-100, OpenAlex returns nothing at all (always 0.0) — so
    comparing raw values across sources would let whichever source happens
    to use a bigger scale dominate the ranking. Ranking within each distinct
    `sources` tuple instead turns "where does this candidate sit relative to
    its own source's other results" into a comparable 0-1 value, regardless
    of what scale (or lack of one) the source used.
    """
    groups: dict[tuple[str, ...], list[int]] = {}
    for index, candidate in enumerate(candidates):
        groups.setdefault(candidate.sources, []).append(index)

    normalized = [_NO_PEER_RELEVANCE] * len(candidates)
    for indices in groups.values():
        if len(indices) == 1:
            continue
        ordered = sorted(indices, key=lambda i: candidates[i].relevance)
        span = len(ordered) - 1
        # Equal source scores receive their shared midrank. Arbitrarily
        # breaking ties here made OpenAlex's all-zero scores depend on order.
        start = 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and candidates[ordered[end]].relevance == candidates[ordered[start]].relevance:
                end += 1
            midrank = (start + end - 1) / (2 * span)
            for index in ordered[start:end]:
                normalized[index] = midrank
            start = end
    return normalized


def _score_one(
    candidate: Candidate, extraction: Extraction, relevance_rank: float
) -> tuple[float, tuple[str, ...]]:
    text = _text_blob(candidate)
    score = 0.0
    notes: list[str] = []

    if _any_signal(text, INCOME_OUTCOME_SIGNALS):
        matched = _matched_signal(text, INCOME_OUTCOME_SIGNALS)
        score += WEIGHT_INCOME_OUTCOME
        notes.append(f"measures an income outcome ({matched})")
    elif _has_judgeable_text(candidate):
        score += WEIGHT_NO_INCOME_PENALTY
        notes.append("no income outcome in the abstract — likely off-mission")
    else:
        # Unknown, not absent. Say so, so a reviewer reads this as a gap in the
        # metadata rather than as a judgment about the study.
        notes.append("outcome unknown — no abstract available to screen")

    if _any_signal(text, LONG_RUN_SIGNALS):
        score += WEIGHT_LONG_RUN
        notes.append("measures long-run persistence or a follow-up horizon")

    if _any_signal(text, CAUSAL_DESIGN_SIGNALS):
        score += WEIGHT_CAUSAL_DESIGN
        notes.append("uses a causal research design")

    # Topical relevance gate. Income + long-run + causal-design wording is
    # generic enough that papers on entirely unrelated subjects clear it: a live
    # run on a Colombian youth-training note surfaced a BMC Psychiatry study of
    # an online resilience program at 8.43, plus two consumer-credit papers,
    # purely on "income"/"consumption" plus follow-up language. Nothing in the
    # score asked whether the paper was about the intervention at all. A
    # candidate that matches no intervention term, no mechanism term, and not
    # the country is off-topic no matter how well it scores elsewhere.
    if not _matches_topic(candidate, extraction):
        score += WEIGHT_OFF_TOPIC_PENALTY
        notes.append("no intervention, mechanism, or country term matched — likely off-topic")

    regions = [r.strip().lower() for r in extraction.regional_expansion_contexts if r]
    country_state = _country_state(candidate, extraction)
    if country_state == "match":
        score += WEIGHT_COUNTRY_MATCH
        notes.append(f"matches the target country ({extraction.country})")
    elif any(region and region in text for region in regions):
        score += WEIGHT_REGION_MATCH
        notes.append("matches a pre-declared regional expansion context")
    elif country_state == "unstated":
        score += WEIGHT_COUNTRY_UNSTATED
        notes.append(
            "no country stated — treated as unknown, not as a mismatch "
            "(domestic studies rarely name their own country)"
        )
    else:
        notes.append("studies a country other than the target")

    if _has_replication_package(candidate):
        score += WEIGHT_REPLICATION
        notes.append("has a replication package")

    citation_contribution = WEIGHT_CITATIONS * _citation_score(candidate.citations)
    if citation_contribution > 0:
        score += citation_contribution
        notes.append(f"{candidate.citations} citations (log-scaled)")

    if candidate.has_recoverable_full_text:
        score += WEIGHT_FULL_TEXT
        notes.append("full text is recoverable")

    if len(candidate.sources) > 1:
        score += WEIGHT_SOURCE_AGREEMENT
        notes.append(f"corroborated across {len(candidate.sources)} sources")

    score += WEIGHT_RELEVANCE * relevance_rank

    return score, tuple(notes)


def rank(
    candidates: Iterable[Candidate], extraction: Extraction, limit: int = DEFAULT_LIMIT
) -> list[Candidate]:
    """Score every candidate and return the top `limit`, best first.

    Never raises: a candidate with unusual field values (missing citations,
    empty text) simply scores lower rather than breaking the run.
    """
    materialized = list(candidates)
    if not materialized:
        return []

    relevance_ranks = _normalize_relevance(materialized)

    scored: list[Candidate] = []
    for candidate, relevance_rank in zip(materialized, relevance_ranks):
        score, notes = _score_one(candidate, extraction, relevance_rank)
        scored.append(replace(candidate, score=score, score_notes=notes))

    scored.sort(key=lambda c: (-c.score, c.doi.casefold(), c.title.casefold(), c.year or 0))
    logger.debug("ranked %d candidates, returning top %d", len(scored), limit)
    return scored[:limit]
