# GitLab Foundation Research

Literature reviews for concept-note assessment, with Gemini, OpenAI or Claude
research providers. Upload a PDF, review the extracted research question and
protocol, then read and download the evidence report.

## What the application does

- Extracts structured intervention, population, geography and income-mechanism
  information from concept notes using Gemini.
- Retrieves candidate studies from OpenAlex and Economics Literature Search,
  deduplicates versions, ranks evidence and records queries and source failures.
- Uses a versioned protocol to screen causal income evidence, persistence,
  null/negative effects and the concept note's claimed mechanism.
- Keeps publisher/DOI links for inaccessible papers and looks for free versions.
  Unknown access is distinguished from confirmed closed access.
- Saves research and evidence snapshots in a searchable library. Identical inputs
  and settings can reuse the original report; **Run a fresh search** bypasses reuse.
- Exports Markdown, PDF and JSON with report provenance and access checks.

A fixed prompt cannot make fresh AI research deterministic. Reopening a saved
run preserves its exact evidence and text. Fresh runs require quality evaluation;
see [research quality and retention](docs/research-quality.md).

## Development

Prerequisites: Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js 22+.

```bash
cp .env.example .env
# Set GOOGLE_API_KEY. Add OPENAI_API_KEY / ANTHROPIC_API_KEY as needed.
# Set OPENALEX_API_KEY for a larger authenticated search budget.
uv sync --locked
uv run uvicorn backend.main:app --port 8000 --reload
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [the local application](http://localhost:5173). Vite proxies `/api` to
FastAPI. For a single server, run `npm run build` in `frontend/` and restart
FastAPI to serve the built application at port 8000.

PDF generation requires WeasyPrint's system libraries:

```bash
# macOS
brew install pango gdk-pixbuf libffi
# Debian/Ubuntu
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0
```

If the checkout lives in Google Drive, keep the virtual environment outside it:
`export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/gtlf-research"`. Install frontend
dependencies locally; Drive does not preserve the required executable symlinks.

## Configuration

| Variable | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini extraction and research |
| `OPENAI_API_KEY` | OpenAI research |
| `ANTHROPIC_API_KEY` | Claude web-search research |
| `OPENALEX_API_KEY` | Optional authenticated scholarly search |
| `OPENALEX_MAILTO` | Optional contact email for OpenAlex requests |
| `EVIDENCE_SEEDING` | `1` by default; `0` disables pre-research candidate retrieval |
| `EVIDENCE_ENRICHMENT` | `1` by default; checks access and cited DOIs after synthesis |
| `LIBRARY_DIR` | Persistent research archive; default `data/library` |
| `JOBS_DIR` | Disposable working files; default `jobs` |
| `JOB_TTL_HOURS` | Disposable job retention; default `24`; `0` disables expiry |
| `RESEARCH_STRUCTURE_RETRY` | One retry for severely incomplete reports; default `1` |

An incomplete-report retry can incur another provider charge. Source outages
are recorded and do not discard a completed research result. PDF export failure
leaves the research data and Markdown available.

## Repository layout

```text
backend/
  main.py                 FastAPI endpoints
  jobs.py                 Background jobs and recovery
  library.py              Persistent archive, fingerprints and reuse
  extraction.py           Schema-constrained PDF extraction
  research_prompt.py      Versioned research protocol
  evidence/               Sources, query construction, deduplication, ranking
  providers/              Gemini, OpenAI and Claude adapters
  report_parse.py         Evidence and access-section parsing
  export.py               Markdown and PDF formatting
frontend/src/             React interface, research library and results
scripts/evaluate_recall.py DOI benchmark and report overlap evaluation
tests/                    Offline regression tests with mocked providers
docs/                     Architecture and research-quality guidance
.github/                  CI and pull-request template
```

Root Python scripts are legacy CLI/Streamlit entry points retained for existing
users. New behavior belongs in `backend/` and `frontend/`. Concept notes, model
responses, local archives and exports are excluded from source control. Removing
a file from the current tree does not remove it from historical Git commits.

## Verification

```bash
uv run pytest -q
uv run ruff check backend tests scripts --select E9,F63,F7,F82
cd frontend && npm ci && npm run build
```

GitHub Actions runs backend regression checks and a clean frontend build.
See [contribution guidance](CONTRIBUTING.md). Tests use synthetic inputs; paid
research runs and provider availability need separate live verification.

To compare saved research against a reviewer-approved DOI benchmark:

```bash
uv run python scripts/evaluate_recall.py benchmark.json run1.json run2.json
```

The benchmark has an `expected_dois` array. Results show cited-DOI recall, missing
papers and pairwise overlap. These metrics do not validate claims or full-text
eligibility; reviewers must check those separately.

## Deployment and retention

The Dockerfile builds the frontend and runs FastAPI. This version uses a
single-process job manager: deploy **one worker and one instance**. On Cloud Run,
background work needs `--no-cpu-throttling`, `--min-instances 1` and
`--max-instances 1`. Use sufficient memory for job artifacts and provider runs.

**Mount persistent storage at `LIBRARY_DIR` and back it up.** Cloud Run container
storage is ephemeral. Minimum instances and local JSON persistence do not protect
against redeployment or instance loss. A shared database and durable queue are
required before horizontal scaling. Use a filesystem with atomic rename support
for the archive; do not assume every object-storage mount provides it.

The library is shared by users of an installation. Put the service behind your
organization's authentication before storing private concept-note research. An
unguessable URL is not access control. Keep provider keys in a secret manager.
For existing Cloud Run services, use image-only deployment or
`--update-env-vars`; `--set-env-vars` replaces existing environment settings.

## Evidence-source attribution

Metadata and access discovery use [OpenAlex](https://openalex.org) and
[Economics Literature Search](https://paulgp.com/econlit-pipeline/), developed by
Paul Goldsmith-Pinkham. Source availability and DOI existence do not establish
that a paper supports an AI-generated claim.
