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
- Requests APA 7 author–date references, links citations to their reference entries,
  and adds return links. PDF references use hanging indents and clickable source URLs.

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

**Configure `LIBRARY_GCS_BUCKET` for Google Cloud Storage**, or mount persistent
storage at `LIBRARY_DIR`. With a bucket configured, completed reports and reusable
extractions live in Cloud Storage; `LIBRARY_DIR` is only a download cache and can
be ephemeral. The app uses the Cloud Storage API directly, without a filesystem
mount. See [Google Cloud storage setup](docs/google-cloud-storage.md).

Minimum instances and local JSON persistence do not protect running jobs against
instance loss. A durable queue is still required for job recovery and horizontal
scaling. Cloud Storage protects completed research, not in-flight model calls.

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

### Gemini model selection

New sessions recommend Deep Research Max (`deep-research-max-preview-04-2026`)
for comprehensive literature reviews. Fast (`deep-research-preview-04-2026`)
remains available for quicker, lighter reviews; the December 2025 agent is kept
for legacy compatibility. Existing saved selections are preserved. An API request
without a tier uses the provider recommendation (Max for Gemini).

PDF extraction uses stable `gemini-3.8-flash`, which supports PDF input and
structured output. Set `EXTRACTION_MODEL` to override it. Model IDs are recorded
and included in reuse fingerprints, so changing models does not reuse a report
generated by another model. The app never silently switches to a cheaper model
after a provider error. Max may take up to 60 minutes and costs more than Fast.

Selection reviewed September 2026 against Google's [model specification](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
and [Deep Research guide](https://ai.google.dev/gemini-api/docs/deep-research).
These defaults are based on documented capabilities; comparative quality has
not yet been benchmarked on private concept notes.

When a model omits its reference list, protocol 8.2 attempts bounded Crossref APA
formatting for DOIs already in the report and adds reference navigation. It
preserves the model's original text in JSON and labels the recovered metadata.
Unresolved and non-DOI sources may still need manual formatting.

## Next Ladder intake surveys

Upload PDF or Word (`.docx`) files. Beside the upload area, choose **Detect
 automatically**, **GitLab concept note**, or **Next Ladder intake**. Auto detection
uses document content; uncertain or conflicting classifications pause at prompt
review even in Standard mode. To correct the format, start over and choose it
explicitly. The detected/selected format appears in the review, progress, saved
report and exported document.

Next Ladder extraction preserves users versus beneficiaries, engagement and
conversion, actual versus projected reach, channel-specific financial impact,
counterfactuals, durability, user costs, historical and projected budgets, total
raise and explicit NLV requests. The research protocol includes benefits access,
cost savings and debt-related outcomes alongside earnings, with checks against
double counting and unsupported lifetime extrapolation. It produces evidence
and model-input implications, not a completed ROI calculation.

Word content is parsed as bounded text, including tables and hyperlink targets;
macros, embedded files and external links are never executed or fetched by the
parser. Image-only Word content should be exported to PDF. Blank template examples
are not investee facts. Format selection and protocol version are part of reuse
keys, so changing format cannot reuse an extraction from another selection.

API: `POST /api/extract` accepts multipart `file`, `refresh`, and
`document_format` (`auto`, `concept_note`, `next_ladder_intake`; default `auto`).
