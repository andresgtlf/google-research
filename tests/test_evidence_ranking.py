"""Unit tests for the paper-retrieval query/dedupe/ranking layer.

Pure unit tests: no network, no mocking, no fixtures beyond plain Python
objects. `build_queries` and `rank` never touch a real index; `Candidate`
and `Extraction` are constructed by hand.
"""

from backend.evidence.base import Candidate
from backend.evidence.dedupe import merge_candidates
from backend.evidence.queries import MAX_QUERIES, build_queries
from backend.evidence.ranking import rank
from backend.schemas import Extraction, Population

# ── build_queries ────────────────────────────────────────────────────────

# A plausible Colombian youth-training concept note: enough intervention
# types, a pre-declared regional expansion set, and a youth/women-skewed
# population to push the family count past MAX_QUERIES and exercise the
# cap/trim logic, not just the happy path.
COLOMBIA_YOUTH_TRAINING = Extraction(
    organization="Fundación Impulso",
    project_title="Vocational Training and Job Matching for Urban Youth",
    intervention_types=[
        "training/coaching",
        "job placement",
        "entrepreneurship support",
    ],
    mechanisms_to_affect_income=(
        "Training increases occupational skills and connects graduates to "
        "formal-sector employers through job-matching services, improving "
        "wages via better job matches."
    ),
    country="Colombia",
    population=Population(
        description="Young adults aged 18-24 from low-income urban households",
        youth_pct=85.0,
        women_pct=55.0,
    ),
    regional_expansion_contexts=[
        "Andean region (Peru/Ecuador/Bolivia)",
        "broader Latin America",
    ],
)


def _query_keys(queries):
    return [(q.terms, q.scope, q.mode) for q in queries]


def test_build_queries_always_includes_the_persistence_family():
    """A one-year bump is nearly worthless for a lifetime-earnings mission,
    so the persistence/long-run family must survive even aggressive
    trimming elsewhere."""
    queries = build_queries(COLOMBIA_YOUTH_TRAINING)
    assert any(
        "persistence" in q.label.lower() or "long-run" in q.label.lower()
        for q in queries
    )


def test_build_queries_respects_the_cap():
    queries = build_queries(COLOMBIA_YOUTH_TRAINING)
    assert len(queries) <= MAX_QUERIES
    # This note's combinations (3 interventions x country, x 2 regions, x 2
    # population cuts, plus mechanism/persistence/income-outcome) exceed the
    # cap, so this assertion is actually exercising the trim path, not just
    # trivially passing under the limit.
    assert len(queries) == MAX_QUERIES


def test_build_queries_has_no_duplicate_queries():
    queries = build_queries(COLOMBIA_YOUTH_TRAINING)
    keys = _query_keys(queries)
    assert len(keys) == len(set(keys))


def test_build_queries_on_empty_extraction_does_not_crash():
    queries = build_queries(Extraction())
    assert isinstance(queries, list)
    # The persistence family alone guarantees this is never empty, even
    # with no intervention/country/mechanism to work with.
    assert len(queries) >= 1


def test_build_queries_on_empty_extraction_has_no_duplicates():
    queries = build_queries(Extraction())
    keys = _query_keys(queries)
    assert len(keys) == len(set(keys))


# ── merge_candidates ─────────────────────────────────────────────────────


def test_merge_candidates_folds_a_journal_and_its_nber_twin():
    journal = Candidate(
        title="Cash Transfers and Youth Earnings in Colombia",
        authors=("Garcia, M.", "Lopez, R."),
        year=2020,
        venue="American Economic Review",
        doi="10.1257/aer.20180001",
        abstract="",
    )
    nber_twin = Candidate(
        title="Cash Transfers and Youth Earnings in Colombia",
        authors=("Garcia, M.", "Lopez, R."),
        year=2018,
        venue="NBER Working Paper Series",
        doi="10.3386/w24999",
        abstract="This paper studies the effect of cash transfers on earnings.",
    )

    merged = merge_candidates([journal, nber_twin])

    assert len(merged) == 1
    result = merged[0]
    # The peer-reviewed version of record wins the primary doi/venue slot.
    assert result.doi == journal.doi
    assert result.venue == journal.venue
    # The working paper's doi is retained, not lost, as an alternate.
    assert nber_twin.doi in result.alt_dois
    # Whichever record had the abstract survives the merge.
    assert result.abstract == nber_twin.abstract


