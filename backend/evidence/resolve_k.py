"""Resolve Section L's paywalled papers to free versions, where one exists.

A paywalled journal article very often has a free NBER/IZA working-paper
twin — the same study, published twice. This module tries, cheapest and
most-certain first, to recover that free twin so a grant reviewer doesn't
have to go hunting manually:

1. If the paper carries a DOI, ask OpenAlex for that DOI's open-access URL.
2. Otherwise (or if step 1 finds nothing), search econlit by exact title for
   a same-title record published as a working paper. NBER DOIs
   (`10.3386/wNNNNN`) resolve to a known-free page at
   `https://www.nber.org/papers/wNNNNN`, so that URL is constructed directly.
3. If the working-paper twin has a non-NBER DOI, try OpenAlex on *that* DOI
   for an open-access URL.

Title matching is exact after normalization (lowercase, no accents/
punctuation, collapsed whitespace) — never fuzzy. Telling a reviewer a paper
is freely available when it is not is worse than saying nothing, so any
uncertainty resolves to "unresolved" with an explanatory note rather than a
guess.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from ..report_parse import PaywalledPaper
from .base import Candidate, EvidenceSource

log = logging.getLogger(__name__)

# Venue substrings (case-insensitive) that mark a record as a working paper
# rather than the peer-reviewed version of record. Mirrors dedupe.py's list.
WORKING_PAPER_VENUE_MARKERS: tuple[str, ...] = (
    "NBER",
    "WORKING PAPER",
    "IZA",
    "DISCUSSION PAPER",
)

_NBER_DOI_RE = re.compile(r"^10\.3386/(w\d+)$", re.IGNORECASE)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Resolution:
    """The outcome of trying to find a free version of one paywalled paper."""

    paper: PaywalledPaper
    found_free_version: bool
    free_url: str = ""
    free_doi: str = ""
    free_venue: str = ""
    note: str = ""


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    decomposed = unicodedata.normalize("NFKD", title)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    no_punct = _PUNCT_RE.sub("", without_accents.lower())
    return _WHITESPACE_RE.sub(" ", no_punct).strip()


def _is_working_paper_venue(venue: str) -> bool:
    if not venue:
        return False
    upper = venue.upper()
    return any(marker in upper for marker in WORKING_PAPER_VENUE_MARKERS)


def _nber_url_from_doi(doi: str) -> str:
    match = _NBER_DOI_RE.match((doi or "").strip())
    if not match:
        return ""
    return f"https://www.nber.org/papers/{match.group(1).lower()}"


def _safe_lookup_by_doi(source: EvidenceSource, doi: str) -> Optional[Candidate]:
    try:
        return source.lookup_by_doi(doi)
    except Exception as exc:  # a source must never take down resolution
        log.warning("resolve_k: lookup_by_doi failed for %s: %s", doi, exc)
        return None


def _safe_find_by_title(source: EvidenceSource, title: str):
    try:
        return source.find_by_title(title)
    except Exception as exc:
        log.warning("resolve_k: find_by_title failed for %r: %s", title, exc)
        return None


def _find_confident_twin(
    paper_title: str, candidates: Sequence[Candidate]
) -> Optional[Candidate]:
    """A same-title, working-paper-venue candidate — exact match only."""
    target = _normalize_title(paper_title)
    if not target:
        return None
    for candidate in candidates:
        if _normalize_title(candidate.title) != target:
            continue
        if not _is_working_paper_venue(candidate.venue):
            continue
        return candidate
    return None


# A publisher's only "open access" file is sometimes the online appendix rather
# than the article. Verified case: OpenAlex reports 10.3982/ecta17945 (Egger et
# al., Econometrica 2022) as is_oa=True, oa_status=bronze, version=
# publishedVersion, but the URL it hands back is
# ".../supp/ecta200500-sup-0001-onlineappendix.pdf". Presenting that to a
# reviewer as "the free version" is worse than saying nothing, because they
# click it, get 40 pages of robustness tables, and lose trust in every other
# link in the report. When the only OA link looks like supplementary material we
# keep searching for a real full-text version instead of declaring success.
_SUPPLEMENT_URL_MARKERS = (
    "onlineappendix",
    "online-appendix",
    "supplement",
    "-supp-",
    "/supp/",
    "_supp_",
    "appendix",
)


def _looks_like_supplement(url: str) -> bool:
    return any(marker in url.lower() for marker in _SUPPLEMENT_URL_MARKERS)


def _resolve_one(
    paper: PaywalledPaper,
    econlit: Optional[EvidenceSource],
    openalex: Optional[EvidenceSource],
    budget: list[int],
) -> Resolution:
    # Step 1: the paper's own DOI -> OpenAlex open-access URL.
    weak_oa_url = ""
    if paper.doi and openalex is not None and budget[0] > 0:
        budget[0] -= 1
        candidate = _safe_lookup_by_doi(openalex, paper.doi)
        if candidate is not None and candidate.oa_url:
            if _looks_like_supplement(candidate.oa_url):
                # Hold it as a fallback and try for the real article first.
                weak_oa_url = candidate.oa_url
            else:
                return Resolution(
                    paper=paper,
                    found_free_version=True,
                    free_url=candidate.oa_url,
                    free_doi=candidate.doi or paper.doi,
                    free_venue=candidate.venue,
                    note="Free full text found via OpenAlex's open-access link for this paper's own DOI.",
                )

    # Step 2 & 3: title -> econlit working-paper twin.
    if paper.title and econlit is not None and budget[0] > 0:
        budget[0] -= 1
        outcome = _safe_find_by_title(econlit, paper.title)
        if outcome is not None and outcome.ok and outcome.candidates:
            twin = _find_confident_twin(paper.title, outcome.candidates)
            if twin is not None and twin.doi:
                nber_url = _nber_url_from_doi(twin.doi)
                if nber_url:
                    return Resolution(
                        paper=paper,
                        found_free_version=True,
                        free_url=nber_url,
                        free_doi=twin.doi,
                        free_venue=twin.venue,
                        note=f"Free NBER working-paper twin found by exact title match ({twin.venue}).",
                    )
                if openalex is not None and twin.doi != paper.doi and budget[0] > 0:
                    budget[0] -= 1
                    oa_candidate = _safe_lookup_by_doi(openalex, twin.doi)
                    if oa_candidate is not None and oa_candidate.oa_url:
                        return Resolution(
                            paper=paper,
                            found_free_version=True,
                            free_url=oa_candidate.oa_url,
                            free_doi=twin.doi,
                            free_venue=twin.venue,
                            note=(
                                "Free version found via OpenAlex's open-access link "
                                f"for the working-paper twin ({twin.venue})."
                            ),
                        )
                return _with_weak_fallback(
                    paper,
                    weak_oa_url,
                    f"Found a same-title working-paper record ({twin.venue}) but "
                    "could not confirm a free-access link for it.",
                )
            return _with_weak_fallback(
                paper,
                weak_oa_url,
                "Econlit returned title matches, but none was a confident "
                "same-title working-paper twin.",
            )

    return _with_weak_fallback(
        paper,
        weak_oa_url,
        "No evidence source was available, or no lookup budget remained.",
    )


def _with_weak_fallback(
    paper: PaywalledPaper, weak_oa_url: str, note: str
) -> Resolution:
    """Fall back to a supplement-looking OA link, labelled for what it is.

    Better than discarding it — the appendix is often still useful, and a
    reviewer who knows what they are clicking is not misled. It is deliberately
    NOT counted as `found_free_version`, so the summary count never overstates
    how many papers are actually readable.
    """
    if not weak_oa_url:
        return Resolution(paper=paper, found_free_version=False, note=note)
    return Resolution(
        paper=paper,
        found_free_version=False,
        free_url=weak_oa_url,
        note=(
            f"{note} The publisher does offer a free file for this DOI, but it "
            f"looks like supplementary material rather than the article "
            f"itself: {weak_oa_url}"
        ),
    )


def resolve_paywalled(
    papers: Sequence[PaywalledPaper],
    econlit: Optional[EvidenceSource] = None,
    openalex: Optional[EvidenceSource] = None,
    max_lookups: int = 20,
) -> list[Resolution]:
    """Try to find a free version of each paywalled paper. Never raises."""
    budget = [max_lookups]
    resolutions: list[Resolution] = []
    for paper in papers:
        if not paper.title and not paper.doi:
            continue
        try:
            resolutions.append(_resolve_one(paper, econlit, openalex, budget))
        except Exception as exc:  # one bad paper must not sink the batch
            log.warning(
                "resolve_k: unexpected failure resolving %r: %s", paper.title, exc
            )
            resolutions.append(
                Resolution(
                    paper=paper,
                    found_free_version=False,
                    note=f"Resolution failed unexpectedly: {exc}",
                )
            )
    return resolutions


def render_resolutions_markdown(resolutions: Sequence[Resolution]) -> str:
    """A reviewer-facing markdown section summarizing free-version recovery."""
    if not resolutions:
        return ""

    resolved = [r for r in resolutions if r.found_free_version]
    unresolved = [r for r in resolutions if not r.found_free_version]

    lines: list[str] = [
        f"**Automated free-version check:** {len(resolved)} of {len(resolutions)} "
        "paywalled paper(s) have a free version available.",
        "",
    ]

    if resolved:
        lines.append("### Free versions found")
        lines.append("")
        for r in resolved:
            title = r.paper.title or "(untitled)"
            lines.append(f"- **{title}**")
            venue_bit = f"{r.free_venue} — " if r.free_venue else ""
            lines.append(f"  - Free version: {venue_bit}{r.free_url}")
            if r.note:
                lines.append(f"  - {r.note}")
        lines.append("")

    if unresolved:
        lines.append("### Still requires manual retrieval")
        lines.append("")
        for r in unresolved:
            title = r.paper.title or "(untitled)"
            doi_bit = f" ({r.paper.doi})" if r.paper.doi else ""
            lines.append(f"- **{title}**{doi_bit}")
            note = r.note or "No free version could be confirmed automatically."
            lines.append(f"  - {note}")
        lines.append("")

    return "\n".join(lines).strip()
