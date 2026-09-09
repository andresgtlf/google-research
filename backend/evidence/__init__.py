"""Paper-retrieval layer: query construction, sources, dedupe, and ranking.

Extends the bare package marker with a source registry mirroring
`backend/providers/__init__.py`'s provider registry: a dict of id -> instance,
plus `get_source`/`list_sources` lookups. `retrieval.py` (the orchestrator)
uses `list_sources()` as its default when the caller does not pass an explicit
`sources` sequence.
"""

from .base import (
    Candidate,
    EvidenceQuery,
    EvidenceSource,
    QueryRecord,
    RetrievalResult,
    SearchOutcome,
)
from .econlit import EconlitSource
from .openalex import OpenAlexSource

SOURCES: dict[str, EvidenceSource] = {
    s.id: s for s in (EconlitSource(), OpenAlexSource())
}


def get_source(source_id: str) -> EvidenceSource:
    if source_id not in SOURCES:
        raise ValueError(f"Unknown evidence source: {source_id}")
    return SOURCES[source_id]


def list_sources() -> list[EvidenceSource]:
    return list(SOURCES.values())


__all__ = [
    "Candidate",
    "EvidenceQuery",
    "EvidenceSource",
    "QueryRecord",
    "RetrievalResult",
    "SearchOutcome",
    "EconlitSource",
    "OpenAlexSource",
    "SOURCES",
    "get_source",
    "list_sources",
]
