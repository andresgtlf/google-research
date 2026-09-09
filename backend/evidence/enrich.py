"""Fill in the gaps econlit leaves behind, one DOI lookup at a time.

Econlit is missing an abstract on ~93% of rows and never returns a URL, so a
candidate list built from it alone gives a reviewer nothing to click on and
no context to judge relevance from a snippet. This module closes both gaps by
looking up each incomplete candidate on OpenAlex and merging the two records
(see `Candidate.merged_with` in `base.py`).

Each lookup is one HTTP call and one OpenAlex rate-limit credit, so the walk
is capped at `max_lookups` and skips anything already complete or lacking a
DOI to look up by.
"""

import logging
from typing import Sequence

from .base import Candidate
from .openalex import OpenAlexSource

log = logging.getLogger(__name__)


def _needs_enrichment(candidate: Candidate) -> bool:
    return not candidate.abstract or not candidate.oa_url


def enrich(
    candidates: Sequence[Candidate],
    source: OpenAlexSource,
    max_lookups: int = 30,
) -> tuple[list[Candidate], list[str]]:
    """Enrich candidates missing an abstract or an open-access URL.

    Returns `(enriched_candidates, notes)` with candidates in the same order
    as the input. A candidate is left unchanged, with a note appended, when
    it has no DOI to look up by, the lookup cap has been reached, or the
    lookup itself fails — this function never raises.
    """
    enriched: list[Candidate] = []
    notes: list[str] = []
    lookups_done = 0

    for candidate in candidates:
        if not _needs_enrichment(candidate):
            enriched.append(candidate)
            continue

        if not candidate.doi:
            enriched.append(candidate)
            continue

        if lookups_done >= max_lookups:
            notes.append(
                f"skipped enrichment for '{candidate.title}': lookup cap "
                f"({max_lookups}) reached"
            )
            enriched.append(candidate)
            continue

        lookups_done += 1
        try:
            match = source.lookup_by_doi(candidate.doi)
        except Exception as exc:  # noqa: BLE001 - enrichment must never raise
            log.warning(
                "enrich: lookup failed for '%s' (%s): %s",
                candidate.title,
                candidate.doi,
                exc,
            )
            notes.append(f"enrichment failed for '{candidate.title}': {exc}")
            enriched.append(candidate)
            continue

        if match is None:
            notes.append(
                f"no OpenAlex match for '{candidate.title}' ({candidate.doi})"
            )
            enriched.append(candidate)
            continue

        enriched.append(candidate.merged_with(match))

    return enriched, notes
