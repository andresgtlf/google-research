"""Structural-compliance validation and the single re-ask.

On 2026-08-01 two runs of a byte-identical prompt, on the same revision 70
minutes apart, produced a report with 4 of 7 mandatory headings and one with 1
of 7. The second was published to a reviewer with no Conclusions section and no
Evidence Digest. Commit a94469b had already made the structure mandatory in the
prompt; wording alone did not hold. See `notes/incident-2026-08-01/`.
"""

import pytest

from backend.jobs import (
    STRUCTURE_RETRY_THRESHOLD,
    _retry_if_structurally_broken,
)
from backend.report_parse import (
    MANDATORY_HEADINGS,
    missing_headings,
    present_headings,
    structural_completeness,
)

COLLAPSED = """**Long-term income effect**

The effects are positive.

## Paywalled High-Value Papers — Manual Retrieval List

No high-value paywalled papers were identified.
"""

COMPLETE = """## Search Metadata

econlit, OpenAlex.

## Included Studies

- Cohodes et al. 2022

## Excluded Studies

- None identified

## Evidence Digest

| Study | Country | Effect |
|---|---|---|
| Cohodes 2022 | US | +3-15% |

## Mechanism Assessment

Partially supported.

## Conclusions

Moderate evidence.

## Paywalled High-Value Papers — Manual Retrieval List

None.
"""


class FakeProvider:
    def __init__(self, *returns):
        self.returns = list(returns)
        self.calls = 0

    def run(self, prompt, model, on_event):
        self.calls += 1
        value = self.returns.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeJob:
    id = "test"

    def __init__(self):
        self.events = []

    def add_event(self, message, *a, **kw):
        self.events.append(message)


def _retry(first, provider):
    return _retry_if_structurally_broken(
        first, provider=provider, prompt="P", model="m", job=FakeJob()
    )


# ── measurement ────────────────────────────────────────────────────────────


def test_the_collapsed_report_scores_one_of_seven():
    assert present_headings(COLLAPSED) == ("Paywalled High-Value Papers",)
    assert structural_completeness(COLLAPSED) == pytest.approx(1 / 7)


def test_a_complete_report_scores_seven_of_seven():
    assert structural_completeness(COMPLETE) == 1.0
    assert missing_headings(COMPLETE) == ()


def test_every_mandatory_heading_is_detected_in_a_real_report():
    assert len(present_headings(COMPLETE)) == len(MANDATORY_HEADINGS)


# ── the retry ──────────────────────────────────────────────────────────────


def test_a_collapsed_report_triggers_exactly_one_retry():
    provider = FakeProvider(COMPLETE)
    assert _retry(COLLAPSED, provider) == COMPLETE
    assert provider.calls == 1


def test_an_acceptable_report_is_never_retried():
    """A retry costs real money and up to 75 minutes; it must not fire on a
    report that is merely imperfect."""
    provider = FakeProvider(COMPLETE)
    assert structural_completeness(COMPLETE) >= STRUCTURE_RETRY_THRESHOLD
    assert _retry(COMPLETE, provider) == COMPLETE
    assert provider.calls == 0


def test_a_failing_retry_never_loses_the_first_report():
    """The v6 rule: an expensive result must never be lost to a step that runs
    after it."""
    provider = FakeProvider(RuntimeError("provider exploded"))
    assert _retry(COLLAPSED, provider) == COLLAPSED
    assert provider.calls == 1


def test_a_retry_that_is_no_better_keeps_the_original():
    worse = "## Paywalled High-Value Papers\n\nNone.\n"
    provider = FakeProvider(worse)
    assert _retry(COLLAPSED, provider) == COLLAPSED


def test_the_retry_never_loops():
    provider = FakeProvider(COLLAPSED, COLLAPSED, COLLAPSED)
    _retry(COLLAPSED, provider)
    assert provider.calls == 1


def test_the_retry_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("RESEARCH_STRUCTURE_RETRY", "0")
    provider = FakeProvider(COMPLETE)
    assert _retry(COLLAPSED, provider) == COLLAPSED
    assert provider.calls == 0


def test_the_reviewer_is_told_what_was_missing():
    job = FakeJob()
    _retry_if_structurally_broken(
        COLLAPSED, provider=FakeProvider(COMPLETE), prompt="P", model="m", job=job
    )
    log = " ".join(job.events)
    assert "Conclusions" in log and "Evidence Digest" in log
