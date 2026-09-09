"""Background job manager with disk persistence.

Jobs run in daemon threads and persist their state to {JOBS_DIR}/{id}/job.json
after every update, so the frontend can poll (and the page can be refreshed)
without killing a running research task — the main fragility of the v2
Streamlit app.

Persisted state is also reloaded on startup, so a redeploy or crash no longer
makes every job on disk permanently unreachable through the API. Jobs that
were mid-flight when the process died are reconciled to "interrupted" rather
than left reporting "running" forever, because their worker thread is gone.

Scope limit worth knowing: job state lives in this process plus the local
disk, so it is correct for a single serving instance. Running more than one
Cloud Run instance without a shared store means a poll can land on an
instance that has never seen the job. See README for the required deploy
flags.
"""

import json
import hashlib
from dataclasses import asdict
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .export import export_research_report
from .extraction import extract_from_pdf, EXTRACTION_MODEL
from .prompts import EXTRACTION_PROMPT
from .library import library, fingerprint, PROTOCOL_VERSION
from .providers import get_provider
from .evidence.status import openalex_status
from .evidence.pipeline import (
    enrich_report,
    enrichment_enabled,
    seed_candidates,
    seeding_enabled,
    summarize_enrichment,
)
from .report_parse import (
    missing_headings,
    parse_report_sections,
    present_headings,
    structural_completeness,
)
from .research_prompt import build_research_prompt

log = logging.getLogger(__name__)

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "jobs"))

# Job artifacts (a 50 MB input PDF, the report, the PDF export) are never
# revisited after a review is finished, and on Cloud Run /tmp is RAM. Without
# a reaper the instance the README tells you to keep warm is the one that
# slowly runs out of memory.
JOB_TTL_HOURS = int(os.environ.get("JOB_TTL_HOURS", "24"))

ACTIVE_STATUSES = ("queued", "running")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age_hours(iso_ts: str) -> float:
    try:
        then = datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0


class Job:
    def __init__(self, kind: str, job_id: Optional[str] = None):
        self.id = job_id or uuid.uuid4().hex[:12]
        self.kind = kind  # "extract" | "research"
        self.status = "queued"  # queued | running | completed | failed | interrupted
        self.created_at = _now()
        self.updated_at = self.created_at
        self.events: list[dict[str, str]] = []
        self.error: Optional[str] = None
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self.remote_id: Optional[str] = None
        self.result: dict[str, Any] = {}
        self.evidence_status: dict[str, Any] = {}
        self.dir = JOBS_DIR / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── Restoring from disk ────────────────────────────────────────

    @classmethod
    def restore(cls, data: dict[str, Any]) -> "Job":
        """Rebuild a Job from its persisted job.json."""
        job = cls.__new__(cls)
        job.id = data["id"]
        job.kind = data.get("kind", "research")
        job.status = data.get("status", "failed")
        job.created_at = data.get("created_at") or _now()
        job.updated_at = data.get("updated_at") or job.created_at
        job.events = list(data.get("events") or [])
        job.error = data.get("error")
        job.provider = data.get("provider")
        job.model = data.get("model")
        job.remote_id = data.get("remote_id")
        job.result = data.get("result") or {}
        job.evidence_status = data.get("evidence_status") or {}
        job.dir = JOBS_DIR / job.id
        job._lock = threading.Lock()

        # The thread that was driving this job died with the old process.
        if job.status in ACTIVE_STATUSES:
            job.status = "interrupted"
            note = "The server restarted while this job was running."
            if job.remote_id:
                note += f" The provider task id was {job.remote_id}."
            job.error = note
            job.events.append({"time": _now(), "message": note})
            job.updated_at = _now()
            job._save_locked()
        return job

    # ── State updates ──────────────────────────────────────────────

    def add_event(self, message: str, remote_id: Optional[str] = None):
        with self._lock:
            self.events.append({"time": _now(), "message": message})
            if remote_id:
                self.remote_id = remote_id
            self.updated_at = _now()
            self._save_locked()

    def set_status(self, status: str, error: Optional[str] = None):
        with self._lock:
            self.status = status
            self.error = error
            self.updated_at = _now()
            self._save_locked()

    def set_evidence_status(self, status: dict[str, Any]):
        with self._lock:
            self.evidence_status = status
            self.updated_at = _now()
            self._save_locked()

    def set_result(self, result: dict[str, Any]):
        with self._lock:
            self.result = result
            self.updated_at = _now()
            self._save_locked()

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
            "error": self.error,
            "provider": self.provider,
            "model": self.model,
            "remote_id": self.remote_id,
            "result": self.result,
            "evidence_status": self.evidence_status,
        }

    def _save_locked(self):
        """Persist state. Never raises: a failed write must not break the job.

        In particular the failure path calls add_event() then set_status(
        "failed"). If the write raised, set_status would never run and the job
        would be stuck reporting "running" with a dead thread.
        """
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / "job.json.tmp"
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))
            tmp.replace(self.dir / "job.json")
        except OSError:
            log.exception("Could not persist job %s state to disk", self.id)


