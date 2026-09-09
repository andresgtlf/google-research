"""GTLF Research API — FastAPI application.

Serves the JSON API under /api/* and the built React frontend (frontend/dist)
for everything else.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from .library import library
from .jobs import manager  # noqa: E402
from .providers import get_provider, list_providers  # noqa: E402

app = FastAPI(title="GTLF Research API", version="5.0")

# CORS for the Vite dev server; in production the frontend is same-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


# ── API models ─────────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    extract_job_id: str
    research_prompt: Optional[str] = None  # edited prompt (customized mode)
    provider: str = "gemini"
    model: Optional[str] = None
    tier: str = "fast"  # fast | max | legacy
    formats: list[str] = ["markdown", "pdf"]
    reuse_existing: bool = True


# ── Endpoints ──────────────────────────────────────────────────────


@app.get("/api/providers")
def providers() -> list[dict[str, Any]]:
    return [asdict(p) for p in list_providers()]


@app.post("/api/extract")
async def extract(request: Request, file: UploadFile = File(...), refresh: bool = Form(False)) -> dict[str, str]:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(400, "Please upload a PDF file")

    # Reject oversized uploads from the declared length before buffering the
    # whole body into memory.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds the 50 MB limit")

    pdf_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds the 50 MB limit")
    if not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(400, "File does not look like a valid PDF")
    job = manager.start_extract(pdf_bytes, file.filename or "upload.pdf", refresh=refresh)
    return {"job_id": job.id}


@app.post("/api/research")
def research(req: ResearchRequest) -> dict[str, str]:
    extract_job = manager.get(req.extract_job_id)
    if extract_job is None or extract_job.kind != "extract":
        raise HTTPException(404, "Extraction job not found")
    if extract_job.status != "completed":
        raise HTTPException(409, "Extraction has not completed yet")

    # Validate provider/model before starting the job
    try:
        provider = get_provider(req.provider)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if req.model and req.model not in [m.id for m in provider.models()]:
        raise HTTPException(400, f"Unknown model for {req.provider}: {req.model}")

    prompt = req.research_prompt or extract_job.result["research_prompt"]
    try:
        job = manager.start_research(
            extraction=extract_job.result["extraction"],
            research_prompt=prompt,
            provider_id=req.provider,
            model_id=req.model,
            tier=req.tier,
            formats=[f for f in req.formats if f in ("markdown", "pdf")],
            source_filename=extract_job.result.get("source_filename", ""),
            reuse_existing=req.reuse_existing,
            evidence_snapshot=extract_job.result.get("evidence_snapshot"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(
            404,
            "Job not found. The server may have restarted — please start again.",
        )
    return job.to_dict()


_FILE_KINDS = {
    "pdf": ("pdf", "application/pdf"),
    "md": ("markdown", "text/markdown"),
    "json": ("json", "application/json"),
}


@app.get("/api/jobs/{job_id}/files/{kind}")
def job_file(job_id: str, kind: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if kind not in _FILE_KINDS:
        raise HTTPException(400, f"Unknown file kind: {kind}")
    files = job.result.get("files", {})
    file_key, media_type = _FILE_KINDS[kind]
    name = files.get(file_key)
    if not name or not (job.dir / name).exists():
        raise HTTPException(404, f"No {kind} file for this job")
    org = (job.result.get("extraction") or {}).get("organization", "report")
    safe_org = "".join(c if c.isalnum() or c in "-_ " else "" for c in org).strip()
    download_name = f"{safe_org or 'report'}_research.{kind if kind != 'md' else 'md'}"
    return FileResponse(job.dir / name, media_type=media_type, filename=download_name)


@app.get("/api/library")
def research_library(q: str = Query("", max_length=200),
                     limit: int = Query(50, ge=1, le=100),
                     offset: int = Query(0, ge=0)):
    return library.list(q, limit, offset)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Frontend (built React bundle) ──────────────────────────────────

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    _DIST_ROOT = FRONTEND_DIST.resolve()

    @app.get("/{path:path}")
    def spa(path: str):
        # Starlette percent-decodes the path before it reaches us, so `..`
        # segments can arrive here as literal parent-directory components
        # (e.g. `/..%2fsecret`). Resolve and confine to the dist root before
        # serving anything, otherwise this is an arbitrary file read.
        if path:
            candidate = (_DIST_ROOT / path).resolve()
            if candidate.is_relative_to(_DIST_ROOT) and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(_DIST_ROOT / "index.html")
