"""Tests for the evidence-retrieval sources (econlit, OpenAlex, enrichment).

No live network calls: every HTTP boundary is mocked via `unittest.mock.patch`
on `requests.Session.get`. These cover the contract that matters most for
this layer — a dead or malformed remote response must never raise, only
degrade into a `SearchOutcome` (or `None`) carrying an error/note.
"""

from unittest.mock import MagicMock, patch

import requests

from backend.evidence.base import Candidate, EvidenceQuery
from backend.evidence.econlit import EconlitSource
from backend.evidence.enrich import enrich
from backend.evidence.openalex import (
    OpenAlexSource,
    abstract_from_inverted_index,
)


def _mock_response(json_data, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            f"{status_code} error"
        )
    else:
        response.raise_for_status.side_effect = None
    return response


# ── econlit: row -> Candidate mapping ──────────────────────────────


def test_econlit_maps_row_with_comma_separated_authors_and_null_replication():
    payload = {
        "query": "cash transfers",
        "total_results": 1,
        "results": [
            {
                "doi": "10.1257/aer.123",
                "title": "Cash Transfers and Earnings",
                "authors": "Jane Doe, John Smith, A. N. Other",
                "year": 2021,
                "journal": "American Economic Review",
                "abstract": "",
                "url": "",
                "relevance": 0.87,
                "snippet": "...",
                "citation_count": 42,
                "chunks_matched": 1,
                "pages_matched": [1],
                "replication": None,
            }
        ],
        "filters": {},
    }
    source = EconlitSource()
    with patch.object(
        source._session, "get", return_value=_mock_response(payload)
    ):
        outcome = source.search(EvidenceQuery(terms="cash transfers"))

    assert outcome.ok
    assert len(outcome.candidates) == 1
    candidate = outcome.candidates[0]
    assert candidate.authors == ("Jane Doe", "John Smith", "A. N. Other")
    assert candidate.doi == "10.1257/aer.123"
    assert candidate.year == 2021
    assert candidate.venue == "American Economic Review"
    assert candidate.citations == 42
    assert candidate.replication_status == ""
    assert candidate.replication_url == ""
    assert candidate.sources == ("econlit",)
    assert outcome.record is not None
    assert outcome.record.total_results == 1
    assert outcome.record.returned == 1
    assert outcome.record.error == ""


def test_econlit_maps_populated_replication_block():
    payload = {
        "total_results": 1,
        "results": [
            {
                "doi": "10.1257/aer.999",
                "title": "Replicated Study",
                "authors": "Solo Author",
                "year": 2019,
                "journal": "Econometrica",
                "replication": {
                    "status": "verified",
                    "icpsr_id": "12345",
                    "repo_host": "openICPSR",
                    "repo_doi": "10.3886/E12345",
                    "reason": "",
                    "repo_url": "https://www.openicpsr.org/openicpsr/project/12345",
                },
            }
        ],
    }
    source = EconlitSource()
    with patch.object(
        source._session, "get", return_value=_mock_response(payload)
    ):
        outcome = source.search(EvidenceQuery(terms="x"))

    candidate = outcome.candidates[0]
    assert candidate.replication_status == "verified"
    assert (
        candidate.replication_url
        == "https://www.openicpsr.org/openicpsr/project/12345"
    )


# ── econlit: failure modes must never raise ────────────────────────


def test_econlit_total_failure_returns_error_outcome_without_raising():
    source = EconlitSource()
    with patch.object(
        source._session, "get", side_effect=requests.ConnectionError("boom")
    ):
        outcome = source.search(EvidenceQuery(terms="anything"))

    assert not outcome.ok
    assert outcome.candidates == ()
    assert outcome.record is not None
    assert outcome.record.error != ""


def test_econlit_malformed_json_list_instead_of_dict_does_not_raise():
    source = EconlitSource()
    with patch.object(
        source._session, "get", return_value=_mock_response(["not", "a", "dict"])
    ):
        outcome = source.search(EvidenceQuery(terms="anything"))

    assert not outcome.ok
    assert outcome.candidates == ()


def test_econlit_malformed_row_missing_keys_does_not_raise():
    payload = {"results": [{"only_key": "value"}]}
    source = EconlitSource()
    with patch.object(
        source._session, "get", return_value=_mock_response(payload)
    ):
        outcome = source.search(EvidenceQuery(terms="anything"))

    assert outcome.ok
    assert len(outcome.candidates) == 1
    assert outcome.candidates[0].title == ""
    assert outcome.candidates[0].authors == ()


def test_econlit_find_by_title_quotes_title_and_scopes_to_title():
    source = EconlitSource()
    captured = {}

    def _capture_get(url, params=None, timeout=None):
        captured["params"] = params
        return _mock_response({"results": []})

    with patch.object(source._session, "get", side_effect=_capture_get):
        source.find_by_title("Cash and the Poor")

    assert captured["params"]["q"] == '"Cash and the Poor"'
    assert captured["params"]["search_in"] == "title"


# ── OpenAlex: abstract reconstruction ───────────────────────────────


def test_abstract_from_inverted_index_orders_words_by_position():
    index = {"cat": [2], "The": [0], "sat": [3], "fluffy": [1]}
    assert abstract_from_inverted_index(index) == "The fluffy cat sat"


