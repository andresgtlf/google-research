"""Orchestrates the paper-retrieval pipeline end to end.

Pipeline: `build_queries` -> route + run queries across sources concurrently
-> collect candidates and `QueryRecord`s -> `merge_candidates` -> `enrich`
(OpenAlex only) -> `rank` -> cap at `limit` -> assemble a `RetrievalResult`.

Retrieval sits in front of a research pipeline that costs real money and up
to ~75 minutes per run (see `base.py`'s module docstring: it is an
*accelerator*, never a precondition). That gives `retrieve()` a much
stricter contract than anything it calls: it MUST NEVER RAISE and MUST NEVER
RETURN `None`, no matter what breaks underneath it — a source outage, a
network blackout, a malformed `Extraction`, or a bug in a helper this module
does not own. Every code path ends in a valid, possibly-empty
`RetrievalResult`. The whole body below is wrapped in a top-level
try/except as a backstop, layered on top of the per-source and per-query
guards inside the pipeline itself, precisely so a failure nobody anticipated
still degrades gracefully instead of propagating into the caller's run.
"""

import logging
import os
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Optional

from ..schemas import Extraction
from . import list_sources
from .base import (
    Candidate,
    EvidenceQuery,
    EvidenceSource,
    QueryRecord,
    RetrievalResult,
    SearchOutcome,
)
from .dedupe import merge_candidates
from .enrich import enrich
from .openalex import OpenAlexSource
from .queries import build_queries
from .ranking import rank

log = logging.getLogger(__name__)

# IO-bound HTTP calls, so a small thread pool buys real wall-clock savings
# over running up to MAX_QUERIES (see queries.py) x up to len(sources) calls
# serially. Kept small and fixed rather than scaled to query count: this is
# an accelerator, not a batch job, and a wide pool against two small
# third-party APIs — one on a free Render tier, see econlit.py — risks
# looking like abuse rather than a research tool.
MAX_WORKERS = 4

# Overall wall-clock ceiling for the whole retrieval pipeline. Overridable
# for local tuning/tests, mirroring the TIMEOUT_S pattern in econlit.py /
# openalex.py.
RETRIEVAL_BUDGET_S = int(os.environ.get("RETRIEVAL_BUDGET_S", "90"))

# Neither `EvidenceSource` nor its concrete subclasses expose a formal
# "supports full-text search" capability flag, so this is inferred by
# reading the implementations rather than guessed at generically:
# `OpenAlexSource._build_filters` explicitly maps `scope="full_text"` to the
# `fulltext.search` OpenAlex filter field. `EconlitSource.search` passes
# `scope` straight through to the third-party API as the `search_in` param
# with no documented contract for a `full_text` value, so it is deliberately
# left out here rather than assumed to work. See `_route_query`.
_FULL_TEXT_CAPABLE_SOURCE_IDS = frozenset({OpenAlexSource.id})


def _load_elite_venues() -> tuple[str, ...]:
    """Parse `research_prompt.ELITE_JOURNALS` into individual venue names.

    Deliberately a *local* (call-scope) import rather than a module-level
    one. `research_prompt.py` imports `evidence.base` and
    `evidence.candidate_table`, both submodules of this same `evidence`
    package. Today that is not actually a cycle: `retrieval.py` is loaded as
    an ordinary submodule (via `backend.evidence.retrieval` or
    `from .retrieval import retrieve`), which Python only does *after*
    `evidence/__init__.py` has fully finished executing, so importing
    `research_prompt` from inside `retrieval.py` at that point sees a fully
    initialized `evidence` package and works fine either way.

    The local import is kept anyway as a deliberate safety margin rather
    than a proven necessity: `evidence/__init__.py` does not import
    `retrieval.py` today, but if it, or any future module, ever comes to
    re-export something from `retrieval.py` at package-init time, a
    module-level import here would silently become a real cycle
    (`evidence` -> `retrieval` -> `research_prompt` -> `evidence.base`,
    with `evidence` still mid-initialization). Deferring the import to call
    time removes that fragility entirely, at the cost of one `sys.modules`
    lookup per call — negligible next to a network round trip.
    """
    from ..research_prompt import ELITE_JOURNALS  # local import — see docstring

    return tuple(v.strip() for v in ELITE_JOURNALS.split("; ") if v.strip())


