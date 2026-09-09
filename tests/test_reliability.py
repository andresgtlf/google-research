"""Regression tests for the v6 reliability and security fixes.

These cover the failure modes that made expensive research runs disappear:
the report-extraction bug, the report-parse blind spot, restart handling, and
the SPA path-traversal hole. None of them need an API key.
"""

import json
from pathlib import Path

import pytest

# ── Gemini report extraction ───────────────────────────────────────
# The real Interaction.outputs is a discriminated union of ~17 block types and
# only text blocks carry `.text`, so `outputs[-1].text` raised AttributeError
# whenever a run ended on a tool-trace block.

from backend.providers.gemini import _collect_report_text  # noqa: E402


class Block:
    """Stand-in for one output block; only sets the fields its type has."""

    def __init__(self, type_: str, **fields):
        self.type = type_
        for key, value in fields.items():
            setattr(self, key, value)


class Interaction:
    def __init__(self, outputs=None, steps=None):
        if outputs is not None:
            self.outputs = outputs
        if steps is not None:
            self.steps = steps


def test_report_text_found_when_run_ends_on_a_tool_block():
    """The regression: report text precedes trailing search/thought blocks."""
    interaction = Interaction(
        outputs=[
            Block("thought", summary="Planning the search"),
            Block("text", text="# Report\n\nFindings here."),
            Block("google_search_call", id="s1", arguments="{}"),
            Block("google_search_result", call_id="s1", result="..."),
        ]
    )
    assert _collect_report_text(interaction) == "# Report\n\nFindings here."


def test_thought_blocks_are_excluded_from_the_report():
    interaction = Interaction(
        outputs=[
            Block("thought", summary="I should check J-PAL", text="internal"),
            Block("text", text="Real report"),
        ]
    )
    assert _collect_report_text(interaction) == "Real report"


def test_multiple_text_blocks_are_concatenated_in_order():
    interaction = Interaction(
        outputs=[Block("text", text="Part one"), Block("text", text="Part two")]
    )
    assert _collect_report_text(interaction) == "Part one\nPart two"


def test_steps_shape_is_supported_as_a_fallback():
    """The post-May-2026 schema exposes the trace as `steps` with nested
    content, replacing the older flat `outputs` list."""
    interaction = Interaction(
        steps=[
            Block("model_output", content=[Block("thought", summary="hmm")]),
            Block("model_output", content=[Block("text", text="Nested report")]),
        ]
    )
    assert _collect_report_text(interaction) == "Nested report"


def test_output_text_convenience_property_is_preferred():
    """google-genai >= 2.0 joins the final text parts into `output_text`."""
    interaction = Interaction(steps=[Block("model_output", content=[])])
    interaction.output_text = "# Final report\n\nFrom output_text."
    assert _collect_report_text(interaction) == "# Final report\n\nFrom output_text."


def test_blank_output_text_falls_through_to_the_step_timeline():
    interaction = Interaction(
        steps=[Block("model_output", content=[Block("text", text="From steps")])]
    )
    interaction.output_text = "   "
    assert _collect_report_text(interaction) == "From steps"


def test_trace_blocks_flattens_steps_and_tolerates_flat_outputs():
    from backend.providers.gemini import _trace_blocks

    stepped = Interaction(
        steps=[
            Block("model_output", content=[Block("thought"), Block("text", text="a")]),
            Block("model_output", content=[Block("google_search_call")]),
        ]
    )
    assert [b.type for b in _trace_blocks(stepped)] == [
        "thought",
        "text",
        "google_search_call",
    ]
    flat = Interaction(outputs=[Block("text", text="a"), Block("thought")])
    assert [b.type for b in _trace_blocks(flat)] == ["text", "thought"]


def test_no_text_anywhere_returns_empty_so_the_caller_can_raise():
    interaction = Interaction(outputs=[Block("google_search_call", id="s1")])
    assert _collect_report_text(interaction) == ""


def test_text_block_with_null_text_is_not_treated_as_the_report():
    interaction = Interaction(
        outputs=[Block("text", text=None), Block("text", text="Actual")]
    )
    assert _collect_report_text(interaction) == "Actual"


# ── Poll retry behaviour ───────────────────────────────────────────
# Losing a 20-minute run to one connection reset was the most expensive
# failure mode in the system.

from backend.providers import _polling  # noqa: E402


class Boom(Exception):
    """A transient network-shaped error."""


class Unauthorized(Exception):
    status_code = 401


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(_polling.time, "sleep", lambda _s: None)


def test_transient_failures_are_retried_then_succeed():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Boom("connection reset")
        return "report"

    events: list[str] = []
    assert _polling.fetch_with_retry(flaky, on_transient=events.append) == "report"
    assert calls["n"] == 3
    assert len(events) == 2  # user saw both retries, not a dead job


def test_permanent_failures_are_not_retried():
    calls = {"n": 0}

    def unauthorized():
        calls["n"] += 1
        raise Unauthorized("bad key")

    with pytest.raises(Unauthorized):
        _polling.fetch_with_retry(unauthorized)
    assert calls["n"] == 1  # no point retrying a 401


def test_sustained_outage_eventually_fails_with_context():
    def always_down():
        raise Boom("nope")

    with pytest.raises(RuntimeError, match="times in a row"):
        _polling.fetch_with_retry(always_down, what="research status check")


