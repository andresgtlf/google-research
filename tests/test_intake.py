from io import BytesIO
from zipfile import ZipFile
import pytest
from backend.documents import docx_text, validate_document
from backend.schemas import Extraction, IntakeImpact
from backend.research_prompt import build_research_prompt


def word(text):
    b = BytesIO()
    with ZipFile(b, "w") as z:
        z.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + text
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    return b.getvalue()


def test_docx_reads_questions_and_answers_without_executing_instructions():
    payload = word(
        "Impact Modeling Intake Survey: NextLadder Ventures. Potential Investee: Synthetic. Reach: 100 households."
    )
    assert validate_document(payload, "survey.docx") == "docx"
    assert "100 households" in docx_text(payload)
    with pytest.raises(ValueError):
        validate_document(b"not a document", "survey.docx")
    with pytest.raises(ValueError):
        validate_document(b"%PDF", "survey.exe")


def test_xml_entities_and_empty_word_are_rejected():
    b = BytesIO()
    with ZipFile(b, "w") as z:
        z.writestr(
            "word/document.xml", '<!DOCTYPE foo [<!ENTITY data "secret">]><foo/>'
        )
    with pytest.raises(ValueError):
        docx_text(b.getvalue())
    with pytest.raises(ValueError):
        docx_text(word(""))


def test_intake_protocol_retains_channels_investment_and_uncertainty():
    e = Extraction(
        source_format="next_ladder_intake",
        organization="Synthetic",
        intake=IntakeImpact(
            financial_impact_channels=["Debt relief"],
            total_raise="$1m total round",
            assumptions_and_gaps=["Unknown actual repayment counterfactual"],
        ),
    )
    p = build_research_prompt(e)
    assert "Next Ladder" in p
    assert "$1m total round" in p and "Unknown actual repayment counterfactual" in p
    assert "not universally" in " ".join(p.split()) and "hypothetical interest" in p
    assert "## Model Input Implications" in p and "## References" in p
    assert "scan on INCOME EFFECTS" not in p
    assert "scan on INCOME EFFECTS" in build_research_prompt(
        Extraction(source_format="concept_note")
    )


def test_format_choice_is_part_of_extraction_cache_and_unknown_needs_review(
    tmp_path, monkeypatch
):
    import backend.jobs as jobs
    from backend.library import ResearchLibrary

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "library", ResearchLibrary(tmp_path / "library"))
    monkeypatch.setenv("EVIDENCE_SEEDING", "0")

    class InlineThread:
        def __init__(self, target, **kw):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(jobs.threading, "Thread", InlineThread)
    calls = []

    def extract(content, document_format="auto"):
        calls.append(document_format)
        return Extraction(organization="Synthetic")

    monkeypatch.setattr(jobs, "extract_from_pdf", extract)
    m = jobs.JobManager()
    first = m.start_extract(b"%PDF-synthetic", "input.pdf")
    assert first.result["requires_format_review"]
    m.start_extract(b"%PDF-synthetic", "renamed.pdf")
    chosen = m.start_extract(
        b"%PDF-synthetic", "input.pdf", document_format="next_ladder_intake"
    )
    assert chosen.result["extraction"]["source_format"] == "next_ladder_intake"
    assert not chosen.result["requires_format_review"]
    assert calls == ["auto", "next_ladder_intake"]
    assert "Next Ladder" in chosen.result["research_prompt"]


def test_docx_extraction_routes_to_text_model(monkeypatch):
    from backend import extraction
    from types import SimpleNamespace

    captured = []

    def generate_content(**kw):
        captured.append(kw)
        return SimpleNamespace(
            parsed=Extraction(
                source_format="next_ladder_intake", format_confidence="high"
            )
        )

    monkeypatch.setattr(
        extraction.genai,
        "Client",
        lambda **kw: SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        ),
    )
    e = extraction.extract_from_docx(
        word("Impact Modeling Intake Survey"), "next_ladder_intake"
    )
    assert e.source_format == "next_ladder_intake"
    assert "DOCUMENT CONTENT" in captured[0]["contents"][1]
    assert "User-selected format: next_ladder_intake" in captured[0]["contents"][0]


def test_api_accepts_docx_and_validates_format(monkeypatch):
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    import backend.main as main

    calls = []

    def start(content, filename, **kwargs):
        calls.append((filename, kwargs))
        return SimpleNamespace(id="abcdef123456")

    monkeypatch.setattr(main.manager, "start_extract", start)
    client = TestClient(main.app)
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = client.post(
        "/api/extract",
        files={"file": ("intake.docx", word("Synthetic survey"), mime)},
        data={"document_format": "next_ladder_intake"},
    )
    assert response.status_code == 200
    assert calls[0][1]["document_format"] == "next_ladder_intake"
    assert (
        client.post(
            "/api/extract",
            files={"file": ("a.pdf", b"%PDF", "application/pdf")},
            data={"document_format": "invalid"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/extract", files={"file": ("bad.docx", b"bad", mime)}
        ).status_code
        == 400
    )


def test_word_text_limit_is_enforced(monkeypatch):
    import backend.documents as documents

    monkeypatch.setattr(documents, "MAX_XML_BYTES", 10)
    with pytest.raises(ValueError, match="20 MB"):
        documents.docx_text(word("text"))


def test_intake_query_builder_includes_financial_channels():
    from backend.evidence.queries import build_queries
    e = Extraction(source_format="next_ladder_intake", country="United States",
                   summary="Benefits navigation and debt relief")
    queries = build_queries(e)
    assert queries
    assert any("benefits enrollment" in q.terms for q in queries)
    assert any("debt relief" in q.terms for q in queries)
    assert queries[0].label == "Next Ladder intake financial-impact channel"
