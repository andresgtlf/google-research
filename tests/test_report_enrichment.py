"""Tests for post-research report enrichment: Section L parsing, free-version
resolution, and citation existence checks.

No live network: fake `EvidenceSource` subclasses stand in for econlit and
OpenAlex.
"""

import json
from pathlib import Path

from backend.evidence.attribution import ATTRIBUTION_MARKDOWN
from backend.evidence.base import (
    Candidate,
    EvidenceQuery,
    EvidenceSource,
    QueryRecord,
    SearchOutcome,
)
from backend.evidence.resolve_k import (
    Resolution,
    render_resolutions_markdown,
    resolve_paywalled,
)
from backend.evidence.verify import render_verification_markdown, verify_citations
from backend.export import create_markdown_report
from backend.report_parse import PaywalledPaper, extract_dois, parse_paywalled_papers


# ── Fakes ─────────────────────────────────────────────────────────────


class FakeEconlit(EvidenceSource):
    id = "econlit"
    label = "Fake Econlit"

    def __init__(self, by_title=None, raise_on_title=None):
        self._by_title = by_title or {}
        self._raise_on_title = raise_on_title or set()
        self.call_count = 0

    def search(self, query: EvidenceQuery) -> SearchOutcome:
        return SearchOutcome(candidates=())

    def find_by_title(self, title: str) -> SearchOutcome:
        self.call_count += 1
        if title in self._raise_on_title:
            raise RuntimeError("econlit is down")
        candidates = tuple(self._by_title.get(title, ()))
        return SearchOutcome(
            candidates=candidates,
            record=QueryRecord(
                source="econlit", terms=title, scope="title", mode="stemmed"
            ),
        )


class FakeOpenAlex(EvidenceSource):
    id = "openalex"
    label = "Fake OpenAlex"

    def __init__(self, by_doi=None, raise_on_doi=None):
        self._by_doi = by_doi or {}
        self._raise_on_doi = raise_on_doi or set()
        self.call_count = 0

    def search(self, query: EvidenceQuery) -> SearchOutcome:
        return SearchOutcome(candidates=())

    def lookup_by_doi(self, doi: str):
        self.call_count += 1
        if doi in self._raise_on_doi:
            raise RuntimeError("openalex is down")
        return self._by_doi.get(doi)


# ── Parser: three realistic, differently-formatted Section L samples ──

SAMPLE_NUMBERED_BOLD = """
## Paywalled High-Value Papers — Manual Retrieval List

1. **General Equilibrium Effects of Cash Transfers on Local Economies**, \
Bandiera, O., Burgess, R., and Sulaiman, M. (2022). Econometrica. \
DOI: 10.3982/ecta17945. Highly relevant: studies GE spillovers of a large \
cash transfer program with a strong identification strategy and hundreds of \
citations. Repositories checked: SSRN, NBER, publisher site. \
Status: not included (inaccessible).

2. **Long-Run Impacts of Unconditional Cash Transfers on Consumption and \
Assets**, Haushofer, J. and Shapiro, J. (2018). Quarterly Journal of \
Economics. DOI: 10.1093/qje/qjx038. Well-cited RCT with a multi-year \
follow-up. Repositories checked: NBER, publisher site. \
Status: abstract-only (included with limited extraction).

## Next Section
Irrelevant trailing content.
"""

SAMPLE_BULLET_INLINE_FIELDS = """
## Paywalled High-Value Papers — Manual Retrieval List

- Title: "Microenterprise Growth and Subsidized Capital"
  - Authors: de Mel, S., McKenzie, D., Woodruff, C.
  - Year: 2019
  - Journal: American Economic Review
  - DOI: 10.1257/aer.20160209
  - Why relevant: High-quality field RCT on capital constraints, strong venue.
  - Checked: NBER, SSRN, publisher site
  - Status: not included (inaccessible)

- Title: "Returns to Capital for Female Microenterprise Owners"
  - Authors: Fafchamps, M., McKenzie, D., Quinn, S., Woodruff, C.
  - Year: 2014
  - Journal: Journal of Development Economics
  - Publisher page: https://www.sciencedirect.com/science/article/pii/S0304387813001596
  - Why relevant: directly tests a gendered mechanism the note relies on.
  - Checked: NBER, publisher site
  - Status: abstract-only (included with limited extraction)
"""