# Below this fraction of the mandatory headings, a report is treated as a
# failed generation rather than a bad one. 0.5 sits between the two runs of
# 2026-08-01: the usable report carried 4/7 (0.57) and the collapsed one 1/7
# (0.14), which shipped to a reviewer with no conclusions and no evidence
# table. See `notes/incident-2026-08-01/`.
STRUCTURE_RETRY_THRESHOLD = 0.5

_STRUCTURE_RETRY_ENV = "RESEARCH_STRUCTURE_RETRY"


def _structure_retry_enabled() -> bool:
    return os.environ.get(_STRUCTURE_RETRY_ENV, "1").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _retry_if_structurally_broken(
    report_md: str, *, provider, prompt: str, model: str, job: "Job"
) -> str:
    """Re-ask the provider ONCE when the first report ignored the structure.

    The protocol has said "EVERY heading below is required" since a94469b, and
    a run on 2026-08-01 returned 1 of 7 headings anyway — no Conclusions, no
    Evidence Digest — from a prompt byte-identical to one that had produced a
    usable report 70 minutes earlier. Prompt wording cannot fix a sampling
    failure; asking again can.

    Two rules make this safe, both from the v6 lesson that an expensive result
    must never be lost:

    - Exactly one retry, never a loop. A second full run costs real money and
      up to 75 minutes.
    - The retry can only ever improve matters. Any failure in the second call
      is swallowed and the original report returned, and the replacement is
      kept only if it is structurally better than what we already had.
    """
    if not _structure_retry_enabled():
        return report_md

    completeness = structural_completeness(report_md)
    if completeness >= STRUCTURE_RETRY_THRESHOLD:
        return report_md

    absent = missing_headings(report_md)
    job.add_event(
        f"Report is missing {len(absent)} of 7 required sections "
        f"({', '.join(absent)}). Asking the provider once more — the first "
        f"report is kept if the retry does not come back better."
    )

    corrective = (
        f"{prompt}\n\n"
        "IMPORTANT — a previous attempt at this exact task returned an "
        "incomplete report that omitted these required sections: "
        f"{', '.join(absent)}.\n"
        "Every heading in the MANDATORY OUTPUT STRUCTURE section is required "
        "and must appear verbatim, even where the section is empty — write "
        "'None identified' under a heading rather than omitting it."
    )

    try:
        retry_md = provider.run(corrective, model, on_event=job.add_event)
    except Exception:
        log.exception("Structure retry failed for job %s; keeping first report", job.id)
        job.add_event(
            "The retry did not complete. Keeping the first report — it is "
            "incomplete, so read it with that in mind."
        )
        return report_md

    if structural_completeness(retry_md) > completeness:
        job.add_event(
            f"Retry returned a more complete report "
            f"({len(present_headings(retry_md))} of 7 sections). Using it."
        )
        return retry_md

    job.add_event(
        "Retry was no more complete than the first report. Keeping the "
        "original."
    )
    return report_md


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._load_from_disk()

    # ── Startup recovery and cleanup ───────────────────────────────

    def _load_from_disk(self):
        """Rehydrate persisted jobs so a restart doesn't orphan them."""
        if not JOBS_DIR.exists():
            return
        restored = 0
        for job_json in sorted(JOBS_DIR.glob("*/job.json")):
            try:
                data = json.loads(job_json.read_text())
                job = Job.restore(data)
            except Exception:
                log.exception("Skipping unreadable job file %s", job_json)
                continue
            self._jobs[job.id] = job
            if job.kind == "research" and job.status == "completed" and not library.get(job.id):
                try:
                    library.save(job.to_dict(), job.dir)
                except OSError:
                    log.exception("Could not archive existing research %s", job.id)
            restored += 1
        if restored:
            log.info("Restored %d job(s) from %s", restored, JOBS_DIR)
        self.reap_expired()

    def reap_expired(self):
        """Delete job directories and in-memory state past the TTL."""
        if JOB_TTL_HOURS <= 0:
            return
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status not in ACTIVE_STATUSES
                and _age_hours(job.updated_at) > JOB_TTL_HOURS
                and (job.kind != "research" or not job.result.get("report_markdown")
                     or library.get(job.id) is not None)
            ]
            for job_id in expired:
                self._jobs.pop(job_id, None)
        for job_id in expired:
            shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
        # Job directories with no in-memory counterpart (unreadable job.json,
        # or written by an older revision) still occupy the disk. Only ever
        # remove directories that are recognisably ours: this path deletes
        # recursively, so an unrecognised directory is left alone.
        if JOBS_DIR.exists():
            for path in JOBS_DIR.iterdir():
                if not path.is_dir() or path.name in self._jobs:
                    continue
                if not (path / "job.json").exists():
                    continue
                try:
                    age = (time.time() - path.stat().st_mtime) / 3600.0
                except OSError:
                    continue
                if age > JOB_TTL_HOURS:
                    shutil.rmtree(path, ignore_errors=True)
        if expired:
            log.info("Reaped %d expired job(s)", len(expired))

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        saved = library.get(job_id)
        if saved:
            job = Job.restore(saved)
            job.dir = library.root / "runs" / job.id
            return job
        return None

    def _register(self, job: Job):
        with self._lock:
            self._jobs[job.id] = job

    # ── Extraction job ─────────────────────────────────────────────

    def start_extract(self, pdf_bytes: bytes, filename: str, refresh: bool = False) -> Job:
        self.reap_expired()
        job = Job("extract")
        job.set_evidence_status({"state": "waiting" if seeding_enabled() else "disabled",
                                 "message": "OpenAlex will search for papers after the concept note is read."
                                 if seeding_enabled() else "OpenAlex candidate search is disabled for this run."})
        self._register(job)
        (job.dir / "input.pdf").write_bytes(pdf_bytes)

        def work():
            try:
                job.set_status("running")
                job.add_event(f"Reading {filename} and extracting structured fields")
                source_hash = hashlib.sha256(pdf_bytes).hexdigest()
                cache_key = fingerprint({"pdf": source_hash, "protocol": PROTOCOL_VERSION,
                                         "model": EXTRACTION_MODEL, "prompt": EXTRACTION_PROMPT,
                                         "seeding": seeding_enabled()})
                cached = None if refresh else library.cached_extraction(cache_key)
                if cached:
                    cached["source_filename"] = filename
                    if seeding_enabled():
                        job.set_evidence_status(openalex_status(cached.get("evidence_snapshot"), reused=True))
                    job.set_result(cached)
                    job.add_event("Reused saved extraction and evidence snapshot; select fresh search to update")
                    job.set_status("completed")
                    return
                extraction = extract_from_pdf(pdf_bytes)
                job.add_event(
                    f"Extracted: {extraction.organization or 'unknown org'}"
                    + (f" ({extraction.country})" if extraction.country else "")
                )

                # Optional and never load-bearing: seeding only
                # accelerates the agent's own search. seed_candidates() returns
                # None when disabled or unusable, which makes the prompt builder
                # emit the unmodified protocol.
                retrieval = None
                if seeding_enabled():
                    job.set_evidence_status({"state": "searching", "message": "Connecting to OpenAlex and searching for relevant papers. Other evidence sources run alongside it."})
                    job.add_event("Searching OpenAlex and Economics Literature Search for candidate studies")
                    retrieval = seed_candidates(extraction)
                    job.set_evidence_status(openalex_status(asdict(retrieval) if retrieval else None))
                    job.add_event("OpenAlex: " + job.evidence_status["message"])
                    if retrieval is not None and retrieval.usable:
                        job.add_event(
                            f"{len(retrieval.candidates)} candidate studies "
                            f"retrieved from {', '.join(retrieval.sources_ok)} "
                            f"({retrieval.total_seen} raw results screened)"
                        )
                    else:
                        job.add_event(
                            "No candidates retrieved — the agent will run the "
                            "full search protocol unaided"
                        )

                prompt = build_research_prompt(extraction, retrieval)
                job.add_event("Research protocol assembled from template")
                result = {
                    "extraction": extraction.model_dump(),
                    "research_prompt": prompt,
                    "source_filename": filename,
                    "source_sha256": source_hash,
                    "protocol_version": PROTOCOL_VERSION,
                    "evidence_snapshot": asdict(retrieval) if retrieval else None,
                }
                (job.dir / "extraction.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2)
                )
                job.set_result(result)
                try:
                    library.save_extraction(cache_key, result)
                except OSError:
                    job.add_event("Could not save extraction for reuse")
                job.set_status("completed")
            except Exception as exc:  # surfaced to the user via the API
                log.exception("Extraction job %s failed", job.id)
                _fail(job, f"Extraction failed: {exc}", exc)
            finally:
                # The input PDF is only needed during extraction.
                _unlink_quietly(job.dir / "input.pdf")

        threading.Thread(target=work, daemon=True).start()
        return job

    # ── Research job ───────────────────────────────────────────────

    def start_research(
        self,
        extraction: dict[str, Any],
        research_prompt: str,
        provider_id: str,
        model_id: Optional[str],
        tier: str,
        formats: list[str],
        source_filename: str = "",
        reuse_existing: bool = True,
        evidence_snapshot: Optional[dict] = None,
        evidence_status: Optional[dict] = None,
    ) -> Job:
        provider = get_provider(provider_id)
        if not provider.available():
            raise ValueError(
                f"{provider.label} is not configured — set {provider.env_key} "
                f"(see API_KEYS.md)"
            )
        resolved_model = model_id or provider.default_model(tier)

        run_key = fingerprint({"extraction": extraction, "prompt": research_prompt,
                               "provider": provider_id, "model": resolved_model,
                               "protocol": PROTOCOL_VERSION,
                               "enrichment": enrichment_enabled()})
        if reuse_existing:
            saved = library.find(run_key, formats)
            if saved:
                restored = Job.restore(saved)
                restored.dir = library.root / "runs" / restored.id
                return restored
        self.reap_expired()
        job = Job("research")
        job.provider = provider_id
        job.model = resolved_model
        job.set_evidence_status(evidence_status or openalex_status(evidence_snapshot))
        self._register(job)

        def work():
            try:
                job.set_status("running")
                report_md = provider.run(
                    research_prompt,
                    resolved_model,
                    on_event=job.add_event,
                )
                # Keep the first paid result before a potential long retry.
                (job.dir / "initial-report.md").write_text(report_md, encoding="utf-8")
                report_md = _retry_if_structurally_broken(
                    report_md,
                    provider=provider,
                    prompt=research_prompt,
                    model=resolved_model,
                    job=job,
                )

                # Persist the report before anything else can fail. Everything
                # after this point is presentation, and a formatting error
                # must never discard a research run that took 20 minutes and
                # real money to produce.
                research_data = {
                    "provider": provider_id,
                    "model": resolved_model,
                    "extraction": extraction,
                    "research_prompt": research_prompt,
                    "source_filename": source_filename,
                    "created_at": job.created_at,
                    "protocol_version": PROTOCOL_VERSION,
                    "run_fingerprint": run_key,
                    "evidence_snapshot": evidence_snapshot,
                    "evidence_status": job.evidence_status,
                    "result": report_md,
                }
                research_json_path = job.dir / "research.json"
                research_json_path.write_text(
                    json.dumps(research_data, ensure_ascii=False, indent=2)
                )
                files: dict[str, str] = {"json": research_json_path.name}
                job.set_result(
                    {
                        "report_markdown": report_md,
                        "run_fingerprint": run_key,
                        "protocol_version": PROTOCOL_VERSION,
                        "sections": {},
                        "files": dict(files),
                        "extraction": extraction,
                    }
                )

                job.add_event("Parsing report sections")
                try:
                    sections = parse_report_sections(report_md)
                except Exception as exc:
                    log.exception("Section parsing failed for job %s", job.id)
                    job.add_event(
                        f"Could not parse report sections, showing the full "
                        f"report instead: {exc}"
                    )
                    sections = {
                        "evidence_table": None,
                        "conclusions": "",
                        "paywalled": "",
                        "parse_warnings": [
                            "Report sections could not be parsed. "
                            "The full report is shown below."
                        ],
                    }
                for warning in sections.get("parse_warnings") or []:
                    job.add_event(warning)

                # Post-research enrichment. Runs only after the report is on
                # disk and published to the job result, and cannot raise, so a
                # 75-minute run can never be lost to it. On failure the report
                # displays exactly as the agent wrote it.
                if enrichment_enabled():
                    job.add_event("Checking paywalled papers and cited DOIs with OpenAlex and Economics Literature Search")
                    source_status = dict(job.evidence_status)
                    job.set_evidence_status({**source_status, "activity": "Checking access links and cited DOIs with OpenAlex"})
                    try:
                        enrichment = enrich_report(report_md)
                    finally:
                        job.set_evidence_status(source_status)
                    sections["enrichment"] = enrichment
                    for event in summarize_enrichment(enrichment):
                        job.add_event(event)

                research_data["enrichment"] = sections.get("enrichment", {})
                research_json_path.write_text(json.dumps(research_data, ensure_ascii=False, indent=2))
                if formats:
                    job.add_event("Generating report files")
                    exported = export_research_report(
                        research_json_path,
                        job.dir,
                        formats,
                        on_warning=job.add_event,
                    )
                    for fmt, path in exported.items():
                        files[fmt] = path.name
                    job.add_event("Reports ready")

                job.set_result(
                    {
                        "report_markdown": report_md,
                        "run_fingerprint": run_key,
                        "protocol_version": PROTOCOL_VERSION,
                        "sections": sections,
                        "files": files,
                        "extraction": extraction,
                    }
                )
                job.set_status("completed")
                try:
                    library.save(job.to_dict(), job.dir)
                    job.add_event("Saved to research library")
                except OSError:
                    job.add_event("Library save failed; download the report before job expiry")
            except Exception as exc:
                log.exception("Research job %s failed", job.id)
                _fail(job, f"Research failed: {exc}", exc)

        threading.Thread(target=work, daemon=True).start()
        return job


def _fail(job: Job, message: str, exc: BaseException):
    """Mark a job failed, tolerating failures in the failure path itself."""
    try:
        job.add_event(message)
    except Exception:
        log.exception("Could not record failure event for job %s", job.id)
    try:
        job.set_status("failed", error=str(exc))
    except Exception:
        log.exception("Could not mark job %s failed", job.id)


def _unlink_quietly(path: Path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Could not remove %s", path)


manager = JobManager()