def test_abstract_from_inverted_index_handles_empty_and_none():
    assert abstract_from_inverted_index(None) == ""
    assert abstract_from_inverted_index({}) == ""


# ── OpenAlex: DOI normalization + lookup mapping ───────────────────


def test_openalex_normalizes_full_url_doi_to_bare_doi():
    work = {
        "doi": "https://doi.org/10.3982/ecta17945",
        "title": "A Paper",
        "publication_year": 2020,
        "cited_by_count": 10,
        "open_access": {"is_oa": True, "oa_url": "https://example.org/paper.pdf"},
        "authorships": [{"author": {"display_name": "A. Researcher"}}],
        "primary_location": {"source": {"display_name": "Econometrica"}},
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
    }
    source = OpenAlexSource()
    with patch.object(source._session, "get", return_value=_mock_response(work)):
        candidate = source.lookup_by_doi("10.3982/ecta17945")

    assert candidate is not None
    assert candidate.doi == "10.3982/ecta17945"
    assert candidate.is_oa is True
    assert candidate.oa_url == "https://example.org/paper.pdf"
    assert candidate.authors == ("A. Researcher",)
    assert candidate.venue == "Econometrica"
    assert candidate.abstract == "Hello world"
    assert candidate.sources == ("openalex",)


def test_openalex_lookup_by_doi_returns_none_on_request_failure():
    source = OpenAlexSource()
    with patch.object(
        source._session, "get", side_effect=requests.Timeout("slow")
    ):
        candidate = source.lookup_by_doi("10.1/whatever")

    assert candidate is None


# ── OpenAlex: rate limiting ──────────────────────────────────────────


def test_openalex_429_returns_error_outcome_without_raising():
    source = OpenAlexSource()
    with patch.object(
        source._session, "get", return_value=_mock_response({}, status_code=429)
    ):
        outcome = source.search(EvidenceQuery(terms="poverty"))

    assert not outcome.ok
    assert outcome.candidates == ()
    assert "rate limit" in outcome.record.error.lower()


def test_openalex_429_on_doi_lookup_returns_none():
    source = OpenAlexSource()
    with patch.object(
        source._session, "get", return_value=_mock_response({}, status_code=429)
    ):
        candidate = source.lookup_by_doi("10.1/whatever")

    assert candidate is None


# ── enrich ───────────────────────────────────────────────────────────


def _bare_candidate(title: str, doi: str = "10.1/x") -> Candidate:
    return Candidate(title=title, doi=doi, sources=("econlit",))


def test_enrich_preserves_order_and_merges_matches():
    candidates = [
        _bare_candidate("First", doi="10.1/a"),
        _bare_candidate("Second", doi="10.1/b"),
        _bare_candidate("Third", doi="10.1/c"),
    ]
    source = OpenAlexSource()

    def _lookup(doi: str):
        return Candidate(title="", abstract=f"abstract for {doi}", oa_url=f"https://x/{doi}")

    with patch.object(source, "lookup_by_doi", side_effect=_lookup):
        enriched, notes = enrich(candidates, source, max_lookups=30)

    assert [c.title for c in enriched] == ["First", "Second", "Third"]
    assert enriched[0].abstract == "abstract for 10.1/a"
    assert enriched[1].abstract == "abstract for 10.1/b"
    assert enriched[2].abstract == "abstract for 10.1/c"
    assert notes == []


def test_enrich_respects_max_lookups_cap():
    candidates = [_bare_candidate(f"Paper {i}", doi=f"10.1/{i}") for i in range(5)]
    source = OpenAlexSource()

    def _lookup(doi: str):
        return Candidate(title="", abstract="filled", oa_url="https://x")

    with patch.object(source, "lookup_by_doi", side_effect=_lookup) as mocked:
        enriched, notes = enrich(candidates, source, max_lookups=2)

    assert mocked.call_count == 2
    assert sum(1 for c in enriched if c.abstract == "filled") == 2
    assert sum(1 for c in enriched if c.abstract == "") == 3
    assert any("cap" in note for note in notes)
    assert [c.title for c in enriched] == [f"Paper {i}" for i in range(5)]


def test_enrich_leaves_candidate_unchanged_on_lookup_failure():
    candidates = [_bare_candidate("Broken", doi="10.1/broken")]
    source = OpenAlexSource()

    with patch.object(
        source, "lookup_by_doi", side_effect=RuntimeError("network exploded")
    ):
        enriched, notes = enrich(candidates, source, max_lookups=30)

    assert enriched[0] == candidates[0]
    assert len(notes) == 1
    assert "Broken" in notes[0]


def test_enrich_skips_candidates_already_complete():
    complete = Candidate(
        title="Complete",
        doi="10.1/complete",
        abstract="already have it",
        oa_url="https://already/have/it",
    )
    source = OpenAlexSource()

    with patch.object(source, "lookup_by_doi") as mocked:
        enriched, notes = enrich([complete], source, max_lookups=30)

    mocked.assert_not_called()
    assert enriched == [complete]
    assert notes == []


def test_enrich_skips_candidates_without_doi():
    no_doi = Candidate(title="No DOI", doi="")
    source = OpenAlexSource()

    with patch.object(source, "lookup_by_doi") as mocked:
        enriched, notes = enrich([no_doi], source, max_lookups=30)

    mocked.assert_not_called()
    assert enriched == [no_doi]
