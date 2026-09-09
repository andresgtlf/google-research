import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from backend.cloud_library import CloudResearchLibrary
from backend.library import fingerprint


class Blob:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def upload_from_string(self, content, **kwargs):
        if kwargs.get("if_generation_match") == 0 and self.name in self.store:
            raise PreconditionFailed("already exists")
        self.store[self.name] = (
            content.encode() if isinstance(content, str) else content
        )

    def download_as_bytes(self, **kwargs):
        if self.name not in self.store:
            raise NotFound("missing")
        return self.store[self.name]

    def download_to_filename(self, path, **kwargs):
        Path(path).write_bytes(self.download_as_bytes())


@pytest.fixture
def cloud(tmp_path):
    store = {}
    bucket = SimpleNamespace(
        blob=lambda name: Blob(store, name),
        list_blobs=lambda **kw: [
            Blob(store, name) for name in store if name.startswith(kw["prefix"])
        ],
    )
    client = SimpleNamespace(bucket=lambda name: bucket)
    return CloudResearchLibrary("test-bucket", tmp_path / "cache", client=client), store


def sample(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "research.md").write_text("Synthetic report")
    return source, {
        "id": "abcdef123456",
        "kind": "research",
        "status": "completed",
        "created_at": "2026-09-09",
        "result": {
            "files": {"markdown": "research.md"},
            "run_fingerprint": "same",
            "extraction": {"country": "Kenya"},
        },
    }


def test_cloud_recovers_after_all_local_files_are_lost(cloud, tmp_path):
    archive, store = cloud
    source, job = sample(tmp_path)
    archive.save(job, source)
    assert list(store)[-1] == "runs/abcdef123456/job.json"
    reopened = CloudResearchLibrary(
        "test-bucket", tmp_path / "fresh-cache", client=archive._client
    )
    assert reopened.list("kenya")[0]["id"] == job["id"]
    assert reopened.find("other", ["markdown"]) is None
    assert reopened.find("same", ["pdf"]) is None
    assert reopened.find("same", ["markdown"]) == job
    assert (
        reopened.root / "runs" / job["id"] / "research.md"
    ).read_text() == "Synthetic report"


def test_partial_upload_is_not_listed_and_can_retry(cloud, tmp_path):
    archive, store = cloud
    source, job = sample(tmp_path)
    job["result"]["files"]["pdf"] = "missing.pdf"
    with pytest.raises(OSError):
        archive.save(job, source)
    assert archive.list() == []
    (source / "missing.pdf").write_bytes(b"synthetic")
    archive.save(job, source)
    assert len(archive.list()) == 1


def test_conflicting_run_does_not_overwrite_archived_content(cloud, tmp_path):
    archive, store = cloud
    source, job = sample(tmp_path)
    archive.save(job, source)
    (source / "research.md").write_text("Different report")
    with pytest.raises(OSError):
        archive.save(job, source)
    assert store["runs/abcdef123456/research.md"] == b"Synthetic report"


def test_extraction_reuse_survives_new_cache(cloud, tmp_path):
    archive, _ = cloud
    key = fingerprint({"input": "synthetic"})
    assert archive.cached_extraction(key) is None
    archive.save_extraction(key, {"prompt": "Synthetic"})
    reopened = CloudResearchLibrary(
        "test-bucket", tmp_path / "new", client=archive._client
    )
    assert reopened.cached_extraction(key) == {"prompt": "Synthetic"}


def test_path_traversal_rejected(cloud, tmp_path):
    archive, store = cloud
    assert archive.get("../../secret") is None
    source, job = sample(tmp_path)
    job["result"]["files"]["markdown"] = "../secret"
    with pytest.raises(OSError):
        archive.save(job, source)
    assert store == {}


def test_cloud_outage_is_not_a_cache_miss(cloud):
    archive, store = cloud
    store["runs/abcdef123456/job.json"] = b"corrupted"
    with pytest.raises(OSError):
        archive.get("abcdef123456")


def test_reaper_preserves_report_during_cloud_outage(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import backend.jobs as jobs

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")

    def unavailable(*args):
        raise OSError("cloud unavailable")

    monkeypatch.setattr(jobs, "library", SimpleNamespace(get=unavailable))
    manager = jobs.JobManager()
    job = jobs.Job("research")
    job.status = "completed"
    job.result = {"report_markdown": "keep"}
    job.updated_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    manager._register(job)
    manager.reap_expired()
    assert job.dir.exists()
    assert manager.get(job.id) is job


def test_configured_bucket_uses_cloud_adapter_without_connecting(monkeypatch):
    from backend.library import configured_library
    monkeypatch.setenv("LIBRARY_GCS_BUCKET", "synthetic-bucket")
    archive = configured_library()
    assert isinstance(archive, CloudResearchLibrary)
    assert archive.bucket_name == "synthetic-bucket"
    assert archive._client is None


def test_storage_outage_returns_actionable_http_error(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.main as main
    def unavailable(*args):
        raise OSError("internal credential detail")
    monkeypatch.setattr(main, "library", SimpleNamespace(list=unavailable))
    response = TestClient(main.app).get("/api/library")
    assert response.status_code == 503
    assert "Research storage is unavailable" in response.json()["detail"]
    assert "credential" not in response.text
