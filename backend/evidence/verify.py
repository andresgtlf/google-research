"""Existence check for citations — an accessibility signal, not a truth verdict.

Deep-research agents occasionally produce plausible-looking citations that
turn out not to check out. This module looks up every DOI it is given
against OpenAlex and reports whether OpenAlex has a matching record.

The critical framing point: a DOI that does *not* resolve in OpenAlex is
**not** proof that the underlying paper is fabricated or hallucinated.
OpenAlex's coverage has real gaps that have nothing to do with whether a
citation is genuine — the paper may be too recent to be indexed yet, it may
be a working paper or preprint outside OpenAlex's scope, or the DOI may be a
real one that is simply malformed in the report. Treating "not found" as
"fake" would misinform a grant reviewer and could unfairly cast doubt on a
real paper and its authors. So both this module's return values and its
rendered markdown describe an unresolved DOI only as "could not be verified
— check manually," and deliberately avoid words like "fabricated" or
"hallucinated" anywhere in reviewer-facing output.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from .base import EvidenceSource

log = logging.getLogger(__name__)

_UNVERIFIED_NOTE = (
    "Could not be verified — check manually. OpenAlex not resolving this DOI "
    "does not mean the paper doesn't exist: it may be too recent, a working "
    "paper outside OpenAlex's coverage, or a real DOI that is malformed here."
)


@dataclass(frozen=True)
class CitationCheck:
    """One DOI's existence check against OpenAlex."""

    doi: str
    exists: bool
    title: str = ""
    year: Optional[int] = None
    citations: Optional[int] = None
    oa_url: str = ""
    replication_url: str = ""
    note: str = ""


def _safe_lookup_by_doi(source: EvidenceSource, doi: str):
    try:
        return source.lookup_by_doi(doi)
    except Exception as exc:  # a source must never take down verification
        log.warning("verify: lookup_by_doi failed for %s: %s", doi, exc)
        return None


def verify_citations(
    dois: Sequence[str],
    openalex: Optional[EvidenceSource] = None,
    econlit: Optional[EvidenceSource] = None,
    max_lookups: int = 30,
) -> list[CitationCheck]:
    """Check each DOI against OpenAlex. Never raises.

    `econlit` is accepted for interface symmetry with `resolve_k.py` and
    future use, but econlit has no DOI-lookup capability (see
    `EvidenceSource.lookup_by_doi`'s default), so only `openalex` drives the
    result here.
    """
    del econlit  # currently unused — see docstring
    checks: list[CitationCheck] = []
    budget = max_lookups
    seen: set[str] = set()

    for doi in dois:
        if not doi:
            continue
        key = doi.lower()
        if key in seen:
            continue
        seen.add(key)

        if openalex is None:
            checks.append(
                CitationCheck(
                    doi=doi,
                    exists=False,
                    note="No verification source available. " + _UNVERIFIED_NOTE,
                )
            )
            continue

        if budget <= 0:
            checks.append(
                CitationCheck(
                    doi=doi,
                    exists=False,
                    note="Lookup budget exhausted. " + _UNVERIFIED_NOTE,
                )
            )
            continue

        budget -= 1
        candidate = _safe_lookup_by_doi(openalex, doi)
        if candidate is not None and (candidate.title or candidate.doi):
            checks.append(
                CitationCheck(
                    doi=doi,
                    exists=True,
                    title=candidate.title,
                    year=candidate.year,
                    citations=candidate.citations,
                    oa_url=candidate.oa_url,
                    replication_url=candidate.replication_url,
                )
            )
        else:
            checks.append(
                CitationCheck(doi=doi, exists=False, note=_UNVERIFIED_NOTE)
            )

    return checks


def render_verification_markdown(checks: Sequence[CitationCheck]) -> str:
    """Reviewer-facing markdown. Never implies a bad match means fabrication."""
    if not checks:
        return ""

    verified = [c for c in checks if c.exists]
    unverified = [c for c in checks if not c.exists]

    lines: list[str] = [
        f"**Automated citation check:** {len(verified)} of {len(checks)} "
        "citation(s) were found in OpenAlex.",
        "",
    ]

    if unverified:
        lines.append(
            "The citations below could not be confirmed against OpenAlex. "
            "This is not evidence that a citation is wrong — OpenAlex's "
            "coverage has gaps (very recent work, working papers, or a DOI "
            "typo can all cause this). Please check these manually:"
        )
        lines.append("")
        for c in unverified:
            note = c.note or "Could not be verified — check manually."
            lines.append(f"- `{c.doi}` — {note}")
        lines.append("")

    if verified:
        lines.append("### Verified citations")
        lines.append("")
        for c in verified:
            extra = []
            if c.year:
                extra.append(str(c.year))
            if c.citations is not None:
                extra.append(f"{c.citations} citations")
            meta = f" ({', '.join(extra)})" if extra else ""
            lines.append(f"- `{c.doi}` — {c.title or '(title unavailable)'}{meta}")
            if c.oa_url:
                lines.append(f"  - Open access: {c.oa_url}")
        lines.append("")

    return "\n".join(lines).strip()
