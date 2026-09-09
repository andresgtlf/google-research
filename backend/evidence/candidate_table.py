"""Render retrieved candidates and their provenance for the research prompt.

Kept separate from `research_prompt.py` so the protocol text stays readable and
the rendering stays testable on its own.

Two things here carry real weight:

1. **The coverage disclosure.** A candidate list handed over without saying what
   it does NOT cover turns retrieval from a guide into a blinker: the agent
   treats the list as the evidence base and quietly stops looking. The index
   covers 7 of the 12 venues in the protocol's own journal list and misses the
   five development/labor journals that carry most of this literature, so the
   gap is named explicitly and the agent is told to search it independently.

2. **Abstract honesty.** econlit populates `abstract` for ~7% of rows. A blank
   cell must read as "not retrieved" rather than as "no abstract exists", or the
   agent will screen a paper out for looking empty.
"""

from typing import Sequence

from .base import Candidate, QueryRecord, RetrievalResult

# Keeping the injected block well clear of the protocol's own length: the
# candidate list is a starting point, not the payload, and a table long enough
# to dominate the context invites the agent to extract it and stop.
MAX_ABSTRACT_CHARS = 420


def _authors(candidate: Candidate, max_names: int = 3) -> str:
    if not candidate.authors:
        return "n/a"
    names = list(candidate.authors[:max_names])
    if len(candidate.authors) > max_names:
        names.append("et al.")
    return ", ".join(names)


def _access(candidate: Candidate) -> str:
    if candidate.oa_url:
        return f"free full text: {candidate.oa_url}"
    if candidate.is_oa:
        return "open access"
    if candidate.is_oa is False:
        return "index reports closed access — retain DOI/publisher link for retrieval"
    return "access unknown — no free version located; this does not confirm a paywall"


def _quality(candidate: Candidate) -> str:
    bits: list[str] = []
    if candidate.citations is not None:
        bits.append(f"{candidate.citations} citations")
    if candidate.replication_url:
        bits.append(f"replication package: {candidate.replication_url}")
    elif candidate.replication_status:
        bits.append(f"replication: {candidate.replication_status}")
    return "; ".join(bits) or "no citation or replication data"


def _abstract(candidate: Candidate) -> str:
    text = candidate.abstract.strip()
    if not text:
        # Explicitly "not retrieved", never an empty cell — see module docstring.
        return (
            "NOT RETRIEVED — the index does not hold an abstract for this "
            "record. Do not treat this as evidence of low quality or of a "
            "missing outcome; retrieve the abstract before screening."
        )
    if len(text) > MAX_ABSTRACT_CHARS:
        return text[:MAX_ABSTRACT_CHARS].rstrip() + "… [truncated]"
    return text


def render_candidate(candidate: Candidate, index: int) -> str:
    versions = ""
    if candidate.alt_dois:
        pairs = ", ".join(
            f"{doi} ({venue})" if venue else doi
            for doi, venue in zip(
                candidate.alt_dois,
                list(candidate.alt_venues) + [""] * len(candidate.alt_dois),
            )
        )
        versions = (
            f"\n   - Other version(s) of the same study: {pairs}"
            f"\n     (Use the peer-reviewed version for conclusions; the working "
            f"paper is usually where the free full text is.)"
        )
    notes = "; ".join(candidate.score_notes) if candidate.score_notes else "n/a"
    return (
        f"{index}. {candidate.title}\n"
        f"   - Authors: {_authors(candidate)}\n"
        f"   - Venue / year: {candidate.venue or 'n/a'} / "
        f"{candidate.year if candidate.year is not None else 'n/a'}\n"
        f"   - DOI: {candidate.doi or 'n/a'}{versions}\n"
        f"   - Access: {_access(candidate)}\n"
        f"   - Quality signals: {_quality(candidate)}\n"
        f"   - Why retrieved: {notes}\n"
        f"   - Abstract: {_abstract(candidate)}"
    )