def test_merge_candidates_does_not_merge_same_title_far_apart_in_year():
    """Two genuinely different studies can share a title; the year-
    tolerance check is what keeps them from being folded together."""
    early = Candidate(
        title="Impacts of Microfinance on Household Welfare",
        year=1998,
        venue="Journal of Development Economics",
        doi="10.1016/early.1998",
    )
    later = Candidate(
        title="Impacts of Microfinance on Household Welfare",
        year=2023,
        venue="World Development",
        doi="10.1016/later.2023",
    )

    merged = merge_candidates([early, later])

    assert len(merged) == 2


def test_merge_candidates_uses_doi_match_even_with_different_titles():
    """A DOI (or alt_doi) match is the strongest signal and should merge
    records even if title text differs cosmetically."""
    a = Candidate(title="Effects of Job Training on Wages", doi="10.1/x")
    b = Candidate(
        title="Effects of Job Training on Wages: Evidence from a Field Experiment",
        alt_dois=("10.1/x",),
    )

    merged = merge_candidates([a, b])

    assert len(merged) == 1


def test_merge_candidates_passes_through_a_singleton_unchanged():
    solo = Candidate(title="A Standalone Study", year=2021, doi="10.9/solo")
    merged = merge_candidates([solo])
    assert merged == [solo]


def test_merge_candidates_handles_empty_input():
    assert merge_candidates([]) == []


# ── rank ─────────────────────────────────────────────────────────────────

TRAINING_EXTRACTION = Extraction(
    country="Colombia", intervention_types=["training/coaching"]
)


def test_rank_prefers_long_run_income_evidence_over_raw_citations():
    """This is the mission encoded as a test: a modestly-cited study that
    measures long-run earnings persistence must outrank a heavily-cited
    study that never measures an income outcome at all. If this test ever
    fails, the ranking has stopped serving GitLab Foundation's mission
    (lifetime earnings), whatever else it might be optimizing for.
    """
    persistent_income_study = Candidate(
        title="Long-Run Earnings Effects of Vocational Training: A Ten-Year Follow-Up",
        abstract="We find persistent earnings gains ten years after training.",
        year=2015,
        citations=20,
        sources=("econlit",),
        relevance=50.0,
    )
    high_cited_off_mission_study = Candidate(
        title="Vocational Training and School Enrollment Outcomes",
        abstract="This study examines enrollment and self-esteem effects.",
        year=2010,
        citations=5000,
        sources=("econlit",),
        relevance=90.0,
    )

    ranked = rank(
        [high_cited_off_mission_study, persistent_income_study], TRAINING_EXTRACTION
    )

    assert ranked[0].title == persistent_income_study.title
    assert ranked[0].score > ranked[1].score


def test_rank_respects_limit_and_populates_score_notes():
    candidates = [
        Candidate(title=f"Study {i}", abstract="earnings and wages", year=2015 + i)
        for i in range(5)
    ]
    ranked = rank(candidates, TRAINING_EXTRACTION, limit=2)

    assert len(ranked) == 2
    assert all(c.score_notes for c in ranked)
    # Every candidate carries a stated reason for its position. Asserting a
    # specific non-zero score would be brittle — with the off-topic penalty in
    # play a total can legitimately land on 0.0 — and it tests nothing a
    # reviewer cares about. Ordering and explainability are the contract.
    assert ranked[0].score >= ranked[1].score


def test_rank_handles_none_citations_without_crashing():
    no_citations = Candidate(
        title="Earnings Effects Study", abstract="earnings", citations=None
    )
    ranked = rank([no_citations], TRAINING_EXTRACTION)

    assert len(ranked) == 1
    assert not any("citations" in note for note in ranked[0].score_notes)


