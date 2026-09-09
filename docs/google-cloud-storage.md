# Google Cloud research archive

The optional `LIBRARY_GCS_BUCKET` setting stores completed report artifacts,
research metadata, and extraction reuse data in a private Cloud Storage bucket.
Input PDFs and API keys are not uploaded by this storage adapter. Extracted
concept-note fields and research prompts can still contain confidential data.
The archive remains shared by users of the application.

## Configured infrastructure

Verified September 9, 2026:

- Project: `gen-lang-client-0479667603` (`gtlfroi`).
- Bucket: `gtlf-research-library-695396203364`, Standard storage in `us-central1`.
- Uniform bucket-level access and public access prevention enabled.
- Default seven-day soft deletion retained; no report expiration rule.
- Existing Cloud Run service: `gitlab-research-agent`, region `us-central1`.
- Existing runtime identity: `695396203364-compute@developer.gserviceaccount.com`.
- Bucket-level `roles/storage.objectUser` granted to that identity. No key file created.

Storage and request charges apply. The bucket does not host a public website or
expose public report URLs. The service still needs organization authentication
before confidential research is accessible through its API.

## Activate with the updated application

The updated application was deployed on September 9, 2026, from merged PR #1
with a live-test correction in commit `220223f`. Revision
`gitlab-research-agent-00012-cos` serves 100% of
production traffic with the archive enabled. For subsequent deployments, preserve
existing secrets and settings; add or change these values with `--update-env-vars`:

```text
LIBRARY_GCS_BUCKET=gtlf-research-library-695396203364
LIBRARY_DIR=/tmp/research-library-cache
```

Do not set `GOOGLE_APPLICATION_CREDENTIALS` on Cloud Run: the client uses the
attached service identity automatically. For this single-process app retain
one worker, `--max-instances 1`, `--min-instances 1`, and `--no-cpu-throttling`.
The production rollout set those worker options. The previous revision
`gitlab-research-agent-00008-jp9` is available for rollback, but lacks this archive
adapter. Rolling back application traffic does not delete bucket contents.

For local use, run `gcloud auth application-default login` using the Foundation
account, then add the bucket setting to `.env` and restart the app. The existing
local ADC credentials required reauthentication during setup, so local `.env`
was not switched to cloud storage. Live verification used the active gcloud
account with a short-lived token held only in memory.

## Durability and recovery

Artifacts are uploaded before `runs/<run-id>/job.json`, which acts as the commit
marker. The library lists only committed runs. Repeating a partial upload is
safe when bytes match; conflicting report content cannot overwrite the same
run. Opening a saved run downloads files into a disposable local cache. Exact
reuse reads remote metadata and works after the local cache is deleted.

Extraction JSON is stored under its content/configuration fingerprint. A refresh
may replace that single cache object atomically. Cloud Storage errors are surfaced
instead of being treated as cache misses. Failed archive writes retain the local
report and add a warning; cleanup retains unarchived reports during an outage.
Retry archival by restarting the app while its job directory is still available.
Do not rely on that directory surviving a Cloud Run replacement.

Existing completed jobs found in `JOBS_DIR` are archived on startup. Existing
files in a previous local `LIBRARY_DIR` are not bulk migrated automatically; keep
that volume until any desired migration has been explicitly performed. No real
concept-note data was migrated during provisioning.

This is a completed-research archive, not a durable job queue or an indexed
research database. Listing currently scans run metadata, suitable for a small
team library; larger collections should add a database index. In-flight work
still requires the existing worker to finish. Cloud Run restarts can interrupt it.

## Production release

- App: https://gitlab-research-agent-oefuclnypq-uc.a.run.app
- Image digest: `sha256:f26eb803bf7a2c81334b172f894af3a25260c1d83748aae5467ff815ffcb7e97`.
- Cloud Build: `a3356dd2-5848-4e14-ab2b-ead90b9f405b`.
- Existing public invocation permissions were retained. Organization sign-in
  protection remains required before confidential research is stored.
- Gemini is configured. OpenAI and Claude need their optional API keys.

## Verification

Offline tests cover empty-cache recovery, exact reuse, missing formats, partial
uploads, conflict prevention, extraction persistence, invalid paths, corrupted
metadata and cleanup during a storage outage. The live smoke test uploaded only
synthetic data, reopened it through a fresh cache, verified reuse, and removed
its test objects afterward (soft-deleted copies expire after seven days).

References: [Cloud Storage uploads](https://docs.cloud.google.com/storage/docs/uploading-objects)
and [uniform bucket-level access](https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access).

Production verification also completed a real Gemini 3.8 Flash extraction, ten
OpenAlex queries (211 matches before deduplication), and a narrowly scoped Gemini
Deep Research Max run. The run completed in about eight minutes. A repeated
request reused the saved result. The live run revealed omitted APA references
and a DOI parsing issue; protocol 8.2 now recovers omitted reference lists through
Crossref's APA formatter for DOI links already in the report. Failed metadata
lookups leave the original report intact. This does not verify research claims.

The test report was reformatted without another model call. Its cloud-saved PDF
has five resolved internal links and sixteen external links; browser citations
have no missing destinations. The final revision recovered the report and PDF
from Cloud Storage into a fresh cache. The corrected synthetic sample remains
in the library as Deployment Test; its original uncorrected test copy was removed.
167 backend tests passed before the corrected deployment.
