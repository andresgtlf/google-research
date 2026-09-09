"""OpenAlex — the enrichment source that fixes econlit's missing metadata.

Econlit never returns a URL and is missing an abstract ~93% of the time, so
it is useless on its own for pointing a reviewer at something they can read.
OpenAlex supports anonymous trial usage and API-key authentication for larger
budgets. OPENALEX_API_KEY is sent in a bearer header so it never appears in
request URLs or exception messages.

Like `econlit.py`, every public method returns rather than raises: retrieval
is an accelerator, and OpenAlex being unreachable must not sink a run.
"""

import logging
import os
from typing import Any, Optional

import requests

from .base import Candidate, EvidenceQuery, EvidenceSource, QueryRecord, SearchOutcome

log = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org"

_USER_AGENT = "GTLF-Research-Evidence-Retrieval/1.0"

TIMEOUT_S = int(os.environ.get("OPENALEX_TIMEOUT_S", "20"))

_MAILTO = os.environ.get("OPENALEX_MAILTO", "")

# ISSNs verified by hand against OpenAlex's `primary_location.source.issn`.
# Omitted rather than guessed for anything uncertain: a wrong ISSN silently
# returns zero results, which is worse than no venue filter at all.
VENUE_ISSNS: dict[str, str] = {
    "Journal of Development Economics": "0304-3878",
    "World Development": "0305-750X",
    "Economic Development and Cultural Change": "0013-0079",
    "Journal of Human Resources": "0022-166X",
    "Journal of Labor Economics": "0734-306X",
    "American Economic Review": "0002-8282",
    "Econometrica": "0012-9682",
    "The Quarterly Journal of Economics": "0033-5533",
    "Journal of Political Economy": "0022-3808",
    "The Review of Economic Studies": "0034-6527",
}


def abstract_from_inverted_index(index: Optional[dict[str, list[int]]]) -> str:
    """Reconstruct plain text from OpenAlex's `abstract_inverted_index`.

    The structure maps each word to the list of positions it occupies, e.g.
    `{"The": [0], "cat": [1]}` -> "The cat". This is what fills in econlit's
    abstract gap once OpenAlex is used as an enrichment source.
    """
    if not index:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for pos in positions:
            if isinstance(pos, int):
                positioned.append((pos, word))
    if not positioned:
        return ""
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned)


def _normalize_doi(raw: Any) -> str:
    """OpenAlex returns DOIs as full URLs; the rest of the pipeline uses bare
    DOIs (see `Candidate.doi`)."""
    if not isinstance(raw, str) or not raw:
        return ""
    prefix = "https://doi.org/"
    if raw.startswith(prefix):
        return raw[len(prefix) :]
    return raw


def _work_to_candidate(work: dict[str, Any]) -> Candidate:
    """Map one OpenAlex work object to a `Candidate`. Defensive against
    missing/malformed keys, since this feeds `lookup_by_doi` results into
    `merged_with` without any other validation."""
    authorships = work.get("authorships") or []
    authors: list[str] = []
    if isinstance(authorships, list):
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author") or {}
            name = author.get("display_name") if isinstance(author, dict) else None
            if isinstance(name, str) and name:
                authors.append(name)

    primary_location = work.get("primary_location") or {}
    source = (
        primary_location.get("source") if isinstance(primary_location, dict) else None
    )
    venue = ""
    if isinstance(source, dict):
        venue = str(source.get("display_name") or "")

    open_access = work.get("open_access") or {}
    is_oa: Optional[bool] = None
    oa_url = ""
    if isinstance(open_access, dict):
        is_oa_raw = open_access.get("is_oa")
        is_oa = is_oa_raw if isinstance(is_oa_raw, bool) else None
        oa_url = str(open_access.get("oa_url") or "")

    year_raw = work.get("publication_year")
    year = year_raw if isinstance(year_raw, int) else None

    citations_raw = work.get("cited_by_count")
    citations = citations_raw if isinstance(citations_raw, int) else None

    return Candidate(
        title=str(work.get("title") or ""),
        authors=tuple(authors),
        year=year,
        venue=venue,
        doi=_normalize_doi(work.get("doi")),
        abstract=abstract_from_inverted_index(work.get("abstract_inverted_index")),
        citations=citations,
        is_oa=is_oa,
        oa_url=oa_url,
        sources=("openalex",),
    )