def test_rank_on_empty_input_returns_empty_list():
    assert rank([], TRAINING_EXTRACTION) == []


# ── Mission calibration: rigor without rigidity ─────────────────────────
#
# The two tests below pin the balance the ranking is supposed to strike.
# Lifetime earnings is an approximation layered on measured income effects, not
# a competing evidence standard, so persistence must inform the ranking without
# overriding direct relevance — and a missing abstract must never be read as a
# missing outcome.


def test_missing_abstract_is_scored_as_unknown_not_as_off_mission():
    """A title-only candidate must not be penalized for the index's gaps.

    econlit populates `abstract` for only ~7% of rows, so treating "no income
    word found" as off-mission would rank on metadata completeness instead of
    relevance, and would demote exactly the on-point titles that the OpenAlex
    enrichment step is about to fill in.
    """
    title_only = Candidate(
        title="Subsidizing Vocational Training for Disadvantaged Youth in Colombia",
        year=2011,
        venue="American Economic Journal: Applied Economics",
        doi="10.1257/app.3.3.188",
        abstract="",
        citations=200,
        sources=("econlit",),
    )
    genuinely_off_mission = Candidate(
        title="Social Preferences and Self-Esteem in Rural Communities",
        year=2023,
        venue="American Economic Review",
        doi="10.1257/aer.20220001",
        abstract=(
            "We study how social exclusion shapes prosocial preferences using a "
            "lab-in-the-field approach. Descendants of excluded individuals are "
            "locally altruistic and extend altruism to outsiders. We measure "
            "altruism, trust, and self-reported wellbeing across two hundred "
            "villages, and find persistent differences in stated preferences "
            "that do not vary with household demographics or village size."
        ),
        citations=200,
        sources=("econlit",),
    )

    ranked = rank([genuinely_off_mission, title_only], Extraction(), limit=5)
    by_doi = {c.doi: c for c in ranked}

    unknown = by_doi["10.1257/app.3.3.188"]
    off_mission = by_doi["10.1257/aer.20220001"]

    # The title-only candidate is flagged as unknown, not judged off-mission.
    assert any("unknown" in note for note in unknown.score_notes)
    assert not any("off-mission" in note for note in unknown.score_notes)
    # The one with a real abstract and no income outcome IS judged.
    assert any("off-mission" in note for note in off_mission.score_notes)
    # And with citations equal, not knowing beats knowing it is off-mission.
    assert unknown.score > off_mission.score


def test_persistence_does_not_outrank_direct_relevance():
    """Long-run evidence is a bonus dimension, not a trump card.

    Most credible RCTs in this literature carry only 1-2 year horizons. If the
    long-run weight matched the income weight, a long-run study of a *different*
    intervention would outrank a directly on-point short-horizon RCT and starve
    the evidence base of its most relevant studies.
    """
    on_point_short_horizon = Candidate(
        title="Vocational Training for Urban Youth in Colombia: Experimental Evidence",
        year=2020,
        venue="American Economic Journal: Applied Economics",
        doi="10.1257/app.on.point",
        abstract=(
            "We report a randomized controlled trial of vocational training for "
            "urban youth in Colombia, measuring effects on monthly earnings and "
            "wages eighteen months after graduation across treatment arms."
        ),
        citations=15,
        sources=("econlit",),
    )
    off_topic_long_run = Candidate(
        title="Long-Term Follow-Up of a Rural Electrification Program",
        year=2019,
        venue="American Economic Review",
        doi="10.1257/aer.off.topic",
        abstract=(
            "We track household earnings ten years after rural electrification, "
            "documenting the persistence of income gains and their fade-out over "
            "a long-run follow-up horizon in a difference-in-differences design."
        ),
        citations=15,
        sources=("econlit",),
    )

    extraction = Extraction(
        country="Colombia",
        intervention_types=["training/coaching"],
    )
    ranked = rank([off_topic_long_run, on_point_short_horizon], extraction, limit=5)

    assert ranked[0].doi == "10.1257/app.on.point", (
        "a directly on-point short-horizon RCT must outrank an off-topic "
        f"long-run study; got {[(c.doi, round(c.score, 2)) for c in ranked]}"
    )


