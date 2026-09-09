"""EconLit search — a free-text index over economics journals plus NBER.

Hosted on a third party's free Render tier (see `_BASE_URL`), so two things
follow: it cold-starts in ~30s on the first request of a process, and it can
disappear entirely without warning. Neither may take down a research run, so
every public method here returns a `SearchOutcome`/`Optional[Candidate]`
instead of raising — see `backend/evidence/base.py` for the contract.

The other defining trait of this API: `url` is empty on every result and
`abstract` is empty ~93% of the time. `find_by_title` exists specifically to
recover a paywalled journal article's free NBER working-paper twin by exact
title, and `enrich.py` fills the abstract/URL gap from OpenAlex afterward.
"""

import logging
import os
import threading
from typing import Any

import requests

from .base import Candidate, EvidenceQuery, EvidenceSource, QueryRecord, SearchOutcome

log = logging.getLogger(__name__)

_BASE_URL = "https://econlit-api.onrender.com"

_USER_AGENT = "GTLF-Research-Evidence-Retrieval/1.0 (+andres@gitlabfoundation.org)"

# Regular per-request timeout once the process is warm.
TIMEOUT_S = int(os.environ.get("ECONLIT_TIMEOUT_S", "25"))

# Allowance for the first request in a process, which pays the Render
# cold-start cost (observed ~30s) on top of normal latency.
WAKE_TIMEOUT_S = int(os.environ.get("ECONLIT_WAKE_TIMEOUT_S", "45"))

# The 14 venues this index covers, as of the last manual check of
# `/api/journals`. Hardcoded so the source is usable offline / when that
# endpoint itself is cold or unreachable; `refresh_covered_venues` can update
# it from the live endpoint but is never required for correctness.
_KNOWN_VENUES: tuple[str, ...] = (
    "American Economic Journal: Applied Economics",
    "American Economic Journal: Economic Policy",
    "American Economic Journal: Macroeconomics",
    "American Economic Journal: Microeconomics",
    "American Economic Review",
    "Econometrica",
    "Journal of Econometrics",
    "Journal of Financial Economics",
    "Journal of Political Economy",
    "NBER Working Papers",
    "The Journal of Finance",
    "The Quarterly Journal of Economics",
    "The Review of Economic Studies",
    "The Review of Financial Studies",
)


def _split_authors(raw: Any) -> tuple[str, ...]:
    """Authors arrive as one comma-separated string, not a list."""
    if not isinstance(raw, str) or not raw.strip():
        return ()
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _row_to_candidate(row: dict[str, Any]) -> Candidate:
    """Map one `/api/search` result row to a `Candidate`.

    Defensive about missing/wrong-typed keys because this is a third-party
    API with no schema guarantee — a malformed row must degrade, not raise.
    """
    replication = row.get("replication") or {}
    if not isinstance(replication, dict):
        replication = {}

    year_raw = row.get("year")
    year = year_raw if isinstance(year_raw, int) else None

    citations_raw = row.get("citation_count")
    citations = citations_raw if isinstance(citations_raw, int) else None

    relevance_raw = row.get("relevance")
    relevance = float(relevance_raw) if isinstance(relevance_raw, (int, float)) else 0.0

    return Candidate(
        title=str(row.get("title") or ""),
        authors=_split_authors(row.get("authors")),
        year=year,
        venue=str(row.get("journal") or ""),
        doi=str(row.get("doi") or ""),
        abstract=str(row.get("abstract") or ""),
        citations=citations,
        oa_url="",  # econlit never returns a URL; OpenAlex fills this in.
        replication_status=str(replication.get("status") or ""),
        replication_url=str(replication.get("repo_url") or ""),
        sources=("econlit",),
        relevance=relevance,
    )


class EconlitSource(EvidenceSource):
    """Full-text search over a curated set of top economics journals + NBER."""

    id = "econlit"
    label = "Economics Literature Search"
    covered_venues: tuple[str, ...] = _KNOWN_VENUES

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = _USER_AGENT
        self._woken = False
        self._wake_lock = threading.Lock()

    def _timeout_s(self) -> int:
        """The first request in a process pays the cold-start cost."""
        with self._wake_lock:
            if not self._woken:
                self._woken = True
                return WAKE_TIMEOUT_S
        return TIMEOUT_S

    def refresh_covered_venues(self) -> tuple[str, ...]:
        """Best-effort refresh of `covered_venues` from `/api/journals`.

        Never required: `covered_venues` already holds the last known-good
        list, and this method leaves it untouched on any failure.
        """
        try:
            response = self._session.get(
                f"{_BASE_URL}/api/journals", timeout=self._timeout_s()
            )
            response.raise_for_status()
            venues = response.json()
            if isinstance(venues, list) and all(isinstance(v, str) for v in venues):
                self.covered_venues = tuple(venues)
        except (requests.RequestException, ValueError) as exc:
            log.warning("econlit: failed to refresh venue list: %s", exc)
        return self.covered_venues

    def search(self, query: EvidenceQuery) -> SearchOutcome:
        params: dict[str, Any] = {
            "q": query.terms,
            "search_in": query.scope,
            "search_mode": query.mode,
            "limit": query.limit,
        }
        if query.year_start is not None:
            params["year_start"] = query.year_start
        if query.year_end is not None:
            params["year_end"] = query.year_end
        if query.venues:
            params["journals"] = list(query.venues)

        record_base = dict(
            source=self.id,
            terms=query.terms,
            scope=query.scope,
            mode=query.mode,
            venues=query.venues,
            year_start=query.year_start,
            year_end=query.year_end,
            label=query.label,
        )

        try:
            response = self._session.get(
                f"{_BASE_URL}/api/search",
                params=params,
                timeout=self._timeout_s(),
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            log.warning("econlit: request failed for %r: %s", query.terms, exc)
            return SearchOutcome(
                record=QueryRecord(**record_base, error=f"request failed: {exc}")
            )
        except ValueError as exc:
            log.warning("econlit: non-JSON response for %r: %s", query.terms, exc)
            return SearchOutcome(
                record=QueryRecord(**record_base, error=f"invalid response: {exc}")
            )

        try:
            if not isinstance(payload, dict):
                raise TypeError(f"expected object, got {type(payload).__name__}")
            rows = payload.get("results") or []
            candidates = tuple(
                _row_to_candidate(row) for row in rows if isinstance(row, dict)
            )
            total = payload.get("total_results")
            total_results = total if isinstance(total, int) else len(candidates)
        except (TypeError, KeyError, AttributeError) as exc:
            log.warning("econlit: malformed payload for %r: %s", query.terms, exc)
            return SearchOutcome(
                record=QueryRecord(**record_base, error=f"malformed response: {exc}")
            )

        return SearchOutcome(
            candidates=candidates,
            record=QueryRecord(
                **record_base,
                total_results=total_results,
                returned=len(candidates),
            ),
        )

    def find_by_title(self, title: str) -> SearchOutcome:
        """Exact-ish title lookup — the highest-value call in the system.

        Wraps `title` in double quotes and searches `scope="title"`, which is
        how a paywalled journal article gets matched to its free NBER
        working-paper twin.
        """
        return self.search(
            EvidenceQuery(
                terms=f'"{title}"',
                scope="title",
                label="title recovery",
            )
        )
