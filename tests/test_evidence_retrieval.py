"""Tests for `backend.evidence.retrieval.retrieve` — the orchestration layer.

No live network calls: every `EvidenceSource` here is a small in-memory fake
defined in this file. The property under test throughout is the one thing
that matters most about this module — `retrieve()` must never raise and
must never return `None`, no matter how badly the sources underneath it
misbehave, because it sits in front of a research run that costs real money
and up to ~75 minutes (see `retrieval.py`'s module docstring).
"""

import time
from unittest.mock import patch

from backend.evidence.base import Candidate, EvidenceQuery, EvidenceSource, QueryRecord, SearchOutcome
from backend.evidence.retrieval import retrieve
from backend.schemas import Extraction

# Five of the twelve ELITE_JOURNALS entries (research_prompt.py) are
# development/labor journals that no source in this test file ever covers.
# Used by the anti-narrowing test below.
DEVELOPMENT_JOURNALS = (
    "Journal of Development Economics",
    "World Development",
    "Economic Development and Cultural Change",
    "Journal of Human Resources",
    "Journal of Labor Economics",
)

EXTRACTION = Extraction(
    organization="Fundación Impulso",
    project_title="Vocational Training for Urban Youth",
    intervention_types=["training/coaching", "job placement"],
    mechanisms_to_affect_income=(
        "Training increases occupational skills and connects graduates to "
        "employers through job-matching services."
    ),
    country="Colombia",
)


def _candidate(
    title: str,
    doi: str = "",
    venue: str = "",
    year: int = 2020,
    sources: tuple[str, ...] = ("fake",),
    abstract: str = "",
) -> Candidate:
    return Candidate(
        title=title,
        doi=doi,
        venue=venue,
        year=year,
        sources=sources,
        abstract=abstract,
        relevance=1.0,
    )


class FakeSource(EvidenceSource):
    """A stand-in `EvidenceSource` that returns a fixed candidate set (or
    raises, or sleeps) on every `search()` call, regardless of the query."""

    def __init__(
        self,
        source_id: str,
        covered_venues: tuple[str, ...] = (),
        candidates: tuple[Candidate, ...] = (),
        raise_always: bool = False,
        sleep_s: float = 0.0,
    ) -> None:
        self.id = source_id
        self.label = source_id
        self.covered_venues = covered_venues
        self._candidates = candidates
        self._raise_always = raise_always
        self._sleep_s = sleep_s
        self.call_count = 0

    def search(self, query: EvidenceQuery) -> SearchOutcome:
        self.call_count += 1
        if self._sleep_s:
            time.sleep(self._sleep_s)
        if self._raise_always:
            raise RuntimeError(f"{self.id} is down")
        return SearchOutcome(
            candidates=self._candidates,
            record=QueryRecord(
                source=self.id,
                terms=query.terms,
                scope=query.scope,
                mode=query.mode,
                venues=query.venues,
                total_results=len(self._candidates),
                returned=len(self._candidates),
                label=query.label,
            ),
        )


# ── 1. Happy path ────────────────────────────────────────────────────────


def test_happy_path_merges_ranks_and_caps():
    dupe_doi = "10.1/dupe"
    source_a = FakeSource(
        "source_a",
        covered_venues=("Journal of Development Economics", "World Development"),
        candidates=(
            _candidate("Training and Earnings in Colombia", doi=dupe_doi),
            _candidate("Job Placement and Wages", doi="10.1/b"),
        ),
    )
    source_b = FakeSource(
        "source_b",
        covered_venues=("American Economic Review",),
        candidates=(
            # Same study as source_a's first candidate (same DOI) -> merges.
            _candidate("Training and Earnings in Colombia", doi=dupe_doi),
            _candidate("Entrepreneurship Support and Profits", doi="10.1/c"),
        ),
    )

    result = retrieve(EXTRACTION, sources=[source_a, source_b], limit=2)

    assert result.usable
    assert len(result.candidates) == 2  # capped at limit
    # 3 distinct studies were retrievable; dedupe must have collapsed the
    # DOI-matched pair, so raw rows seen > final candidates returned.
    assert result.total_seen > len(result.candidates)
    # Coverage is reported from the venues present in the RETURNED candidates,
    # not from what the sources declared they could reach. These fakes return
    # candidates with no venue set, so nothing is represented — see
    # `test_uncovered_venues_reflects_the_actual_candidate_list` for why this
    # distinction is the whole point.
    assert result.covered_venues == []
    assert result.sources_ok == ["source_a", "source_b"]
    assert result.sources_failed == []
    assert result.queries  # provenance was recorded