class OpenAlexSource(EvidenceSource):
    """Scholarly search and DOI metadata with optional API authentication."""

    id = "openalex"
    label = "OpenAlex"
    covered_venues: tuple[str, ...] = tuple(VENUE_ISSNS.keys())

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers["User-Agent"] = _USER_AGENT
        api_key = os.environ.get("OPENALEX_API_KEY", "")
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"

    def _filter_field(self, query: EvidenceQuery) -> str:
        return "fulltext.search" if query.scope == "full_text" else (
            "title_and_abstract.search"
        )

    def _build_filters(self, query: EvidenceQuery) -> str:
        filters = [f"{self._filter_field(query)}:{query.terms}"]

        if query.year_start is not None and query.year_end is not None:
            filters.append(f"publication_year:{query.year_start}-{query.year_end}")
        elif query.year_start is not None:
            filters.append(f"publication_year:{query.year_start}-2100")
        elif query.year_end is not None:
            filters.append(f"publication_year:2000-{query.year_end}")

        issns = [VENUE_ISSNS[v] for v in query.venues if v in VENUE_ISSNS]
        if issns:
            filters.append(f"primary_location.source.issn:{'|'.join(sorted(set(issns)))}")

        return ",".join(filters)

    def search(self, query: EvidenceQuery) -> SearchOutcome:
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

        params = {
            "filter": self._build_filters(query),
            "per_page": query.limit,
            "mailto": _MAILTO,
        }

        try:
            response = self._session.get(
                f"{_BASE_URL}/works", params=params, timeout=TIMEOUT_S
            )
            if response.status_code == 429:
                log.warning("openalex: rate limited for %r", query.terms)
                return SearchOutcome(
                    record=QueryRecord(
                        **record_base, error="rate limited (429) by OpenAlex"
                    )
                )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            log.warning("openalex: request failed for %r: %s", query.terms, exc)
            return SearchOutcome(
                record=QueryRecord(**record_base, error=f"request failed: {exc}")
            )
        except ValueError as exc:
            log.warning("openalex: non-JSON response for %r: %s", query.terms, exc)
            return SearchOutcome(
                record=QueryRecord(**record_base, error=f"invalid response: {exc}")
            )

        try:
            if not isinstance(payload, dict):
                raise TypeError(f"expected object, got {type(payload).__name__}")
            rows = payload.get("results") or []
            candidates = tuple(
                _work_to_candidate(row) for row in rows if isinstance(row, dict)
            )
            meta = payload.get("meta") or {}
            total = meta.get("count") if isinstance(meta, dict) else None
            total_results = total if isinstance(total, int) else len(candidates)
        except (TypeError, KeyError, AttributeError) as exc:
            log.warning("openalex: malformed payload for %r: %s", query.terms, exc)
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

    def lookup_by_doi(self, doi: str) -> Optional[Candidate]:
        """Fetch one work by DOI. Returns None on any failure or malformed
        response rather than raising — see class docstring."""
        bare_doi = _normalize_doi(doi) or doi
        if not bare_doi:
            return None
        try:
            response = self._session.get(
                f"{_BASE_URL}/works/https://doi.org/{bare_doi}",
                params={"mailto": _MAILTO},
                timeout=TIMEOUT_S,
            )
            if response.status_code == 429:
                log.warning("openalex: rate limited on DOI lookup for %s", doi)
                return None
            response.raise_for_status()
            work = response.json()
        except requests.RequestException as exc:
            log.warning("openalex: DOI lookup failed for %s: %s", doi, exc)
            return None
        except ValueError as exc:
            log.warning("openalex: non-JSON DOI response for %s: %s", doi, exc)
            return None

        try:
            if not isinstance(work, dict):
                raise TypeError(f"expected object, got {type(work).__name__}")
            return _work_to_candidate(work)
        except (TypeError, KeyError, AttributeError) as exc:
            log.warning("openalex: malformed DOI response for %s: %s", doi, exc)
            return None