SAMPLE_HEADING_PER_PAPER = """
## Paywalled High-Value Papers — Manual Retrieval List

### 1. "Poverty and the Psychology of Scarcity"

- Authors: Mullainathan, S., Shafir, E.
- Year: 2013
- Publisher URL: https://www.journals.uchicago.edu/doi/abs/10.xxxx/scarcity
- DOI: 10.1086/671221
- Why relevant: foundational theory paper underlying the note's mechanism.
- Checked: NBER, JSTOR, publisher site
- Status: not included (inaccessible)

### 2. "Behavioral Development Economics"

- Authors: Kremer, M., Rao, G., Schilbach, F.
- Year: 2019
- DOI: 10.1016/bs.hesbe.2018.12.002
- Why relevant: widely cited handbook chapter informing the theory of change.
- Checked: publisher site
- Status: abstract-only (included with limited extraction)
"""

SAMPLE_NONE_IDENTIFIED = """
## Paywalled High-Value Papers — Manual Retrieval List

No high-value paywalled papers were identified.
"""


def test_attribution_markdown_credits_both_evidence_sources() -> None:
    assert "Goldsmith-Pinkham" in ATTRIBUTION_MARKDOWN
    assert "paulgp.com" in ATTRIBUTION_MARKDOWN
    assert "openalex.org" in ATTRIBUTION_MARKDOWN


def test_markdown_export_includes_evidence_source_attribution(tmp_path: Path) -> None:
    research_path = tmp_path / "research.json"
    research_path.write_text(
        json.dumps({"extraction": {}, "result": "Minimal research result."}),
        encoding="utf-8",
    )

    markdown_path = create_markdown_report(research_path)

    assert ATTRIBUTION_MARKDOWN in markdown_path.read_text(encoding="utf-8")


def test_parses_numbered_bold_format():
    papers = parse_paywalled_papers(SAMPLE_NUMBERED_BOLD)
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.title == "General Equilibrium Effects of Cash Transfers on Local Economies"
    assert p1.doi == "10.3982/ecta17945"
    assert "Bandiera" in p1.authors
    assert p1.year == 2022
    assert "Econometrica" in p1.venue
    assert p1.status == "not included (inaccessible)"
    assert p1.raw  # original block preserved

    p2 = papers[1]
    assert p2.doi == "10.1093/qje/qjx038"
    assert p2.year == 2018
    assert p2.status == "abstract-only (included with limited extraction)"


def test_parses_bullet_inline_fields_format():
    papers = parse_paywalled_papers(SAMPLE_BULLET_INLINE_FIELDS)
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.title == "Microenterprise Growth and Subsidized Capital"
    assert p1.authors.startswith("de Mel")
    assert p1.year == 2019
    assert p1.venue == "American Economic Review"
    assert p1.doi == "10.1257/aer.20160209"
    assert p1.status == "not included (inaccessible)"

    p2 = papers[1]
    assert p2.title == "Returns to Capital for Female Microenterprise Owners"
    assert p2.publisher_url.startswith("https://www.sciencedirect.com")
    assert p2.status == "abstract-only (included with limited extraction)"


def test_parses_heading_per_paper_format():
    papers = parse_paywalled_papers(SAMPLE_HEADING_PER_PAPER)
    assert len(papers) == 2

    p1 = papers[0]
    assert p1.title == "Poverty and the Psychology of Scarcity"
    assert p1.doi == "10.1086/671221"
    assert p1.year == 2013
    assert p1.status == "not included (inaccessible)"

    p2 = papers[1]
    assert p2.title == "Behavioral Development Economics"
    assert p2.doi == "10.1016/bs.hesbe.2018.12.002"
    assert p2.status == "abstract-only (included with limited extraction)"


def test_no_papers_identified_returns_empty_list():
    assert parse_paywalled_papers(SAMPLE_NONE_IDENTIFIED) == []


def test_empty_string_returns_empty_list():
    assert parse_paywalled_papers("") == []


