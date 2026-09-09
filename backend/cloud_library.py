"""Cloud Storage archive with an expendable local download cache.

A run's job.json is its commit marker: artifacts must upload successfully first.
Only completed research and extraction JSON are stored, never input PDFs or keys.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


class CloudResearchLibrary:
    def __init__(self, bucket_name: str, root: Path | None = None, *, client=None):
        from .library import ResearchLibrary

        self._local = ResearchLibrary(root)
        self.root = self._local.root
        self._lock = self._local._lock
        self.bucket_name = bucket_name
        self._client = client

    @property
    def bucket(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client.bucket(self.bucket_name)

    def _json(self, name):
        from google.api_core.exceptions import NotFound

        try:
            value = json.loads(self.bucket.blob(name).download_as_bytes(timeout=60))
            if not isinstance(value, dict):
                raise ValueError("Expected JSON object")
            return value
        except NotFound:
            return None
        except Exception as exc:
            raise OSError("Could not read research archive from Cloud Storage") from exc

    def _records(self):
        try:
            # Read only commit markers. Artifact downloads happen on opening a run.
            for blob in self.bucket.list_blobs(prefix="runs/", timeout=60):
                if re.fullmatch(r"runs/[a-f0-9]{12}/job.json", blob.name):
                    job = self._json(blob.name)
                    if job:
                        yield job
        except Exception as exc:
            raise OSError("Could not list research archive in Cloud Storage") from exc

    @staticmethod
    def _filenames(job):
        names = job.get("result", {}).get("files", {}).values()
        for name in names:
            if (
                not isinstance(name, str)
                or not name
                or Path(name).name != name
                or name in {".", "..", "job.json"}
            ):
                raise ValueError("Invalid artifact filename")
            yield name

    def save(self, job: dict, source: Path) -> None:
        if job.get("status") != "completed" or job.get("kind") != "research":
            return
        if not re.fullmatch(r"[a-f0-9]{12}", job["id"]):
            raise ValueError("Invalid run ID")
        from google.api_core.exceptions import PreconditionFailed

        with self._lock:
            try:
                for name in self._filenames(job):
                    blob = self.bucket.blob(f"runs/{job['id']}/{name}")
                    content = (source / name).read_bytes()
                    try:
                        blob.upload_from_string(
                            content, if_generation_match=0, timeout=60
                        )
                    except PreconditionFailed:
                        # An interrupted upload can be retried, but never overwrite
                        # another report under the same run ID.
                        if blob.download_as_bytes(timeout=60) != content:
                            raise OSError("Archive artifact conflict")
                marker = self.bucket.blob(f"runs/{job['id']}/job.json")
                payload = json.dumps(job, ensure_ascii=False).encode()
                try:
                    marker.upload_from_string(
                        payload,
                        content_type="application/json",
                        if_generation_match=0,
                        timeout=60,
                    )
                except PreconditionFailed:
                    existing = self._json(marker.name)
                    if existing.get("result") != job.get("result"):
                        raise OSError("Archive metadata conflict")
            except Exception as exc:
                raise OSError("Could not save research to Cloud Storage") from exc

    def get(self, run_id: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{12}", run_id):
            return None
        job = self._json(f"runs/{run_id}/job.json")
        if job is None:
            return None
        if job.get("id") != run_id:
            raise OSError("Archive run ID mismatch")
        with self._lock:
            target = self.root / "runs" / run_id
            target.mkdir(parents=True, exist_ok=True)
            try:
                for name in self._filenames(job):
                    path = target / name
                    if not path.is_file():
                        temporary = path.with_name(name + ".download")
                        self.bucket.blob(f"runs/{run_id}/{name}").download_to_filename(
                            str(temporary), timeout=60
                        )
                        temporary.replace(path)
                self._local._write(target / "job.json", job)
            except Exception as exc:
                raise OSError(
                    "Could not download archived report from Cloud Storage"
                ) from exc
        return job

    def list(self, query: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        return self._local._summaries(self._records(), query, limit, offset)

    def find(self, key: str, formats: list[str]) -> dict | None:
        matches = sorted(
            self._records(),
            key=lambda job: (job.get("created_at", ""), job["id"]),
            reverse=True,
        )
        for job in matches:
            result = job.get("result", {})
            if result.get("run_fingerprint") == key and all(
                fmt in result.get("files", {}) for fmt in formats
            ):
                return self.get(job["id"])
        return None

    def cached_extraction(self, key: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid extraction fingerprint")
        return self._json(f"extractions/{key}.json")

    def save_extraction(self, key: str, value: dict) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid extraction fingerprint")
        try:
            self.bucket.blob(f"extractions/{key}.json").upload_from_string(
                json.dumps(value, ensure_ascii=False),
                content_type="application/json",
                timeout=60,
            )
        except Exception as exc:
            raise OSError("Could not save extraction to Cloud Storage") from exc