# ── Country relevance (notes/incident-2026-08-01 §11) ────────────────────
#
# For the CodePath.org note, NBER w30227 scored 5.941 and fell just outside the
# 25-candidate cap, while "Long-Run Pollution Exposure and Adult Mortality:
# Evidence from the Acid Rain Program" outranked it — partly on the country
# clause, which w30227 could not earn because its abstract names no country at
# all. Both texts below are the real ones returned by econlit.

CODEPATH_US = Extraction(
    organization="CodePath.org",
    project_title="Reprogramming Higher Education for AI-enabled Engineers",
    summary=(
        "CS courses and career support for Black, Latino/a, Indigenous and "
        "low-income college computing students."
    ),
    intervention_types=["training/coaching", "job placement"],
    mechanisms_to_affect_income="Career support raises placement rates.",
    country="United States",
    population=Population(
        description="first-generation college computing students",
    ),
)

STEM_SUMMER = Candidate(
    title="STEM Summer Programs for Underrepresented Youth Increase STEM Degrees",
    abstract=(
        "Underrepresentation of Black and Hispanic workers in STEM fields "
        "contributes to racial wage gaps. We fielded a randomized controlled "
        "trial to study a suite of such programs targeted to underrepresented "
        "high-school students and hosted at an elite technical institution. "
        "Students offered seats were more likely to enroll in, persist "
        "through, and graduate from elite colleges. These improvements in "
        "college outcomes raised predicted earnings by 3 to 15 percentage "
        "points."
    ),
    venue="NBER Working Papers",
    year=2022,
    doi="10.3386/w30227",
    citations=6,
    sources=("econlit",),
)

ACID_RAIN = Candidate(
    title=(
        "Long-Run Pollution Exposure and Adult Mortality: Evidence from the "
        "Acid Rain Program"
    ),
    abstract=(
        "We study long-run mortality and employment effects of the Acid Rain "
        "Program in the United States."
    ),
    venue="NBER Working Papers",
    year=2017,
    doi="10.3386/w23524",
    citations=40,
    sources=("econlit",),
)


def test_country_neutral_study_is_not_scored_as_a_country_mismatch():
    """An unstated country is UNKNOWN, not a mismatch — the same rule that
    governs a missing abstract. w30227 never says "United States"; almost no
    domestic US study does."""
    ranked = rank([STEM_SUMMER], extraction=CODEPATH_US, limit=1)
    notes = " ".join(ranked[0].score_notes).lower()
    assert "no country stated" in notes
    assert "studies a country other than" not in notes


def test_demonym_counts_as_a_country_match():
    american = Candidate(
        title="Earnings of American college graduates",
        abstract="A randomized evaluation of American labor market earnings.",
        sources=("econlit",),
    )
    ranked = rank([american], extraction=CODEPATH_US, limit=1)
    assert any("target country" in n for n in ranked[0].score_notes)


def test_study_of_a_different_country_earns_no_country_credit():
    kenyan = Candidate(
        title="Microenterprise training in Kenya",
        abstract="A randomized controlled trial of training and earnings in Kenya.",
        sources=("econlit",),
    )
    ranked = rank([kenyan], extraction=CODEPATH_US, limit=1)
    notes = " ".join(ranked[0].score_notes).lower()
    assert "target country" not in notes
    assert "no country stated" not in notes


def test_on_point_study_outranks_an_off_mission_one_that_names_the_country():
    """The incident in one assertion: a directly on-point STEM-education RCT
    must not lose to an acid-rain mortality study for a note about getting
    underrepresented students into technical careers."""
    ranked = rank([ACID_RAIN, STEM_SUMMER], extraction=CODEPATH_US, limit=2)
    assert ranked[0].doi == "10.3386/w30227"
