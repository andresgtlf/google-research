"""Model recommendations must not override an explicit research choice."""
from backend.main import ResearchRequest
from backend.providers import get_provider


def test_omitted_tier_uses_provider_recommendation():
    request = ResearchRequest(extract_job_id="example")
    assert request.tier is None
    gemini = get_provider(request.provider)
    assert gemini.default_model(request.tier) == "deep-research-max-preview-04-2026"
    assert gemini.info().recommended_tier == "max"
    for provider_id in ("openai", "claude"):
        provider = get_provider(provider_id)
        assert provider.default_model() == provider.default_model("fast")


def test_explicit_gemini_choices_are_preserved():
    gemini = get_provider("gemini")
    assert gemini.default_model("fast") == "deep-research-preview-04-2026"
    assert gemini.default_model("legacy") == "deep-research-pro-preview-12-2025"


def test_extraction_uses_configured_model_and_structured_pdf_input(monkeypatch):
    from types import SimpleNamespace
    from backend import extraction
    calls = []
    def generate_content(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("stop before generation")
    monkeypatch.setattr(extraction, "EXTRACTION_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(extraction.genai, "Client", lambda **kwargs: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)))
    import pytest
    with pytest.raises(RuntimeError, match="stop before generation"):
        extraction.extract_from_pdf(b"synthetic PDF")
    assert calls[0]["model"] == "gemini-3.8-flash"
    assert calls[0]["contents"][1].inline_data.mime_type == "application/pdf"
    assert calls[0]["config"].response_schema is extraction.Extraction
    assert calls[0]["config"].temperature == 0