def test_garbage_input_never_raises():
    garbage_inputs = [
        "###$$$ !!! not markdown at all @@@ ???",
        "\x00\x01\x02 binary-ish junk",
        "## Paywalled High-Value Papers — Manual Retrieval List\n" + ("x" * 5000),
        None,
    ]
    for garbage in garbage_inputs:
        result = parse_paywalled_papers(garbage)  # type: ignore[arg-type]
        assert isinstance(result, list)


def test_extract_dois_handles_url_bare_and_trailing_punctuation():
    text = (
        "See https://doi.org/10.1257/aer.20160209 for details. "
        "Also bare 10.1093/qje/qjx038 doi. "
        "And cite (10.3982/ecta17945)."
    )
    dois = extract_dois(text)
    assert dois == ["10.1257/aer.20160209", "10.1093/qje/qjx038", "10.3982/ecta17945"]


def test_extract_dois_deduplicates():
    text = "10.1257/aer.20160209 and again https://doi.org/10.1257/aer.20160209"
    assert extract_dois(text) == ["10.1257/aer.20160209"]


def test_extract_dois_empty_and_garbage_never_raise():
    assert extract_dois("") == []
    assert extract_dois("no dois here at all") == []


# ── Resolver tests ──────────────────────────────────────────────────


def _paper(**kwargs) -> PaywalledPaper:
    defaults = dict(title="", authors="", year=None, venue="", doi="")
    defaults.update(kwargs)
    return PaywalledPaper(**defaults)


def test_resolve_via_doi_when_openalex_has_open_access_url():
    paper = _paper(title="Some Paywalled Study", doi="10.1257/aer.999999")
    openalex = FakeOpenAlex(
        by_doi={
            "10.1257/aer.999999": Candidate(
                title="Some Paywalled Study",
                doi="10.1257/aer.999999",
                venue="American Economic Review",
                oa_url="https://example.com/free-copy.pdf",
            )
        }
    )
    resolutions = resolve_paywalled([paper], econlit=None, openalex=openalex)
    assert len(resolutions) == 1
    r = resolutions[0]
    assert r.found_free_version is True
    assert r.free_url == "https://example.com/free-copy.pdf"


def test_resolve_via_title_finds_nber_twin_and_constructs_url():
    title = "General Equilibrium Effects of Cash Transfers"
    paper = _paper(title=title, doi="10.3982/ecta17945")
    econlit = FakeEconlit(
        by_title={
            title: [
                Candidate(
                    title=title,
                    venue="Econometrica",
                    doi="10.3982/ecta17945",
                ),
                Candidate(
                    title=title,
                    venue="NBER Working Papers",
                    doi="10.3386/w26600",
                ),
            ]
        }
    )
    # openalex intentionally omitted: the NBER DOI resolves to a free URL
    # directly, no OpenAlex lookup needed.
    resolutions = resolve_paywalled([paper], econlit=econlit, openalex=None)
    assert len(resolutions) == 1
    r = resolutions[0]
    assert r.found_free_version is True
    assert r.free_url == "https://www.nber.org/papers/w26600"
    assert r.free_doi == "10.3386/w26600"


def test_resolve_near_miss_title_does_not_resolve():
    # Same first several words, but genuinely a different study (a different
    # country). A false "this is free" is worse than reporting nothing, so
    # this must NOT match even though the titles are superficially similar.
    paper_title = "General Equilibrium Effects of Cash Transfers"
    different_title = "General Equilibrium Effects of Cash Transfers in Kenya"
    paper = _paper(title=paper_title, doi="10.3982/ecta17945")
    econlit = FakeEconlit(
        by_title={
            paper_title: [
                Candidate(
                    title=different_title,
                    venue="NBER Working Papers",
                    doi="10.3386/w99999",
                )
            ]
        }
    )
    resolutions = resolve_paywalled([paper], econlit=econlit, openalex=None)
    assert resolutions[0].found_free_version is False


def test_resolve_both_sources_none_leaves_all_unresolved_without_raising():
    papers = [_paper(title="A"), _paper(title="B", doi="10.1/xyz")]
    resolutions = resolve_paywalled(papers, econlit=None, openalex=None)
    assert len(resolutions) == 2
    assert all(not r.found_free_version for r in resolutions)