# ── 2. One source raises on every call ──────────────────────────────────


def test_one_source_raising_does_not_break_the_run():
    good = FakeSource(
        "good_source",
        covered_venues=("American Economic Review",),
        candidates=(_candidate("A Fine Study", doi="10.1/fine"),),
    )
    bad = FakeSource("bad_source", raise_always=True)

    result = retrieve(EXTRACTION, sources=[good, bad], limit=10)

    assert result.usable
    assert any(c.doi == "10.1/fine" for c in result.candidates)
    assert "bad_source" in result.sources_failed
    assert "good_source" in result.sources_ok
    assert "bad_source" not in result.sources_ok


# ── 3. All sources raise ────────────────────────────────────────────────


def test_all_sources_raising_returns_empty_but_valid_result():
    bad_a = FakeSource("bad_a", raise_always=True)
    bad_b = FakeSource("bad_b", raise_always=True)

    result = retrieve(EXTRACTION, sources=[bad_a, bad_b], limit=10)

    assert result.candidates == []
    assert result.usable is False
    assert set(result.sources_failed) == {"bad_a", "bad_b"}
    assert result.sources_ok == []


# ── 4. Malformed candidate data does not crash the pipeline ────────────


def test_malformed_candidate_data_does_not_crash():
    malformed = Candidate(title="", doi="", venue="", year=None, sources=("odd",))
    source = FakeSource("odd_source", candidates=(malformed,))

    result = retrieve(EXTRACTION, sources=[source], limit=10)

    assert result.usable is True or result.candidates == []  # must not raise
    assert isinstance(result.total_seen, int)


# ── 5. Anti-narrowing: uncovered_venues names development journals ─────


def test_uncovered_venues_names_development_journals_when_only_top_covered():
    """Only a source covering the "big 5" theory journals answers this run.
    The report-facing coverage disclosure (candidate_table.render_coverage)
    depends on `uncovered_venues` naming the development/labor journals that
    carry most of this literature — silently omitting them would turn
    retrieval from a guide into a blinker (see base.py's module docstring).
    This test is the guarantee that never happens.
    """
    top5_only = FakeSource(
        "top5_only",
        covered_venues=(
            "American Economic Review",
            "Econometrica",
            "Journal of Political Economy",
            "The Quarterly Journal of Economics",
            "The Review of Economic Studies",
        ),
        candidates=(_candidate("Some Top-5 Study", doi="10.1/top5"),),
    )

    result = retrieve(EXTRACTION, sources=[top5_only], limit=10)

    for journal in DEVELOPMENT_JOURNALS:
        assert journal in result.uncovered_venues, (
            f"{journal!r} must be disclosed as uncovered when no answering "
            "source declares it"
        )


# ── 6. build_queries returning nothing ──────────────────────────────────


def test_empty_query_list_yields_valid_empty_result_without_crashing():
    source = FakeSource(
        "source_a",
        candidates=(_candidate("Should Never Be Retrieved", doi="10.1/x"),),
    )

    with patch("backend.evidence.retrieval.build_queries", return_value=[]):
        result = retrieve(EXTRACTION, sources=[source], limit=10)

    assert result.candidates == []
    assert result.total_seen == 0
    assert result.usable is False
    assert source.call_count == 0  # nothing was routed anywhere


# ── 7. No OpenAlexSource present -> enrichment skipped, not fatal ──────