def render_provenance(queries: Sequence[QueryRecord]) -> str:
    if not queries:
        return "No structured queries were recorded."
    lines = []
    for q in queries:
        scope = f"scope={q.scope}, mode={q.mode}"
        window = (
            f", years={q.year_start or 'any'}-{q.year_end or 'any'}"
            if (q.year_start or q.year_end)
            else ""
        )
        found = (
            f"{q.total_results} matches, {q.returned} returned"
            if q.total_results is not None
            else f"{q.returned} returned"
        )
        outcome = f"ERROR: {q.error}" if q.error else found
        lines.append(
            f'- [{q.source}] "{q.terms}" ({scope}{window}) — {outcome}'
            + (f" — purpose: {q.label}" if q.label else "")
        )
    return "\n".join(lines)


def render_coverage(result: RetrievalResult) -> str:
    """State coverage as a fact about the list, never as a claim about reach.

    `covered_venues` / `uncovered_venues` are computed in `retrieval.py` from the
    venues actually present in the returned candidates. Phrasing this as "the
    index covers X" would overstate it: a source can be able to search a journal
    and still return nothing from it, and the agent would read that as coverage.
    """
    covered = ", ".join(result.covered_venues) or "none"
    uncovered = ", ".join(result.uncovered_venues)
    text = (
        f"COVERAGE OF THE LIST ABOVE — venues actually represented in it: "
        f"{covered}.\n"
    )
    if uncovered:
        text += (
            f"\nThe list contains NO papers from these venues, which are on the "
            f"protocol's own journal list in Section B: {uncovered}.\n"
            f"You MUST search them independently. They carry a large share of "
            f"the causal income-effects literature for this kind of "
            f"intervention, so treating the pre-screened list as complete would "
            f"narrow this review rather than sharpen it. Their absence here is "
            f"a gap in the retrieval, NOT evidence that no such studies "
            f"exist.\n"
        )
    text += (
        "\nThe list also does NOT cover the RCT and evaluation repositories "
        "(J-PAL, IPA, 3ie, World Bank DIME, AEA RCT Registry), the other "
        "working-paper archives (IZA, SSRN, RePEc), grey literature, or any "
        "non-English source. Those remain entirely your responsibility."
    )
    return text


def render_candidate_block(result: RetrievalResult) -> str:
    """The full injected block, or a plain note when retrieval found nothing."""
    if not result.usable:
        failed = ", ".join(result.sources_failed)
        reason = f" (sources unavailable: {failed})" if failed else ""
        return (
            "PRE-SCREENED CANDIDATE STUDIES: none available for this run"
            f"{reason}. Conduct the full retrieval protocol below yourself, "
            "unaided.\n"
        )

    candidates = "\n\n".join(
        render_candidate(c, i) for i, c in enumerate(result.candidates, 1)
    )
    return f"""\
PRE-SCREENED CANDIDATE STUDIES ({len(result.candidates)} studies, retrieved \
{result.retrieved_at} before this run)

These were retrieved deterministically by structured query, NOT chosen by \
judgment. They are a STARTING SET, NOT THE ANSWER SET, and they are ranked by a \
crude keyword heuristic that has not read the papers. Your obligations:

- Screen EVERY candidate against the study parameters. Include it or exclude \
it, and give a reason either way. An unexplained omission makes the report \
incomplete.
- Reject freely. A candidate scoring well on the heuristic may be irrelevant on \
reading; say so and exclude it. Retrieval ranking is not evidence of quality.
- Keep searching after this list. It covers a fraction of the relevant \
literature — see the coverage limits below — and a report that only contains \
these studies has not done the job.

{render_coverage(result)}

--- CANDIDATES ---

{candidates}

--- QUERIES THAT PRODUCED THE LIST (reproduce verbatim in Search Metadata) ---

{render_provenance(result.queries)}
"""
