"""Query-construction regression tests.

Every test here encodes a failure found by running the retrieval layer against
the live indexes for the CodePath.org concept note (US, college computing
students), documented in `notes/incident-2026-08-01/`. The Colombian
youth-training note the layer was originally tuned on hid all of them, because
its controlled-vocabulary labels happen to be single words and its mechanism
prose happens to use standard development-economics wording.

The through-line: a query is only worth issuing if some paper could plausibly
match it. Terms lifted verbatim out of a schema label or a concept note's prose
cannot.
"""

from backend.evidence.queries import build_queries
from backend.evidence.query_terms import (
    MECHANISM_MAX_WORDS,
    extract_mechanism_phrases,
    split_label_terms,
    subject_groups,
)
from backend.schemas import Extraction, IntendedOutcomes, Population

# The real extraction from job d9f07573bcaf, trimmed to the fields queries.py
# reads. Kept verbatim so these tests fail the way production failed.
CODEPATH = Extraction(
    organization="CodePath.org",
    project_title=(
        "Reprogramming Higher Education to Create the Most Diverse Generation "
        "of AI-enabled Engineers"
    ),
    summary=(
        "CodePath delivers CS courses and career support to prepare Black, "
        "Latino/a, Indigenous, and low-income students for competitive jobs in "
        "the tech industry by redesigning curricula to include AI skills and "
        "deploying AI-powered student support bots."
    ),
    intervention_types=["training/coaching", "job placement"],
    mechanisms_to_affect_income=(
        "Redesigning technical curriculum to include AI-enabled developer "
        "workflows and providing AI-powered career support to increase "
        "placement rates into high-paying technical roles."
    ),
    country="United States",
    region="North America",
    population=Population(
        description=(
            "Black, Latino/a, Indigenous, low-income, and first-generation "
            "college computing students."
        )
    ),
    intended_outcomes=IntendedOutcomes(
        direct=[
            "technical internships",
            "full-time technical employment",
            "increased annual income",
            "CS degree completion",
        ]
    ),
)

# A note with no computing or higher-education content, to prove the subject
# family is triggered by the note rather than bolted on for every run.
CASH_TRANSFER = Extraction(
    organization="Example",
    summary="Unconditional cash transfers to rural households.",
    intervention_types=["cash transfer"],
    mechanisms_to_affect_income="Liquidity relieves credit constraints.",
    country="Kenya",
    population=Population(description="Rural smallholder households."),
)


# ── Bug A: controlled-vocabulary labels used verbatim as search terms ───────


def test_slashed_vocabulary_label_is_split_into_searchable_terms():
    """`training/coaching` is a schema label, not something a paper says.

    Issued verbatim it matched nothing, so the query collapsed to a search for
    the country name alone and returned 50 rows of US-history papers.
    """
    assert split_label_terms(["training/coaching"]) == ("training", "coaching")


def test_label_splitting_handles_the_other_separators_and_leaves_hyphens():
    assert split_label_terms(["cash transfer"]) == ("cash transfer",)
    assert split_label_terms(["mentoring & referrals"]) == ("mentoring", "referrals")
    assert split_label_terms(["savings, credit"]) == ("savings", "credit")
    # Hyphens are part of real economics vocabulary and must survive.
    assert split_label_terms(["difference-in-differences"]) == (
        "difference-in-differences",
    )


def test_no_emitted_query_contains_a_raw_vocabulary_separator():
    for query in build_queries(CODEPATH):
        assert "/" not in query.terms, f"unsplit label leaked into: {query.terms}"


def test_both_halves_of_a_split_label_reach_the_queries():
    corpus = " ".join(q.terms for q in build_queries(CODEPATH)).lower()
    assert "training" in corpus
    assert "coaching" in corpus


# ── Bug B: mechanism family quoted concept-note prose verbatim ──────────────


def test_mechanism_phrases_are_short_enough_to_match_a_real_paper():
    """The family selected the LONGEST content-word runs, which are exactly the
    phrases unique to this note. Live check: 0 rows, every time."""
    phrases = extract_mechanism_phrases(CODEPATH.mechanisms_to_affect_income)
    assert phrases, "mechanism family produced nothing to search on"
    for phrase in phrases:
        assert len(phrase.split()) <= MECHANISM_MAX_WORDS, (
            f"{phrase!r} is note-specific prose, not a searchable phrase"
        )


def test_mechanism_family_drops_the_verbatim_note_prose():
    phrases = extract_mechanism_phrases(CODEPATH.mechanisms_to_affect_income)
    assert "include AI-enabled developer workflows" not in phrases


def test_mechanism_family_keeps_the_short_searchable_phrase():
    """`placement rates` is the one phrase here a labour paper might carry, and
    it was being discarded for being short."""
    phrases = extract_mechanism_phrases(CODEPATH.mechanisms_to_affect_income)
    assert "placement rates" in phrases


# ── Bug C: the note's own subject was never searched for ───────────────────
#
# Measured against econlit on the CodePath extraction: 16 of 30 candidate
# formulations retrieved NBER w30227, and every one but a single outlier
# contained the token STEM. The best — subject AND education-level AND
# demographic AND country, full-text scoped — returned it at position 1.


def test_computing_note_gets_stem_vocabulary_it_never_states():
    """`STEM` appears nowhere in the extraction, yet it is the single term that
    most reliably retrieves this literature. It has to be inferred from the
    note's CS / engineering / computing wording."""
    names = dict(subject_groups(CODEPATH))
    assert "STEM" in " ".join(names.get("field", ()))


def test_demographic_descriptors_map_to_academic_search_terms():
    """The note says "Black, Latino/a, Indigenous, low-income". The literature
    says "underrepresented" and "minority". Searching the note's own wording
    finds nothing."""
    groups = dict(subject_groups(CODEPATH))
    assert "underrepresented" in groups.get("demographic", ())


def test_subject_family_reads_fields_the_builder_previously_ignored():
    """`population.description` and `intended_outcomes.direct` carry "college"
    and "degree completion" verbatim, and were never read."""
    groups = dict(subject_groups(CODEPATH))
    assert "college" in groups.get("education_level", ())


def test_subject_terms_reach_the_emitted_queries():
    corpus = " ".join(q.terms for q in build_queries(CODEPATH))
    assert "STEM" in corpus
    assert "underrepresented" in corpus
    assert "college" in corpus


def test_subject_family_is_silent_on_a_note_with_no_such_subject():
    assert subject_groups(CASH_TRANSFER) == ()
    corpus = " ".join(q.terms for q in build_queries(CASH_TRANSFER))
    assert "STEM" not in corpus
    assert "college" not in corpus


def test_cash_transfer_note_still_builds_usable_queries():
    queries = build_queries(CASH_TRANSFER)
    assert queries
    corpus = " ".join(q.terms for q in queries).lower()
    assert "cash transfer" in corpus


# ── Contracts the rewrite must not break (see notes/incident-2026-08-01) ────


def test_build_queries_is_deterministic_for_the_codepath_note():
    first = [(q.terms, q.scope, q.mode) for q in build_queries(CODEPATH)]
    second = [(q.terms, q.scope, q.mode) for q in build_queries(CODEPATH)]
    assert first == second


def test_codepath_note_still_gets_a_persistence_query():
    labels = [q.label.lower() for q in build_queries(CODEPATH)]
    assert any("persistence" in a or "long-run" in a for a in labels)