def test_resolve_source_raising_leaves_paper_unresolved_with_note():
    title = "A Study That Breaks The Lookup"
    paper = _paper(title=title)
    econlit = FakeEconlit(raise_on_title={title})
    resolutions = resolve_paywalled([paper], econlit=econlit, openalex=None)
    assert len(resolutions) == 1
    assert resolutions[0].found_free_version is False
    assert resolutions[0].note


def test_resolve_respects_max_lookups():
    papers = [
        _paper(title=f"Study {i}", doi=f"10.1/{i}") for i in range(5)
    ]
    openalex = FakeOpenAlex(by_doi={})  # never finds anything, just counts calls
    resolve_paywalled(papers, econlit=None, openalex=openalex, max_lookups=2)
    assert openalex.call_count == 2


def test_resolve_skips_papers_with_no_title_and_no_doi():
    resolutions = resolve_paywalled([_paper()], econlit=None, openalex=None)
    assert resolutions == []


def test_render_resolutions_markdown():
    resolved = Resolution(
        paper=_paper(title="Found Paper", doi="10.1/found"),
        found_free_version=True,
        free_url="https://www.nber.org/papers/w1",
        free_venue="NBER Working Papers",
        note="Free NBER working-paper twin found by exact title match.",
    )
    unresolved = Resolution(
        paper=_paper(title="Missing Paper", doi="10.1/missing"),
        found_free_version=False,
        note="No free version could be confirmed automatically.",
    )
    md = render_resolutions_markdown([resolved, unresolved])
    assert "1 of 2" in md
    assert "Found Paper" in md
    assert "Missing Paper" in md
    assert "https://www.nber.org/papers/w1" in md


def test_render_resolutions_markdown_empty():
    assert render_resolutions_markdown([]) == ""


# ── Verifier tests ──────────────────────────────────────────────────


def test_verify_found_doi_returns_exists_true_with_metadata():
    openalex = FakeOpenAlex(
        by_doi={
            "10.1257/aer.999": Candidate(
                title="A Real Paper",
                doi="10.1257/aer.999",
                year=2020,
                citations=42,
                oa_url="https://example.com/paper.pdf",
            )
        }
    )
    checks = verify_citations(["10.1257/aer.999"], openalex=openalex)
    assert len(checks) == 1
    c = checks[0]
    assert c.exists is True
    assert c.title == "A Real Paper"
    assert c.year == 2020
    assert c.citations == 42


def test_verify_unknown_doi_reports_unverified_and_rendering_avoids_loaded_words():
    openalex = FakeOpenAlex(by_doi={})  # DOI simply isn't there
    checks = verify_citations(["10.9999/does-not-exist"], openalex=openalex)
    assert len(checks) == 1
    assert checks[0].exists is False

    md = render_verification_markdown(checks)
    lowered = md.lower()
    assert "fabricated" not in lowered
    assert "hallucinated" not in lowered
    assert "could not be verified" in lowered


def test_verify_source_raising_never_raises():
    openalex = FakeOpenAlex(raise_on_doi={"10.1/broken"})
    checks = verify_citations(["10.1/broken"], openalex=openalex)
    assert len(checks) == 1
    assert checks[0].exists is False


def test_verify_respects_max_lookups():
    dois = [f"10.1/{i}" for i in range(5)]
    openalex = FakeOpenAlex(by_doi={})
    verify_citations(dois, openalex=openalex, max_lookups=2)
    assert openalex.call_count == 2


def test_render_verification_markdown_empty():
    assert render_verification_markdown([]) == ""


# ── Supplement-URL guard (regression) ───────────────────────────────────
#
# Verified live against OpenAlex: 10.3982/ecta17945 (Egger et al., Econometrica
# 2022) reports is_oa=True / oa_status=bronze / version=publishedVersion, but the
# oa_url it hands back is ".../supp/ecta200500-sup-0001-onlineappendix.pdf" — the
# online appendix, not the article. The resolver used to accept that as a resolved
# free version AND short-circuit before trying econlit, which does hold the free
# NBER twin (10.3386/w26600) for this exact paper. So the weak link both misled
# the reviewer and cost us the better answer.

