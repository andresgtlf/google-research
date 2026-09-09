"""Merge records of the same study published more than once.

A journal article and its NBER/IZA working-paper twin are the same study,
not two studies. If they occupy two slots in a candidate list that is
capped before it reaches the agent, the agent sees an evidence base
narrower than the one that actually exists — one real study consumed two of
its limited slots. This module finds those twins and folds them into one
`Candidate` via `Candidate.merged_with` (see `base.py`), so the cap is spent
on distinct studies.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable
from itertools import combinations
from typing import Optional

from .base import Candidate

logger = logging.getLogger(__name__)

# An NBER/IZA paper often precedes the journal version by 2-3 years, so a
# strict equality requirement on `year` would miss real twins. 4 years is
# generous enough to cover that gap without being so wide it starts folding
# together genuinely different studies that happen to share a title.
YEAR_TOLERANCE = 4

# Venue substrings (case-insensitive) that mark a record as a working paper
# rather than the peer-reviewed version of record. Used to decide which half
# of a merged pair keeps `doi`/`venue` and which becomes an `alt_*`.
WORKING_PAPER_VENUE_MARKERS: tuple[str, ...] = (
    "NBER",
    "Working Paper",
    "IZA",
    "Discussion Paper",
)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_title(title: str, strip_subtitle: bool = False) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace.

    `strip_subtitle` drops everything after the first colon — used only as a
    secondary pass (see `_group_by_title`), because two studies in different
    countries can otherwise share a stem before the colon (e.g. "Effects of
    X: Evidence from Kenya" vs "...: Evidence from Peru") and the year-
    tolerance check is the only guard against merging those.
    """
    text = title.split(":", 1)[0] if strip_subtitle and ":" in title else title
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    no_punct = _PUNCT_RE.sub("", without_accents.lower())
    return _WHITESPACE_RE.sub(" ", no_punct).strip()


def _years_compatible(
    year_a: Optional[int], year_b: Optional[int], tolerance: int = YEAR_TOLERANCE
) -> bool:
    """True when nothing rules out these being the same study's two years.

    A missing year on either side can't disprove a match, so it is treated
    as compatible rather than blocking a merge that the title already
    supports — a deliberate, documented judgment call, not an oversight.
    """
    if year_a is None or year_b is None:
        return True
    return abs(year_a - year_b) <= tolerance


def _is_working_paper(venue: str) -> bool:
    lowered = venue.lower()
    return any(marker.lower() in lowered for marker in WORKING_PAPER_VENUE_MARKERS)


class _UnionFind:
    """Minimal disjoint-set over list indices, used to group twins found by
    independent passes (DOI, then title) into one merge group each."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, index: int) -> int:
        root = index
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[index] != root:
            self._parent[index], index = root, self._parent[index]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def _group_by_doi(candidates: list[Candidate], uf: _UnionFind) -> None:
    """Pass 1: exact DOI match, including a DOI appearing in another
    candidate's `alt_dois`."""
    doi_to_indices: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        for doi in candidate.all_dois:
            doi_to_indices.setdefault(doi, []).append(index)

    for indices in doi_to_indices.values():
        for other in indices[1:]:
            uf.union(indices[0], other)


def _group_by_title(candidates: list[Candidate], uf: _UnionFind) -> None:
    """Pass 2 (primary) + pass 3 (secondary, subtitle-stripped) normalized-
    title matching, each gated by year tolerance."""
    for strip_subtitle in (False, True):
        buckets: dict[str, list[int]] = {}
        for index, candidate in enumerate(candidates):
            key = _normalize_title(candidate.title, strip_subtitle=strip_subtitle)
            if key:
                buckets.setdefault(key, []).append(index)

        for indices in buckets.values():
            for a, b in combinations(indices, 2):
                if _years_compatible(candidates[a].year, candidates[b].year):
                    uf.union(a, b)


def _choose_base(group: list[Candidate]) -> tuple[Candidate, list[Candidate]]:
    """Pick the version-of-record to merge the rest into.

    Preferring a peer-reviewed candidate (not a working paper) as `self` in
    `merged_with` keeps its `doi`/`venue` in the primary slot, since
    `merged_with` keeps `self`'s populated fields first — the working
    paper's doi/venue end up in `alt_dois`/`alt_venues` instead, which is
    where the free full text usually lives anyway.
    """
    peer_reviewed = [
        c for c in group if c.venue and not _is_working_paper(c.venue)
    ]
    base = peer_reviewed[0] if peer_reviewed else group[0]
    rest = [c for c in group if c is not base]
    return base, rest


def merge_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Merge records that are the same study published more than once.

    Order of matching, most reliable first:
    1. Exact DOI match (including a DOI that appears in another record's
       `alt_dois`).
    2. Normalized-title match within a year tolerance, then the same check
       again with a trailing subtitle stripped as a secondary pass.

    Returns one `Candidate` per distinct study, in first-appearance order.
    """
    materialized = list(candidates)
    if not materialized:
        return []

    uf = _UnionFind(len(materialized))
    _group_by_doi(materialized, uf)
    _group_by_title(materialized, uf)

    groups: dict[int, list[int]] = {}
    for index in range(len(materialized)):
        groups.setdefault(uf.find(index), []).append(index)

    merged: list[Candidate] = []
    for first_index in sorted(groups, key=lambda root: groups[root][0]):
        member_indices = groups[first_index]
        members = [materialized[i] for i in member_indices]

        if len(members) == 1:
            merged.append(members[0])
            continue

        base, rest = _choose_base(members)
        combined = base
        for other in rest:
            combined = combined.merged_with(other)
        logger.debug(
            "dedupe: merged %d records into one study: %r",
            len(members),
            combined.title,
        )
        merged.append(combined)

    return merged
