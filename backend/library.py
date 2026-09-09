"""Persistent research archive, independent of disposable job workspaces.

Use a persistent local/block volume for LIBRARY_DIR and back it up. This is a
single-server store, not a distributed queue or a shared multi-tenant database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "8.0"


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class ResearchLibrary:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get("LIBRARY_DIR", "data/library"))
        self._lock = threading.RLock()

    def save(self, job: dict, source: Path) -> None:
        """Publish metadata last so readers never see a partially copied run."""
        if job.get("status") != "completed" or job.get("kind") != "research":
            return
        with self._lock:
            target = self.root / "runs" / job["id"]
            target.mkdir(parents=True, exist_ok=True)
            for name in job.get("result", {}).get("files", {}).values():
                if Path(name).name != name:
                    raise ValueError("Invalid artifact filename")
                if (source / name).is_file():
                    shutil.copy2(source / name, target / name)
            self._write(target / "job.json", job)

    def get(self, run_id: str) -> dict | None:
        if not re.fullmatch(r"[a-f0-9]{12}", run_id):
            return None
        return self._read(self.root / "runs" / run_id / "job.json")

    def list(self, query: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
        rows = []
        for path in (self.root / "runs").glob("*/job.json"):
            job = self._read(path)
            if not job:
                continue
            extraction = job.get("result", {}).get("extraction", {})
            row = {
                "id": job["id"],
                "created_at": job["created_at"],
                "provider": job.get("provider"),
                "model": job.get("model"),
                "organization": extraction.get("organization", ""),
                "project_title": extraction.get("project_title", ""),
                "country": extraction.get("country", ""),
            }
            if query.casefold() in " ".join(str(v) for v in row.values()).casefold():
                rows.append(row)
        rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
        return rows[offset : offset + limit]

    def find(self, key: str, formats: list[str]) -> dict | None:
        for path in sorted(
            (self.root / "runs").glob("*/job.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            job = self._read(path)
            result = (job or {}).get("result", {})
            if result.get("run_fingerprint") != key:
                continue
            if all(
                (
                    path.parent / result.get("files", {}).get(fmt, "__missing__")
                ).is_file()
                for fmt in formats
            ):
                return job
        return None

    def cached_extraction(self, key: str) -> dict | None:
        return self._read(self.root / "extractions" / f"{key}.json")

    def save_extraction(self, key: str, value: dict) -> None:
        with self._lock:
            self._write(self.root / "extractions" / f"{key}.json", value)

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)


library = ResearchLibrary()
