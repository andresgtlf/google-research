"""Shared helpers for polling long-running remote research tasks.

A deep research run is a 5 to 60 minute remote job that we observe through
several hundred sequential status checks. Two things follow from that:

1. **A single failed status check must not kill the job.** Losing a 20-minute
   run to one connection reset is the most expensive failure mode this system
   has, so transient errors are retried with backoff and only a sustained
   outage fails the job.
2. **Our deadline must not race the provider's own.** Gemini documents a
   60-minute maximum research time; a local 60-minute cap therefore reports
   "timed out" for runs that were about to succeed. We poll past the
   provider's maximum so the provider always gets the chance to report a
   terminal status itself.
"""

import logging
import os
import time
from typing import Callable, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Poll past the providers' documented 60-minute ceiling (see module docstring).
DEFAULT_TIMEOUT_S = int(os.environ.get("RESEARCH_TIMEOUT_S", str(75 * 60)))

# Per-request HTTP timeout for status checks, so a stalled socket raises
# instead of blocking the worker thread forever.
POLL_REQUEST_TIMEOUT_S = int(os.environ.get("POLL_REQUEST_TIMEOUT_S", "60"))

# How many consecutive failed status checks we tolerate before giving up.
MAX_CONSECUTIVE_POLL_ERRORS = int(os.environ.get("MAX_POLL_ERRORS", "6"))

# HTTP statuses that will never succeed on retry.
_FATAL_STATUS = {400, 401, 403, 404, 422}


def is_transient(exc: BaseException) -> bool:
    """Whether a failed status check is worth retrying.

    Errors are treated as transient by default: during a long poll the
    expensive mistake is abandoning a live job, not retrying a doomed one a
    few times. Only clearly permanent failures (bad credentials, unknown id,
    malformed request) are fatal.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(status, int) and status in _FATAL_STATUS:
        return False
    return True


def fetch_with_retry(
    fetch: Callable[[], T],
    *,
    on_transient: Optional[Callable[[str], None]] = None,
    what: str = "status check",
) -> T:
    """Run `fetch`, retrying transient failures with exponential backoff.

    Raises the underlying error if it is permanent, or after
    `MAX_CONSECUTIVE_POLL_ERRORS` consecutive transient failures.
    """
    delay = 2.0
    last_error: Optional[BaseException] = None
    for attempt in range(1, MAX_CONSECUTIVE_POLL_ERRORS + 1):
        try:
            return fetch()
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            if not is_transient(exc):
                raise
            last_error = exc
            log.warning(
                "%s failed (attempt %d/%d): %s",
                what,
                attempt,
                MAX_CONSECUTIVE_POLL_ERRORS,
                exc,
            )
            if attempt == MAX_CONSECUTIVE_POLL_ERRORS:
                break
            if on_transient:
                on_transient(
                    f"{what.capitalize()} failed, retrying in {int(delay)}s "
                    f"(attempt {attempt} of {MAX_CONSECUTIVE_POLL_ERRORS})"
                )
            time.sleep(delay)
            delay = min(delay * 2, 60.0)

    raise RuntimeError(
        f"{what} failed {MAX_CONSECUTIVE_POLL_ERRORS} times in a row; "
        f"last error: {last_error}"
    ) from last_error


class Deadline:
    """Monotonic deadline for a polling loop."""

    def __init__(self, timeout_s: int = DEFAULT_TIMEOUT_S):
        self.timeout_s = timeout_s
        self._end = time.monotonic() + timeout_s

    def expired(self) -> bool:
        return time.monotonic() >= self._end

    @property
    def minutes(self) -> int:
        return self.timeout_s // 60
