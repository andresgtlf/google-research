from backend.evidence.status import openalex_status


def snapshot(*records):
    return {"queries": list(records), "retrieved_at": "2026-09-09T12:00:00Z"}


def test_success_and_empty_search_are_distinct_from_failure():
    status = openalex_status(snapshot({"source": "openalex", "returned": 0}))
    assert status["state"] == "complete"
    assert status["matches"] == 0
    assert status["queries_completed"] == 1
    assert openalex_status(None)["state"] == "unavailable"
    assert openalex_status(snapshot({"source": "openalex", "error": "429"}))["state"] == "unavailable"


def test_partial_results_do_not_claim_complete_connection():
    status = openalex_status(snapshot(
        {"source": "openalex", "returned": 5},
        {"source": "openalex", "error": "timeout"},
        {"source": "econlit", "returned": 100},
    ))
    assert status["state"] == "partial"
    assert status["matches"] == 5
    assert status["queries_failed"] == 1


def test_timeout_and_cached_failure_remain_visible():
    status = openalex_status(snapshot(
        {"source": "openalex", "returned": 4},
        {"source": "retrieval", "error": "budget exceeded"},
    ))
    assert status["state"] == "partial"
    cached = openalex_status(snapshot({"source": "openalex", "error": "offline"}), reused=True)
    assert cached["state"] == "unavailable"
    assert cached["reused"] is True
    assert "no new connection" in cached["message"]


def test_status_survives_job_persistence(tmp_path, monkeypatch):
    import backend.jobs as jobs
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    job = jobs.Job("extract")
    job.set_evidence_status({"state": "searching", "message": "Connecting to OpenAlex"})
    job.set_status("completed")
    restored = jobs.Job.restore(job.to_dict())
    assert restored.evidence_status == job.evidence_status
