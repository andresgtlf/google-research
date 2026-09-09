"""Pipeline entry points for the evidence layer — the only module jobs.py calls.

Everything here is optional, flagged, and failure-tolerant. The v6 lesson that
shaped this file is in `CHANGELOG-v6.md`: an expensive result must never be lost
to a step that runs after it. A research run costs real money and up to 75
minutes, so no function here may raise, and none may run before the report has
been persisted.

Two independent switches, because the two capabilities carry different risk:

- ``EVIDENCE_ENRICHMENT`` (default ON) — post-research work only. Resolves the
  paywalled list to free links and existence-checks the cited DOIs. It cannot
  change what the research agent said, so it ships enabled.

- ``EVIDENCE_SEEDING`` (default ON) — retrieve candidates before synthesis.
  Set EVIDENCE_SEEDING=0 for a provider-only comparison. Saved snapshots are
  replayable; fresh retrieval still needs benchmark recall evaluation.
"""

import logging
import os
from typing import Any, Optional

from ..report_parse import extract_dois, parse_paywalled_papers, parse_paywalled_section
from ..schemas import Extraction
from .base import RetrievalResult
from .econlit import EconlitSource
from .openalex import OpenAlexSource
from .resolve_k import render_resolutions_markdown, resolve_paywalled
from .retrieval import retrieve
from .verify import render_verification_markdown, verify_citations

log = logging.getLogger(__name__)

_TRUE = {"1", "true", "yes", "on"}


def seeding_enabled() -> bool:
    return os.environ.get("EVIDENCE_SEEDING", "1").strip().lower() in _TRUE


def enrichment_enabled() -> bool:
    return os.environ.get("EVIDENCE_ENRICHMENT", "1").strip().lower() in _TRUE


def _sources() -> tuple[EconlitSource, OpenAlexSource]:
    return EconlitSource(), OpenAlexSource()


def seed_candidates(extraction: Extraction) -> Optional[RetrievalResult]:
    """Retrieve pre-screened candidates, or None when seeding is off/unusable.

    Returning None rather than an empty result is deliberate: it makes
    `build_research_prompt` omit the candidate block entirely instead of telling
    the agent that a retrieval was attempted and found nothing, which would be
    misleading when seeding was simply switched off.
    """
    if not seeding_enabled():
        return None
    try:
        econlit, openalex = _sources()
        result = retrieve(extraction, sources=[econlit, openalex])
    except Exception:  # retrieve() is contractually safe; belt and braces
        log.exception("Candidate seeding failed; continuing without candidates")
        return None
    if not result.usable:
        log.warning(
            "Candidate seeding produced nothing (failed sources: %s)",
            ", ".join(result.sources_failed) or "none",
        )
    return result


def enrich_report(report_md: str) -> dict[str, Any]:
    """Resolve the paywalled list and existence-check cited DOIs.

    Never raises. Returns a dict that is safe to merge into the job's
    ``sections`` payload; on any failure the values are empty and the report is
    displayed exactly as the agent wrote it.
    """
    empty: dict[str, Any] = {
        "resolutions_markdown": "",
        "verification_markdown": "",
        "resolved_count": 0,
        "unresolved_count": 0,
        "unverified_dois": [],
        "enrichment_notes": [],
    }
    if not enrichment_enabled() or not report_md.strip():
        return empty

    notes: list[str] = []
    econlit, openalex = _sources()

    resolutions: list[Any] = []
    try:
        papers = parse_paywalled_papers(parse_paywalled_section(report_md))
        if papers:
            resolutions = resolve_paywalled(
                papers, econlit=econlit, openalex=openalex
            )
    except Exception:
        log.exception("Paywalled-paper resolution failed")
        notes.append("Could not check the paywalled list for free versions.")

    checks: list[Any] = []
    try:
        dois = extract_dois(report_md)
        if dois:
            checks = verify_citations(dois, openalex=openalex)
    except Exception:
        log.exception("Citation verification failed")
        notes.append("Could not verify the DOIs cited in the report.")

    resolved = [r for r in resolutions if r.found_free_version]
    return {
        "resolutions_markdown": (
            render_resolutions_markdown(resolutions) if resolutions else ""
        ),
        "verification_markdown": (
            render_verification_markdown(checks) if checks else ""
        ),
        "resolved_count": len(resolved),
        "unresolved_count": len(resolutions) - len(resolved),
        "unverified_dois": [c.doi for c in checks if not c.exists],
        "enrichment_notes": notes,
    }


def summarize_enrichment(enrichment: dict[str, Any]) -> list[str]:
    """Short human-readable job events describing what enrichment achieved."""
    events: list[str] = []
    resolved = enrichment.get("resolved_count") or 0
    unresolved = enrichment.get("unresolved_count") or 0
    if resolved or unresolved:
        events.append(
            f"Paywalled list checked: {resolved} free version(s) located, "
            f"{unresolved} still need manual retrieval"
        )
    unverified = enrichment.get("unverified_dois") or []
    if unverified:
        events.append(
            f"{len(unverified)} cited DOI(s) could not be confirmed against "
            f"OpenAlex — flagged for manual checking, not treated as errors"
        )
    events.extend(enrichment.get("enrichment_notes") or [])
    return events
