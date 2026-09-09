from backend.citations import prepare_citations
from backend.report_html import report_html

REPORT = """## Conclusions

Income increased (Smith et al., 2020). Smith et al. (2020) measured a follow-up.

## References

Smith, A. A., Jones, B. B., & Lee, C. C. (2020). Training and earnings. *Journal of Examples, 12*(3), 45–67. https://doi.org/10.1234/example
"""


def test_apa_author_date_links_and_return_links():
    result = prepare_citations(REPORT)
    assert result.reference_count == 1
    assert result.citation_count == 2
    assert "[Smith et al., 2020](#ref-smith-et-al-2020)" in result.markdown
    assert "[Back to citation 2](#cite-ref-smith-et-al-2020-2)" in result.markdown
    assert (
        "[https://doi.org/10.1234/example](https://doi.org/10.1234/example)"
        in result.markdown
    )
    assert prepare_citations(result.markdown).markdown == result.markdown


def test_explicit_protocol_links_and_pdf_destinations():
    text = """## Conclusions

([Smith, 2020](#ref-smith-2020)).

## References

<a id="ref-smith-2020"></a>Smith, A. (2020). A study. *Journal, 1*, 1–9. [https://doi.org/10.1234/a](https://doi.org/10.1234/a)
"""
    result = prepare_citations(text)
    html = report_html(result.markdown)
    assert '<a id="ref-smith-2020"></a>' in html
    assert 'href="#ref-smith-2020"' in html
    assert 'id="cite-ref-smith-2020-1"' in html
    assert 'href="#cite-ref-smith-2020-1"' in html
    assert 'class="apa-reference"' in html
    assert 'class="citation-backlinks"' in html
    assert 'id="references"' in html


def test_unknown_reference_does_not_invent_metadata():
    result = prepare_citations("## Conclusions\n\nUnverified statement.")
    assert result.reference_count == 0
    assert result.warnings
    assert "## References" not in result.markdown


def test_ambiguous_same_author_year_is_not_guessed():
    text = "Smith (2020)\n\n## References\n\nSmith, A. (2020). First.\n\nSmith, A. (2020). Second."
    result = prepare_citations(text)
    assert result.citation_count == 0
    assert result.warnings
    assert "Smith (2020)" in result.markdown


def test_same_year_suffixes_two_authors_and_organizations():
    text = """Smith & Jones (2020a). (Smith & Jones, 2020b). World Bank (n.d.).

## References

Smith, A., & Jones, B. (2020a). First.

Smith, A., & Jones, B. (2020b). Second.

World Bank. (n.d.). Statistics.
"""
    result = prepare_citations(text)
    assert result.citation_count == 3
    assert result.reference_count == 3


def test_no_links_inside_code_or_existing_external_links():
    text = REPORT.replace(
        "Income increased (Smith et al., 2020). Smith et al. (2020) measured a follow-up.",
        "`Smith et al. (2020)`\n\n[Smith et al. (2020)](https://example.org)\n\n```\n[Smith et al., 2020](#ref-smith-et-al-2020)\n```",
    )
    result = prepare_citations(text)
    assert result.citation_count == 0
    assert "`Smith et al. (2020)`" in result.markdown


def test_broken_explicit_target_is_flagged():
    result = prepare_citations(
        REPORT.replace(
            "Income increased", "[Missing, 1999](#ref-missing-1999). Income increased"
        )
    )
    assert "](#ref-missing-1999)" not in result.markdown
    assert result.warnings


def test_full_date_reference_and_duplicate_anchor_safety():
    result = prepare_citations(
        "World Bank (2024).\n\n## References\n\nWorld Bank. (2024, March 1). Statistics."
    )
    assert result.citation_count == 1
    duplicate = """[Smith, 2020](#ref-smith)

## References

<a id="ref-smith"></a>Smith, A. (2020). First.

<a id="ref-smith"></a>Smith, A. (2021). Second.
"""
    result = prepare_citations(duplicate)
    assert result.citation_count == 0
    assert result.warnings


def test_citation_year_must_match_explicit_reference():
    text = '[Smith, 2021](#ref-smith)\n\n## References\n\n<a id="ref-smith"></a>Smith, A. (2020). Study.'
    result = prepare_citations(text)
    assert result.citation_count == 0
    assert any('date differs' in warning for warning in result.warnings)