_APPENDIX_URL = (
    "https://www.econometricsociety.org/publications/econometrica/2022/11/01/"
    "General-Equilibrium-Effects/supp/ecta200500-sup-0001-onlineappendix.pdf"
)
_GE_TITLE = "General Equilibrium Effects of Cash Transfers"

_SUPPLEMENT_ONLY = {
    "10.3982/ecta17945": Candidate(
        title=_GE_TITLE,
        year=2022,
        venue="Econometrica",
        doi="10.3982/ecta17945",
        is_oa=True,
        oa_url=_APPENDIX_URL,
    )
}
_NBER_TWIN = {
    _GE_TITLE: (
        Candidate(
            title=_GE_TITLE,
            year=2019,
            venue="NBER Working Papers",
            doi="10.3386/w26600",
        ),
    )
}


def test_supplement_oa_link_does_not_short_circuit_the_nber_twin():
    """A supplement link must not beat the real free working paper."""
    paper = PaywalledPaper(title=_GE_TITLE, doi="10.3982/ecta17945")
    resolutions = resolve_paywalled(
        [paper],
        econlit=FakeEconlit(by_title=_NBER_TWIN),
        openalex=FakeOpenAlex(by_doi=_SUPPLEMENT_ONLY),
    )
    assert len(resolutions) == 1
    res = resolutions[0]
    assert res.found_free_version is True
    assert res.free_url == "https://www.nber.org/papers/w26600", (
        f"should have preferred the free NBER twin, got {res.free_url!r}"
    )
    assert "onlineappendix" not in res.free_url


def test_supplement_link_is_offered_but_never_counted_as_the_article():
    """With no twin available, the appendix is surfaced but labelled honestly."""
    paper = PaywalledPaper(title=_GE_TITLE, doi="10.3982/ecta17945")
    resolutions = resolve_paywalled(
        [paper], econlit=None, openalex=FakeOpenAlex(by_doi=_SUPPLEMENT_ONLY)
    )
    res = resolutions[0]
    # Surfaced, because an appendix still has some value...
    assert "onlineappendix" in res.free_url
    # ...but NOT counted as readable, so the summary count stays honest.
    assert res.found_free_version is False
    assert "supplementary material" in res.note


def test_a_genuine_full_text_oa_link_still_resolves_immediately():
    """The guard must not break the normal case it sits in front of."""
    real = {
        "10.1257/app.1.1.1": Candidate(
            title="A Real Open Access Paper",
            venue="AEJ: Applied Economics",
            doi="10.1257/app.1.1.1",
            is_oa=True,
            oa_url="https://www.nber.org/system/files/working_papers/w1/w1.pdf",
        )
    }
    resolutions = resolve_paywalled(
        [PaywalledPaper(title="A Real Open Access Paper", doi="10.1257/app.1.1.1")],
        econlit=None,
        openalex=FakeOpenAlex(by_doi=real),
    )
    assert resolutions[0].found_free_version is True
    assert resolutions[0].free_url.endswith("w1.pdf")


# ── Attribution renders as real markup, not just as a matching string ────
#
# Regression: the first version of ATTRIBUTION_MARKDOWN put the bullet list
# directly after the intro paragraph with no blank line. Python-Markdown (which
# export.py uses to build the PDF) will not start a list that interrupts a
# paragraph, so it absorbed both bullets into one <p> and the reviewer's PDF
# showed a run-on sentence with stray "-" characters. A test asserting only that
# the string appears in the exported markdown passed the whole time.


def test_attribution_renders_as_a_real_list_in_html():
    """Assert the rendered output, not the source string."""
    import markdown

    from backend.evidence.attribution import ATTRIBUTION_MARKDOWN

    html = markdown.markdown(ATTRIBUTION_MARKDOWN, extensions=["tables", "fenced_code"])

    assert "<ul>" in html, (
        "the attribution bullets must render as a list; a missing blank line "
        f"before the list silently collapses them into a paragraph. Got: {html}"
    )
    assert html.count("<li>") == 2
    # Both credits must survive as clickable links in the PDF.
    assert 'href="https://paulgp.com/econlit-pipeline/"' in html
    assert 'href="https://openalex.org"' in html
    # No literal bullet characters leaking into rendered prose.
    assert "\n- " not in html
