# Research quality and reuse

Protocol 8.1 separates repeatable inputs from stochastic research. A prompt
cannot guarantee that Gemini, OpenAI or Claude will retrieve the same studies
on every fresh run. They can change search paths, model versions and synthesis.

## Saved runs

By default, identical PDF bytes reuse their saved extraction and evidence
snapshot. The extraction cache includes the extraction model, extraction prompt,
protocol version and seeding flag. Identical extraction, research prompt,
provider, resolved model, protocol version and enrichment setting reuse a saved
report if all requested export files exist. Reopening a saved run has no model
cost and preserves the original timestamp. The fresh-search checkbox bypasses
both caches. Changed source configuration requires a fresh search.

Saved artifacts live under `LIBRARY_DIR` (default `data/library`), separate from
24-hour disposable jobs. The library stores extraction snapshots, report text,
provider/model, exact prompt, evidence candidates, query records, date, fingerprint,
access checks and exported files. It does not retain uploaded PDF bytes.
Existing completed job directories are archived on startup. An archive failure
prevents the reaper deleting the only copy of a completed report.

This is a single-server filesystem archive. On Cloud Run a container directory
is ephemeral even with minimum instances set to one. Set `LIBRARY_DIR` to a
mounted persistent storage location and back it up before relying on retention
across deployments. A shared database and worker queue are needed for horizontal
scaling. The library is shared by all users of the installation: deploy behind
organization authentication. An unguessable URL is not access control.

## Evidence retrieval

`EVIDENCE_SEEDING=1` is the default and runs OpenAlex and econlit
before synthesis. An explicit `EVIDENCE_SEEDING=0` disables it.
Queries without venue constraints now search OpenAlex broadly. Explicit venue
queries remain constrained. All candidates remain subject to causal relevance
screening; broad retrieval does not make every match relevant.

Set `OPENALEX_API_KEY` for authenticated requests. It is sent as a bearer header,
not in URLs. Anonymous requests have a smaller budget; source failures appear in
the retrieval audit. Current authentication documentation:
https://help.openalex.org/api/authentication/

Equal source relevance scores now receive equal normalized scores; final ties
sort by DOI/title/year. This removes an accidental dependence on source result
ordering. Network timeouts and upstream index changes can still alter new
snapshots. The saved snapshot, rather than a fresh search, is the reproducible
unit.

## Access and citations

Closed access, unknown access and abstract-only are distinct states. A missing
open-access URL does not prove a paywall. Retain publisher/DOI links and verified
free working-paper versions. Supplementary appendices do not count as full text.
OpenAlex DOI existence checks do not establish that a paper supports a claim.
The Markdown/PDF downloads include the same access and citation appendix as the
interface. The JSON download includes the underlying research record.

## Evaluation before rollout

Offline regression tests verify behavior, not research recall. Build a reviewed
benchmark of synthetic or approved concept notes and known relevant study DOIs.
Run fresh searches at least three times per provider. Measure benchmark recall,
Jaccard overlap of included studies, missed long-run papers, null-effect coverage,
unsupported effect-size claims and access-link correctness. Do not use an LLM's
own report as the gold standard. Review failures before changing retrieval
weights or deploying the new protocol.

## APA citations and navigation

Protocol 8.1 requests APA 7 author-date citations and an alphabetical reference
list with verified DOI or publisher hyperlinks. The application adds stable
citation destinations and per-occurrence return links; the PDF uses hanging
indents and a references shortcut. Internal links in the app stay in the report.

The navigation pass does not invent missing bibliographic metadata or guarantee
that a model formatted every field correctly. It recognizes older APA-style
reference lists where possible, flags ambiguous or missing references, and
retains unrecognized material. The research JSON preserves the original model
text as `original_result`. Existing saved artifacts are not rewritten in place.
