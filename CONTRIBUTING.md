# Contributing

The supported application is `backend/` (FastAPI) and `frontend/` (React).
Root Python scripts are legacy entry points; do not add application behavior there.
Evidence adapters belong in `backend/evidence/`, model integrations in
`backend/providers/`, and regression tests in `tests/`.

Create a short-lived branch and a pull request. Keep data and credentials out of
Git. Run `uv sync --locked`, `uv run pytest`, and `npm ci && npm run build` in
`frontend/`. CI also checks Python syntax and undefined names with Ruff.

Use mocked provider responses in automated tests. Live research costs money;
record provider, model, protocol version and input fingerprint for evaluations.
Evaluate retrieval changes against known relevant papers, including paywalled,
null-effect and long-term follow-up studies. Report recall and included-study
Jaccard overlap between fresh runs. A saved-run replay tests reproducibility,
not scholarly completeness.

Do not commit concept notes, provider responses, exported research, API keys or
local incident artifacts. Use synthetic examples. Deployment is separate from
code changes; see README for the single-instance storage constraints.
