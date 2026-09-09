from backend.citations import prepare_citations
from backend.reference_recovery import recover_references

ENTRY = "Attanasio, O., Kugler, A., & Meghir, C. (2011). Training. Journal, 3(3), 188–220. https://doi.org/10.1257/app.3.3.188"
TEXT = "## Conclusions\n\nSee [paper](https://doi.org/10.1257/app.3.3.188)."


def test_missing_references_recovered_with_bidirectional_links():
    text, entries = recover_references(TEXT, lookup=lambda doi: ENTRY)
    doc = prepare_citations(text)
    assert len(entries) == doc.reference_count == doc.citation_count == 1
    assert "Back to citation 1" in doc.markdown
    assert "https://doi.org/10.1257/app.3.3.188" in doc.markdown
    assert "Crossref" in doc.markdown
    assert not doc.warnings


def test_existing_reference_list_unchanged_without_lookup():
    text = TEXT + "\n\n## References\n\n" + ENTRY

    def unexpected(doi):
        raise AssertionError("must not lookup")

    assert recover_references(text, lookup=unexpected) == (text, [])


def test_unverified_or_failed_metadata_leaves_report_intact():
    assert recover_references(TEXT, lookup=lambda doi: "Unrelated metadata") == (
        TEXT,
        [],
    )

    def unavailable(doi):
        raise OSError("registry down")

    assert recover_references(TEXT, lookup=unavailable) == (TEXT, [])


def test_doi_as_markdown_label_does_not_swallow_link_destination():
    from backend.report_parse import extract_dois

    text = "[10.1257/app.3.3.188](https://doi.org/10.1257/app.3.3.188)"
    assert extract_dois(text) == ["10.1257/app.3.3.188"]
    recovered, _ = recover_references(text, lookup=lambda doi: ENTRY)
    assert prepare_citations(recovered).citation_count == 1