def _route_query(
    query: EvidenceQuery, sources: Sequence[EvidenceSource]
) -> list[EvidenceSource]:
    """Decide which sources one query should run against.

    Routing rule, in priority order (documented here because a future reader
    needs to know *why* a given query went where):

    1. Venue-scoped queries (`query.venues` non-empty) go only to sources
       that declare at least one of those venues in `covered_venues`.
       Sending a venue filter to a source that recognizes none of the named
       venues is, at best, a wasted HTTP call, and at worst a source that
       silently returns zero rows for a filter it does not understand.
    2. Full-text-scoped queries (`scope == "full_text"`) go only to sources
       listed in `_FULL_TEXT_CAPABLE_SOURCE_IDS` (see that constant).
    3. Everything else — no venue constraint, not full-text — goes to every
       available source. Recall is cheap here; precision is the query
       terms' job (see `queries.py`'s module docstring on narrow queries).

    In both (1) and (2), if applying the rule would route to zero sources
    (e.g. no configured source declares the requested venue), the query
    falls back to every available source rather than being silently
    dropped: a broader-than-requested search beats no search at all.
    """
    available = [s for s in sources if s.available()]
    if not available:
        return []

    if query.venues:
        venues = set(query.venues)
        matches = [s for s in available if venues & set(s.covered_venues)]
        return matches or available

    if query.scope == "full_text":
        capable = [s for s in available if s.id in _FULL_TEXT_CAPABLE_SOURCE_IDS]
        return capable or available

    return available


def _search_safe(source: EvidenceSource, query: EvidenceQuery) -> SearchOutcome:
    """Run one query against one source, never letting it raise.

    Every `EvidenceSource` is documented (base.py) to never raise — but a
    defensive orchestrator does not take a contract on faith when the
    alternative is one buggy source taking down the whole retrieval run.
    """
    try:
        return source.search(query)
    except Exception as exc:  # noqa: BLE001 - defensive backstop, see docstring
        log.exception(
            "retrieval: source %r raised on query %r (contract violation — "
            "EvidenceSource.search must never raise)",
            source.id,
            query.terms,
        )
        return SearchOutcome(
            record=QueryRecord(
                source=source.id,
                terms=query.terms,
                scope=query.scope,
                mode=query.mode,
                venues=query.venues,
                year_start=query.year_start,
                year_end=query.year_end,
                label=query.label,
                error=f"source raised unexpectedly: {exc}",
            )
        )


def _run_queries(
    tasks: list[tuple[EvidenceQuery, EvidenceSource]], deadline: float
) -> tuple[list[Optional[SearchOutcome]], bool]:
    """Run every (query, source) task under a bounded pool, honoring `deadline`.

    Returns `(outcomes, truncated)` where `outcomes[i]` is `None` for any
    task that never got a chance to finish before the budget ran out.
    `outcomes` preserves `tasks`' order regardless of completion order, so
    the caller's audit trail and candidate ordering are deterministic even
    though the work itself runs concurrently.
    """
    if not tasks:
        return [], False

    outcomes: list[Optional[SearchOutcome]] = [None] * len(tasks)
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        future_to_index = {
            executor.submit(_search_safe, source, query): i
            for i, (query, source) in enumerate(tasks)
        }
        remaining = max(0.0, deadline - time.monotonic())
        done, not_done = wait(future_to_index, timeout=remaining)

        for future in done:
            index = future_to_index[future]
            query, source = tasks[index]
            try:
                outcomes[index] = future.result()
            except Exception as exc:  # noqa: BLE001 - belt-and-suspenders
                log.exception(
                    "retrieval: unexpected error collecting result for %r on %r",
                    query.terms,
                    source.id,
                )
                outcomes[index] = SearchOutcome(
                    record=QueryRecord(
                        source=source.id,
                        terms=query.terms,
                        scope=query.scope,
                        mode=query.mode,
                        venues=query.venues,
                        year_start=query.year_start,
                        year_end=query.year_end,
                        label=query.label,
                        error=f"internal error: {exc}",
                    )
                )

        for future in not_done:
            future.cancel()
            index = future_to_index[future]
            query, source = tasks[index]
            log.warning(
                "retrieval: budget of %ss exceeded — skipping query %r on %r",
                RETRIEVAL_BUDGET_S,
                query.terms,
                source.id,
            )
        return outcomes, bool(not_done)
    finally:
        # wait=False: do not block the caller on threads we already gave up
        # waiting for (e.g. econlit's ~45s cold-start timeout) once the
        # budget is spent. Returning promptly matters more than these
        # orphaned calls completing; their results are discarded regardless.
        executor.shutdown(wait=False)


def _empty_result(reason: str) -> RetrievalResult:
    log.exception("retrieval: %s", reason)
    return RetrievalResult(retrieved_at=datetime.now(timezone.utc).isoformat())


