"""Common interface for evidence sources — the paper-retrieval layer.

Mirrors the shape of `backend/providers/base.py`: an ABC plus concrete
implementations behind a registry. The difference is what failure means. A
research provider failing kills the run; an evidence source failing must not.
Retrieval is an *accelerator* for the agent's own search, so every source is
allowed to time out, error, or return nothing and the pipeline still produces a
report. That contract is enforced in `retrieval.py`, but it starts here: every
method returns an outcome object carrying an `error` string rather than raising.

A note on `Candidate`, because it drives everything downstream: one *study* is
one candidate. A journal article and its NBER working-paper twin are the same
study published twice, so they merge into a single Candidate with both DOIs
(see `dedupe.py`). Without that, one study eats two slots in a capped candidate
list and the agent sees an evidence base narrower than it really is.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Optional

# GitLab Foundation's mission is lifetime earnings, so "does the effect last"
# is not a refinement of the research question — it is the research question.
# Retrieval carries these so ranking can prefer studies that actually measure
# persistence over studies that measure a one-year bump. See ranking.py.
LONG_RUN_SIGNALS = (
    "long-term",
    "long term",
    "long-run",
    "long run",
    "follow-up",
    "follow up",
    "followup",
    "years later",
    "persistence",
    "persistent",
    "fade-out",
    "fade out",
    "decay",
    "durable",
    "lasting",
)

# Outcomes that count as income under the Foundation's mission. Used to score
# whether a candidate measures earnings at all, rather than measuring
# enrollment, test scores, or empowerment and being retrieved on topic overlap.
INCOME_OUTCOME_SIGNALS = (
    "earnings",
    "wage",
    "wages",
    "income",
    "profit",
    "profits",
    "revenue",
    "revenues",
    "consumption",
    "labor market outcome",
    "employment",
)


@dataclass(frozen=True)
class Candidate:
    """One study, however many times it was published."""

    title: str
    authors: tuple[str, ...] = ()
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""

    # Twin versions of the same study, merged by dedupe.py. `doi` holds the
    # version of record (journal if known); alt_* hold the recoverable
    # alternatives, which is usually where the free full text lives.
    alt_dois: tuple[str, ...] = ()
    alt_venues: tuple[str, ...] = ()

    abstract: str = ""
    citations: Optional[int] = None

    # Access. `oa_url` is the whole point of the enrichment step: econlit
    # returns a URL for 0% of rows, so without OpenAlex there is no link to
    # give a reviewer who wants to read the paper.
    is_oa: Optional[bool] = None
    oa_url: str = ""

    # Replication package status (openICPSR). The strongest single quality
    # signal available for free, and the one thing OpenAlex does not carry.
    replication_status: str = ""
    replication_url: str = ""

    # Provenance and scoring.
    sources: tuple[str, ...] = ()
    relevance: float = 0.0
    score: float = 0.0
    score_notes: tuple[str, ...] = ()

    @property
    def all_dois(self) -> tuple[str, ...]:
        return tuple(d for d in (self.doi, *self.alt_dois) if d)

    @property
    def all_venues(self) -> tuple[str, ...]:
        return tuple(v for v in (self.venue, *self.alt_venues) if v)

    @property
    def has_recoverable_full_text(self) -> bool:
        """True when a reviewer can actually read this without a subscription."""
        return bool(self.oa_url) or self.is_oa is True

    def merged_with(self, other: "Candidate") -> "Candidate":
        """Union two records of the same study, preferring populated fields.

        Field-by-field rather than record-level so a sparse econlit row and a
        rich OpenAlex row combine into one complete candidate instead of one
        winning outright.
        """
        venues = tuple(
            dict.fromkeys(v for v in (*self.all_venues, *other.all_venues) if v)
        )
        dois = tuple(dict.fromkeys(d for d in (*self.all_dois, *other.all_dois) if d))
        return replace(
            self,
            title=self.title or other.title,
            authors=self.authors or other.authors,
            year=self.year if self.year is not None else other.year,
            venue=venues[0] if venues else "",
            alt_venues=venues[1:],
            doi=dois[0] if dois else "",
            alt_dois=dois[1:],
            abstract=self.abstract or other.abstract,
            citations=(
                max(c for c in (self.citations, other.citations) if c is not None)
                if any(c is not None for c in (self.citations, other.citations))
                else None
            ),
            is_oa=self.is_oa if self.is_oa is not None else other.is_oa,
            oa_url=self.oa_url or other.oa_url,
            replication_status=self.replication_status or other.replication_status,
            replication_url=self.replication_url or other.replication_url,
            sources=tuple(dict.fromkeys((*self.sources, *other.sources))),
            relevance=max(self.relevance, other.relevance),
        )


@dataclass(frozen=True)
class EvidenceQuery:
    """One structured query. Recorded verbatim so the report can cite it."""

    terms: str
    scope: str = "all"  # all | title | abstract | full_text
    mode: str = "stemmed"  # stemmed | exact
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    venues: tuple[str, ...] = ()
    limit: int = 50
    label: str = ""  # why this query exists, e.g. "mechanism x country"


@dataclass(frozen=True)
class QueryRecord:
    """What a query actually did — the auditable half of Search Metadata."""

    source: str
    terms: str
    scope: str
    mode: str
    venues: tuple[str, ...] = ()
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    total_results: Optional[int] = None
    returned: int = 0
    label: str = ""
    error: str = ""


@dataclass(frozen=True)
class SearchOutcome:
    """A source's answer. Never raises — `error` carries the failure instead."""

    candidates: tuple[Candidate, ...] = ()
    record: Optional[QueryRecord] = None

    @property
    def ok(self) -> bool:
        return not (self.record and self.record.error)


@dataclass
class RetrievalResult:
    """Everything the prompt builder and the report need from retrieval."""

    candidates: list[Candidate] = field(default_factory=list)
    queries: list[QueryRecord] = field(default_factory=list)
    retrieved_at: str = ""
    sources_ok: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    covered_venues: list[str] = field(default_factory=list)
    uncovered_venues: list[str] = field(default_factory=list)
    total_seen: int = 0

    @property
    def usable(self) -> bool:
        return bool(self.candidates)


class EvidenceSource(ABC):
    """A searchable index of papers.

    Implementations must not raise from any method. Return an outcome carrying
    `error` instead, so one dead index can never take down a research run.
    """

    id: str
    label: str
    # Venues this source can see. Declared, not guessed, because the prompt has
    # to tell the agent which journals the candidate list does NOT cover — a
    # silent gap turns retrieval from a guide into a blinker.
    covered_venues: tuple[str, ...] = ()

    def available(self) -> bool:
        return True

    @abstractmethod
    def search(self, query: EvidenceQuery) -> SearchOutcome:
        """Run one query. Must not raise."""

    def lookup_by_doi(self, doi: str) -> Optional[Candidate]:
        """Fetch one record by DOI. Returns None when unsupported or missing."""
        return None

    def find_by_title(self, title: str) -> SearchOutcome:
        """Exact-ish title lookup, used to recover twin versions of a study."""
        return self.search(
            EvidenceQuery(terms=f'"{title}"', scope="title", label="title recovery")
        )