def test_no_openalex_source_present_still_returns_candidates():
    source = FakeSource(
        "just_econlit_like",
        candidates=(_candidate("Unenriched Study", doi="10.1/unenriched"),),
    )

    result = retrieve(EXTRACTION, sources=[source], limit=10)

    assert result.usable
    assert any(c.doi == "10.1/unenriched" for c in result.candidates)


# ── 8. Determinism across repeated calls ────────────────────────────────


def test_repeated_calls_produce_identical_ordering():
    source_a = FakeSource(
        "source_a",
        covered_venues=("Journal of Development Economics",),
        candidates=(
            _candidate("Study One", doi="10.1/one"),
            _candidate("Study Two", doi="10.1/two"),
        ),
    )
    source_b = FakeSource(
        "source_b",
        covered_venues=("American Economic Review",),
        candidates=(_candidate("Study Three", doi="10.1/three"),),
    )

    result_1 = retrieve(EXTRACTION, sources=[source_a, source_b], limit=10)
    result_2 = retrieve(EXTRACTION, sources=[source_a, source_b], limit=10)

    dois_1 = [c.doi for c in result_1.candidates]
    dois_2 = [c.doi for c in result_2.candidates]
    assert dois_1 == dois_2
    assert dois_1  # sanity: the fixture actually produced candidates

    keys_1 = [(q.source, q.terms, q.scope, q.mode) for q in result_1.queries]
    keys_2 = [(q.source, q.terms, q.scope, q.mode) for q in result_2.queries]
    assert keys_1 == keys_2


# ── Bonus: wall-clock budget truncation must not block the caller ──────


def test_budget_exceeded_returns_promptly_with_truncation_recorded():
    slow = FakeSource("slow_source", sleep_s=0.2)
    fast = FakeSource(
        "fast_source", candidates=(_candidate("Fast Study", doi="10.1/fast"),)
    )

    with patch("backend.evidence.retrieval.RETRIEVAL_BUDGET_S", 0):
        start = time.monotonic()
        result = retrieve(EXTRACTION, sources=[slow, fast], limit=10)
        elapsed = time.monotonic() - start

    # Must not block on the slow source's sleep once the budget is spent.
    assert elapsed < 0.2
    assert any(q.error and "budget" in q.error.lower() for q in result.queries)


# ── Anti-narrowing guarantee (regression) ───────────────────────────────
#
# This is the most important behavior in the whole retrieval layer, and it was
# silently broken on the first live run.
#
# `covered_venues` was originally the union of each source's DECLARED
# `covered_venues`. OpenAlex declares the five development journals because it
# can filter on their ISSNs, so on a real Colombian youth-training note the
# union covered every venue in ELITE_JOURNALS and `uncovered_venues` came back
# EMPTY — while the actual candidate list contained zero papers from any
# development journal. That silently removed the disclosure telling the research
# agent to search those journals itself, which is the one thing standing between
# "retrieval guides the agent" and "retrieval blinds it".
#
# Coverage must therefore be a fact about the returned list, never a promise
# about reach.


def test_uncovered_venues_reflects_the_actual_candidate_list():
    """A venue a source *can* search is not covered until a paper comes back."""
    top5_only = FakeSource(
        "top5",
        # Declares reach over the development journals...
        covered_venues=(
            "American Economic Review",
            "Journal of Development Economics",
            "World Development",
        ),
        candidates=(
            # ...but only ever returns AER papers.
            _candidate(
                "Training and Earnings in Colombia",
                doi="10.1/aer1",
                venue="American Economic Review",
                abstract="We study earnings effects of vocational training.",
            ),
        ),
    )

    result = retrieve(EXTRACTION, sources=[top5_only], limit=10)

    assert result.usable
    assert "American Economic Review" in result.covered_venues
    # The declared-but-unrepresented journals must be reported as gaps, so the
    # prompt tells the agent to go search them.
    assert "Journal of Development Economics" in result.uncovered_venues, (
        "a declared-but-unrepresented venue must be reported as a gap; "
        f"got covered={result.covered_venues} uncovered={result.uncovered_venues}"
    )
    assert "World Development" in result.uncovered_venues
    # And a venue must never appear in both lists.
    assert not set(result.covered_venues) & set(result.uncovered_venues)