def test_deadline_is_above_the_providers_documented_maximum():
    """Gemini documents a 60 minute maximum research time. A local cap equal
    to it reported our timeout for runs that were about to succeed."""
    assert _polling.DEFAULT_TIMEOUT_S > 60 * 60
    assert _polling.Deadline(_polling.DEFAULT_TIMEOUT_S).minutes >= 75


# ── Report section parsing ─────────────────────────────────────────

from backend.report_parse import parse_report_sections  # noqa: E402

# A structurally COMPLETE report. It previously carried only 3 of the 7
# headings Section K declares mandatory, while the test asserting "all sections
# present" passed — which is precisely how a 1-of-7 report reached a reviewer
# on 2026-08-01. See notes/incident-2026-08-01/.
GOOD_REPORT = """# Income Effects Review

## Search Metadata

Databases searched: econlit, OpenAlex. 2011-2026.

## Included Studies

- Banerjee 2015

## Excluded Studies

- None identified

## Mechanism Assessment

The mechanism is partially supported.

## Evidence Digest

| Study | Country | Effect | Link |
|---|---|---|---|
| Banerjee 2015 | Kenya | +12% earnings | https://example.org/a |

## Conclusions

The evidence base is moderate.

## Paywalled High-Value Papers

- Some Paper (2019), Journal of Development Economics
"""


def test_parse_warnings_empty_when_all_sections_present():
    sections = parse_report_sections(GOOD_REPORT)
    assert sections["parse_warnings"] == []
    assert sections["conclusions"].startswith("## Conclusions")
    assert sections["evidence_table"][0]["Country"] == "Kenya"


def test_missing_sections_are_reported_not_silently_dropped():
    """Without this the UI rendered an almost-empty page and looked broken."""
    sections = parse_report_sections("# Report\n\nJust prose, no headings.\n")
    assert sections["conclusions"] == ""
    assert sections["evidence_table"] is None
    # conclusions, evidence digest, and the four audit-trail sections
    assert len(sections["parse_warnings"]) == 3
    assert any("conclusions" in w.lower() for w in sections["parse_warnings"])


def test_absent_paywalled_section_is_not_a_warning():
    """Nothing paywalled is a legitimate outcome, not a parse failure."""
    report = GOOD_REPORT.split("## Paywalled")[0]
    sections = parse_report_sections(report)
    assert sections["paywalled"] == ""
    assert not any("paywall" in w.lower() for w in sections["parse_warnings"])


# ── Restart handling ───────────────────────────────────────────────


def test_interrupted_jobs_are_reconciled_on_restore(tmp_path, monkeypatch):
    """A job whose thread died must not keep reporting "running" forever."""
    import backend.jobs as jobs

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    job_dir = tmp_path / "abc123"
    job_dir.mkdir()
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "kind": "research",
                "status": "running",
                "created_at": "2026-07-31T10:00:00+00:00",
                "updated_at": "2026-07-31T10:05:00+00:00",
                "events": [],
                "remote_id": "rsr_xyz",
                "result": {},
            }
        )
    )

    restored = jobs.Job.restore(json.loads((job_dir / "job.json").read_text()))
    assert restored.status == "interrupted"
    assert "restarted" in (restored.error or "").lower()
    assert "rsr_xyz" in (restored.error or "")


def test_completed_jobs_survive_restore_unchanged(tmp_path, monkeypatch):
    import backend.jobs as jobs

    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path)
    restored = jobs.Job.restore(
        {
            "id": "done1",
            "kind": "research",
            "status": "completed",
            "created_at": "2026-07-31T10:00:00+00:00",
            "updated_at": "2026-07-31T10:30:00+00:00",
            "events": [{"time": "t", "message": "Research completed"}],
            "result": {"report_markdown": "# Report"},
        }
    )
    assert restored.status == "completed"
    assert restored.result["report_markdown"] == "# Report"


def test_save_never_raises_even_when_the_directory_is_unwritable(tmp_path):
    """The failure path calls add_event then set_status("failed"). If the write
    raised, the job would be stuck at "running" with a dead thread."""
    import backend.jobs as jobs

    job = jobs.Job.restore(
        {"id": "nodir", "kind": "extract", "status": "failed", "events": []}
    )
    job.dir = Path("/proc/definitely-not-writable/nodir")
    job.add_event("this must not raise")
    job.set_status("failed", error="boom")
    assert job.status == "failed"


# ── SPA route path traversal ───────────────────────────────────────


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import backend.main as main

    if not main.FRONTEND_DIST.exists():
        pytest.skip("frontend/dist not built")
    return TestClient(main.app)


@pytest.mark.parametrize(
    "attack",
    [
        "/../pyproject.toml",
        "/..%2fpyproject.toml",
        "/%2e%2e/pyproject.toml",
        "/%2e%2e%2f%2e%2e%2fpyproject.toml",
        "/..%2f..%2fbackend%2fmain.py",
    ],
)
def test_spa_route_does_not_serve_files_outside_dist(client, attack):
    """Percent-encoded .. segments arrive here decoded; before the fix these
    returned real file contents (verified arbitrary file read)."""
    response = client.get(attack)
    assert response.status_code == 200
    body = response.text
    assert "[project]" not in body, f"leaked pyproject.toml via {attack}"
    assert "FastAPI" not in body, f"leaked backend source via {attack}"
    assert "<" in body, "expected the SPA index.html fallback"
