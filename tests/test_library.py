import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.library import ResearchLibrary, fingerprint


@pytest.fixture
def archive(tmp_path):
    return ResearchLibrary(tmp_path / "library")


def sample_run(tmp_path):
    source = tmp_path / "jobs" / "abcdef123456"
    source.mkdir(parents=True)
    (source / "research.md").write_text("A preserved report")
    return source, {
        "id": "abcdef123456",
        "kind": "research",
        "status": "completed",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "provider": "gemini",
        "model": "test-model",
        "result": {
            "extraction": {"organization": "Synthetic Foundation", "country": "Kenya"},
            "run_fingerprint": "same-settings",
            "report_markdown": "A preserved report",
            "files": {"markdown": "research.md"},
        },
    }


def test_archive_survives_job_removal_and_new_process(tmp_path, archive):
    import shutil

    source, job = sample_run(tmp_path)
    archive.save(job, source)
    shutil.rmtree(source)
    reopened = ResearchLibrary(archive.root)
    assert reopened.get(job["id"]) == job
    assert reopened.list("kenya")[0]["id"] == job["id"]
    assert (
        archive.root / "runs" / job["id"] / "research.md"
    ).read_text() == "A preserved report"
    assert reopened.list("unrelated") == []


def test_reuse_requires_settings_and_requested_files(tmp_path, archive):
    source, job = sample_run(tmp_path)
    archive.save(job, source)
    assert archive.find("same-settings", ["markdown"])
    assert archive.find("different-settings", ["markdown"]) is None
    assert archive.find("same-settings", ["pdf"]) is None


def test_archive_rejects_path_traversal(archive):
    assert archive.get("../../.env") is None


def test_fingerprint_is_order_independent_and_content_sensitive():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert fingerprint({"prompt": "one"}) != fingerprint({"prompt": "two"})


def test_reaper_preserves_unarchived_reports(tmp_path, archive, monkeypatch):
    import backend.jobs as jobs

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "library", archive)
    manager = jobs.JobManager()
    job = jobs.Job("research")
    job.status = "completed"
    job.result = {"report_markdown": "valuable"}
    job.updated_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    manager._register(job)
    manager.reap_expired()
    assert manager.get(job.id) is job
    assert job.dir.exists()


def test_manager_reopens_archived_artifacts(tmp_path, archive, monkeypatch):
    import backend.jobs as jobs

    source, job = sample_run(tmp_path)
    archive.save(job, source)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "empty")
    monkeypatch.setattr(jobs, "library", archive)
    reopened = jobs.JobManager().get(job["id"])
    assert reopened.dir == archive.root / "runs" / job["id"]
    assert (reopened.dir / "research.md").is_file()


def test_export_preserves_access_checks_and_run_date(tmp_path):
    from backend.export import create_markdown_report

    path = tmp_path / "research.json"
    path.write_text(
        json.dumps(
            {
                "created_at": "2026-01-01",
                "result": "Evidence",
                "enrichment": {
                    "resolutions_markdown": "[Publisher](https://doi.org/10.1/example)",
                    "verification_markdown": "Citation status unknown",
                },
                "run_fingerprint": "stable",
                "protocol_version": "8.0",
            }
        )
    )
    content = create_markdown_report(path).read_text()
    assert "2026-01-01" in content
    assert "https://doi.org/10.1/example" in content
    assert "Citation status unknown" in content
    assert "stable" in content


def test_openalex_broad_queries_and_authentication(monkeypatch):
    from backend.evidence.openalex import OpenAlexSource
    from backend.evidence.base import EvidenceQuery

    monkeypatch.setenv("OPENALEX_API_KEY", "synthetic-test-key")
    source = OpenAlexSource()
    assert source._session.headers["Authorization"] == "Bearer synthetic-test-key"
    assert "issn" not in source._build_filters(
        EvidenceQuery(terms="vocational training")
    )
    assert "issn" in source._build_filters(
        EvidenceQuery(terms="training", venues=("World Development",))
    )


def test_unknown_access_is_not_called_paywalled():
    from backend.evidence.base import Candidate
    from backend.evidence.candidate_table import render_candidate

    assert "access unknown" in render_candidate(Candidate(title="Unknown"), 1)


def test_ranking_ties_ignore_source_response_order():
    from backend.evidence.base import Candidate
    from backend.evidence.ranking import rank
    from backend.schemas import Extraction

    a, b = Candidate(title="A", doi="10.1/a"), Candidate(title="B", doi="10.1/b")
    assert rank([a, b], Extraction()) == rank([b, a], Extraction())


def test_job_pipeline_archives_and_reuses_without_second_model_call(tmp_path, monkeypatch):
    import backend.jobs as jobs

    archive = ResearchLibrary(tmp_path / "library")
    monkeypatch.setattr(jobs, "library", archive)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("EVIDENCE_ENRICHMENT", "0")
    monkeypatch.setenv("RESEARCH_STRUCTURE_RETRY", "0")

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    class Provider:
        label = "Synthetic"
        calls = 0

        def available(self):
            return True

        def default_model(self, tier):
            return "synthetic-model"

        def run(self, *args, **kwargs):
            self.calls += 1
            return "## Conclusions\n\nSynthetic research."

    provider = Provider()
    monkeypatch.setattr(jobs.threading, "Thread", InlineThread)
    monkeypatch.setattr(jobs, "get_provider", lambda _: provider)
    manager = jobs.JobManager()
    args = dict(extraction={"organization": "Synthetic"}, research_prompt="fixed prompt",
                provider_id="test", model_id=None, tier="fast", formats=["markdown"])
    first = manager.start_research(**args)
    assert first.status == "completed"
    assert archive.get(first.id)
    second = manager.start_research(**args)
    assert second.id == first.id
    assert provider.calls == 1
    assert (second.dir / second.result["files"]["markdown"]).is_file()
    fresh = manager.start_research(**args, reuse_existing=False)
    assert fresh.id != first.id
    assert provider.calls == 2
    changed = manager.start_research(**{**args, "research_prompt": "different prompt"})
    assert changed.id not in {first.id, fresh.id}
    assert provider.calls == 3


def test_extraction_cache_avoids_reextracting_and_refresh_bypasses(tmp_path, monkeypatch):
    import backend.jobs as jobs
    from backend.schemas import Extraction

    monkeypatch.setattr(jobs, "library", ResearchLibrary(tmp_path / "library"))
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("EVIDENCE_SEEDING", "0")
    calls = []

    class InlineThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(jobs.threading, "Thread", InlineThread)
    monkeypatch.setattr(jobs, "extract_from_pdf", lambda content: calls.append(content) or Extraction(organization="Synthetic"))
    manager = jobs.JobManager()
    first = manager.start_extract(b"%PDF-synthetic", "first.pdf")
    second = manager.start_extract(b"%PDF-synthetic", "renamed.pdf")
    assert first.status == second.status == "completed"
    assert first.result["research_prompt"] == second.result["research_prompt"]
    assert second.result["source_filename"] == "renamed.pdf"
    assert len(calls) == 1
    manager.start_extract(b"%PDF-synthetic", "first.pdf", refresh=True)
    assert len(calls) == 2


def test_recall_evaluation_reports_missing_studies():
    from scripts.evaluate_recall import evaluate
    result = evaluate(["10.1234/a", "10.1234/b"], {
        "one": "https://doi.org/10.1234/a",
        "two": "10.1234/a and 10.1234/b",
    })
    assert result["runs"][0]["benchmark_recall"] == 0.5
    assert result["runs"][0]["missing_dois"] == ["10.1234/b"]
    assert result["overlap"][0]["jaccard"] == 0.5