def retrieve(
    extraction: Extraction,
    sources: Optional[Sequence[EvidenceSource]] = None,
    limit: int = 25,
    max_enrich: int = 30,
) -> RetrievalResult:
    """Run the full retrieval pipeline for one concept note.

    Never raises and never returns `None` — see the module docstring. Every
    failure mode degrades to a valid `RetrievalResult`, in the worst case one
    with `candidates=[]` (`result.usable` is `False`), so the caller can
    always proceed with the research run this accelerates.
    """
    try:
        start = time.monotonic()
        deadline = start + RETRIEVAL_BUDGET_S

        active_sources = list(sources) if sources is not None else list_sources()
        available_sources = [s for s in active_sources if s.available()]

        try:
            elite_venues = _load_elite_venues()
        except Exception:  # noqa: BLE001 - venue list is informational only
            log.exception("retrieval: failed to load ELITE_JOURNALS")
            elite_venues = ()

        static_covered = sorted(
            {v for s in available_sources for v in s.covered_venues}
        )
        static_uncovered = sorted(v for v in elite_venues if v not in static_covered)

        try:
            queries = build_queries(
                extraction,
                covered_venues=static_covered,
                uncovered_venues=static_uncovered,
            )
        except Exception:  # noqa: BLE001 - build_queries claims never to raise
            log.exception("retrieval: build_queries raised unexpectedly")
            queries = []

        tasks: list[tuple[EvidenceQuery, EvidenceSource]] = [
            (query, source)
            for query in queries
            for source in _route_query(query, active_sources)
        ]

        outcomes, truncated = _run_queries(tasks, deadline)

        all_candidates: list[Candidate] = []
        query_records: list[QueryRecord] = []
        attempt_count: dict[str, int] = {}
        success_count: dict[str, int] = {}

        for (query, source), outcome in zip(tasks, outcomes):
            if outcome is None:
                continue  # never ran — budget truncation, see _run_queries
            attempt_count[source.id] = attempt_count.get(source.id, 0) + 1
            if outcome.record is not None:
                query_records.append(outcome.record)
            if outcome.ok:
                success_count[source.id] = success_count.get(source.id, 0) + 1
            all_candidates.extend(outcome.candidates)

        if truncated:
            skipped = sum(1 for o in outcomes if o is None)
            query_records.append(
                QueryRecord(
                    source="retrieval",
                    terms="",
                    scope="all",
                    mode="stemmed",
                    label="budget truncation",
                    error=(
                        f"retrieval budget of {RETRIEVAL_BUDGET_S}s exceeded; "
                        f"{skipped} of {len(tasks)} queued source queries were "
                        "skipped so the pipeline could keep moving"
                    ),
                )
            )

        total_seen = len(all_candidates)

        try:
            merged = merge_candidates(all_candidates)
        except Exception:  # noqa: BLE001 - merge_candidates claims never to raise
            log.exception("retrieval: merge_candidates raised unexpectedly")
            merged = list(all_candidates)

        openalex_source = next(
            (
                s
                for s in active_sources
                if isinstance(s, OpenAlexSource) and s.available()
            ),
            None,
        )
        if openalex_source is not None:
            try:
                enriched, enrich_notes = enrich(
                    merged, openalex_source, max_lookups=max_enrich
                )
                for note in enrich_notes:
                    log.debug("retrieval: enrichment note: %s", note)
            except Exception:  # noqa: BLE001 - enrich claims never to raise
                log.exception("retrieval: enrichment raised unexpectedly")
                enriched = merged
        else:
            log.info(
                "retrieval: no available OpenAlexSource among configured "
                "sources; skipping enrichment"
            )
            enriched = merged

        try:
            ranked = rank(enriched, extraction, limit=limit)
        except Exception:  # noqa: BLE001 - rank claims never to raise
            log.exception("retrieval: rank raised unexpectedly")
            ranked = list(enriched)[:limit]

        # Coverage is reported from what the candidate list ACTUALLY CONTAINS,
        # not from what the sources could theoretically reach.
        #
        # The first version of this used the union of `source.covered_venues`,
        # which produced an empty `uncovered_venues` on a live run: OpenAlex
        # declares the five development journals because it *can* filter by
        # their ISSNs, so every elite venue looked covered — while the returned
        # candidate list held zero papers from any of them. That silently
        # disabled the anti-narrowing disclosure, which is the one thing
        # standing between "retrieval guides the agent" and "retrieval blinds
        # it". Declared reach is a promise; venues present in the results are a
        # fact, and only the fact is safe to show the agent.
        venues_in_results = {
            v.strip().lower() for c in ranked for v in c.all_venues if v.strip()
        }

        def _represented(venue: str) -> bool:
            needle = venue.strip().lower()
            return any(needle in got or got in needle for got in venues_in_results)

        covered_venues = sorted(v for v in elite_venues if _represented(v))
        uncovered_venues = sorted(v for v in elite_venues if not _represented(v))

        sources_ok = sorted(
            s.id for s in active_sources if success_count.get(s.id, 0) > 0
        )
        sources_failed = sorted(
            s.id
            for s in active_sources
            if attempt_count.get(s.id, 0) > 0 and success_count.get(s.id, 0) == 0
        )

        queries_sorted = sorted(
            query_records, key=lambda r: (r.source, r.terms, r.scope, r.mode)
        )

        return RetrievalResult(
            candidates=ranked,
            queries=queries_sorted,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            sources_ok=sources_ok,
            sources_failed=sources_failed,
            covered_venues=covered_venues,
            uncovered_venues=uncovered_venues,
            total_seen=total_seen,
        )
    except Exception:  # noqa: BLE001 - the backstop: retrieve() must never raise
        return _empty_result("retrieve() failed unexpectedly; returning empty result")
