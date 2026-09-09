"""Parse the research report markdown into display-ready sections.

Ported from the v2 app.py helpers, with two changes:
  - link columns are KEPT (v2 dropped them),
  - a new parser extracts the "Paywalled High-Value Papers" section.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger(__name__)


def _clean_cell(text: str) -> str:
    text = re.sub(r"\[cite:\s*[\d,\s]+\]", "", text)
    return text.replace("**", "").replace("*", "").strip()


def parse_evidence_table(md_text: str) -> Optional[list[dict[str, str]]]:
    """Extract the evidence digest table as a list of row dicts."""
    lines = md_text.split("\n")
    tables: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if "|" in stripped and stripped.count("|") >= 3:
            current.append(stripped)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)

    best, best_cols = None, 0
    for tbl in tables:
        if len(tbl) < 3:
            continue
        header = tbl[0].lower()
        cols = tbl[0].count("|") - 1
        if ("study" in header or "source" in header) and cols > best_cols:
            best, best_cols = tbl, cols
    if best is None:
        for tbl in tables:
            cols = tbl[0].count("|") - 1
            if len(tbl) >= 3 and cols > best_cols:
                best, best_cols = tbl, cols
    if best is None or len(best) < 3:
        return None

    headers = [h.strip() for h in best[0].split("|") if h.strip()]
    rows = []
    for line in best[2:]:
        cells = [c.strip() for c in line.split("|")]
        # strip leading/trailing empty cells produced by boundary pipes
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if not any(cells):
            continue
        padded = cells + [""] * (len(headers) - len(cells))
        rows.append(
            {h: _clean_cell(c) for h, c in zip(headers, padded[: len(headers)])}
        )
    return rows or None


def _extract_heading_section(md_text: str, keywords: list[str]) -> str:
    """Return the markdown of the first section whose heading matches a keyword."""
    lines = md_text.split("\n")
    start = None
    start_level = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        heading = stripped.lstrip("#").strip().lower()
        if start is None and any(kw in heading for kw in keywords):
            start, start_level = i, level
        elif start is not None and level <= start_level:
            return "\n".join(lines[start:i]).strip()
    if start is not None:
        return "\n".join(lines[start:]).strip()
    return ""


def parse_conclusions(md_text: str) -> str:
    return _extract_heading_section(
        md_text,
        ["conclusion", "key findings", "summary of findings", "overall assessment"],
    )


def parse_paywalled_section(md_text: str) -> str:
    return _extract_heading_section(
        md_text,
        ["paywall", "manual retrieval", "inaccessible papers"],
    )


# The headings Section K of `research_prompt.py` declares mandatory, each with
# the keywords that identify it. Keyword matching rather than literal string
# equality because three structurally different providers write these reports
# and headings drift — the paywalled heading alone carries an em-dash and a
# subtitle that providers routinely reformat.
#
# Order matters only for readability of the warning text.
MANDATORY_HEADINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Search Metadata", ("search metadata", "search strategy", "searches run")),
    ("Included Studies", ("included studies", "studies included")),
    ("Excluded Studies", ("excluded studies", "studies excluded")),
    ("Evidence Digest", ("evidence digest", "evidence table")),
    ("Mechanism Assessment", ("mechanism assessment", "mechanism validation")),
    ("Conclusions", ("conclusion", "key findings", "summary of findings",
                     "overall assessment")),
    ("Paywalled High-Value Papers", ("paywall", "manual retrieval",
                                     "inaccessible papers")),
)


def present_headings(md_text: str) -> tuple[str, ...]:
    """Which mandatory headings the report actually carries."""
    found: list[str] = []
    headings = [
        line.strip().lstrip("#").strip().lower()
        for line in md_text.split("\n")
        if line.strip().startswith("#")
    ]
    for name, keywords in MANDATORY_HEADINGS:
        if any(kw in heading for heading in headings for kw in keywords):
            found.append(name)
    return tuple(found)


def missing_headings(md_text: str) -> tuple[str, ...]:
    present = set(present_headings(md_text))
    return tuple(name for name, _kw in MANDATORY_HEADINGS if name not in present)


def structural_completeness(md_text: str) -> float:
    """Fraction of the mandatory headings present, 0.0-1.0.

    The signal `jobs.py` uses to decide whether a report is worth keeping. On
    2026-08-01 two runs of the same prompt scored 4/7 and 1/7; the 1/7 report
    was published to a reviewer with no conclusions section and no evidence
    table. See `notes/incident-2026-08-01/`.
    """
    return len(present_headings(md_text)) / len(MANDATORY_HEADINGS)


def parse_report_sections(md_text: str) -> dict[str, Any]:
    """Parse the report into display sections, reporting what could not be found.

    Section detection is heading-string matching, and three structurally
    different providers generate these reports, so headings do drift. When a
    section is missed the UI would otherwise render an almost-empty results
    page with no explanation, so misses are reported explicitly in
    `parse_warnings` for the caller to surface.
    """
    evidence_table = parse_evidence_table(md_text)
    conclusions = parse_conclusions(md_text)
    paywalled = parse_paywalled_section(md_text)

    warnings: list[str] = []
    if not conclusions:
        warnings.append(
            "Could not find a conclusions section in the report. "
            "Read the full report below."
        )
    if evidence_table is None:
        warnings.append(
            "Could not find the evidence digest table in the report. "
            "Any evidence tables still appear inline in the full report."
        )
    if not paywalled:
        # Absence here is often legitimate (nothing was paywalled), so this is
        # informational rather than a parse failure.
        log.info("No paywalled-papers section found in report")

    # The four structural sections nothing used to check. They carry the audit
    # trail — which searches ran, what was included, what was rejected and why
    # — so their silent absence is what made the 2026-08-01 regression
    # undiagnosable after the fact: with no Included/Excluded lists there is no
    # way to tell a study that was considered and rejected from one that was
    # never retrieved. Paywalled is excluded here because its absence is
    # legitimate and is handled above.
    unchecked = {"Search Metadata", "Included Studies", "Excluded Studies",
                 "Mechanism Assessment"}
    absent = [name for name in missing_headings(md_text) if name in unchecked]
    if absent:
        warnings.append(
            "The report is missing "
            + ", ".join(absent)
            + ". These sections document how the search was run, so the "
            "report cannot be fully audited."
        )

    for warning in warnings:
        log.warning("Report parse: %s", warning)

    return {
        "evidence_table": evidence_table,
        "conclusions": conclusions,
        "paywalled": paywalled,
        "parse_warnings": warnings,
    }


# ── Section L: paywalled high-value papers ──────────────────────────
#
# Three structurally different LLM providers write Section L, and they do
# not format it identically (see `research_prompt.py` Section L for the
# instructions the agent is given — the wording is followed loosely).
# Observed shapes include: numbered lists with a bolded title followed by
# an inline "Authors (Year). Venue. DOI: ..." tail; bullet lists with
# labeled sub-bullets ("- DOI: ...", "- Status: ..."); and a heading per
# paper with labeled bullets underneath. `parse_paywalled_papers` handles
# all three. A wrong title produces a wrong downstream lookup (see
# `backend/evidence/resolve_k.py`), so every field extraction here prefers
# leaving a field empty over guessing.

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")
_DOI_TRAILING_PUNCT_RE = re.compile(r"[)\]\.,;:!?]+$")

_NO_PAPERS_RE = re.compile(
    r"no\s+high[- ]value\s+paywalled\s+papers\s+were\s+identified", re.IGNORECASE
)

# Sub-bullet/label field names the LLMs use, mapped to our field names.
_LABEL_ALIASES: dict[str, str] = {
    "title": "title",
    "author": "authors",
    "authors": "authors",
    "year": "year",
    "journal": "venue",
    "venue": "venue",
    "publisher": "venue",
    "doi": "doi",
    "publisher page": "publisher_url",
    "publisher url": "publisher_url",
    "publisher link": "publisher_url",
    "link": "publisher_url",
    "url": "publisher_url",
    "status": "status",
}

_LABEL_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\d+[.)]\s+)?\*{0,2}\s*"
    r"([A-Za-z][A-Za-z ]{1,25}?)\s*\*{0,2}\s*:\s*\*{0,2}\s*(.+?)\s*\*{0,2}\s*$"
)


def _clean_doi(raw: str) -> str:
    return _DOI_TRAILING_PUNCT_RE.sub("", raw.strip())


def extract_dois(md_text: str) -> list[str]:
    """Deduplicated, normalized bare DOIs found anywhere in `md_text`.

    Tolerant of `https://doi.org/` prefixes (the regex just starts matching
    at "10.", so the prefix is naturally ignored) and trailing punctuation
    like a closing paren or period picked up from surrounding prose.
    """
    if not md_text:
        return []
    try:
        found: list[str] = []
        seen: set[str] = set()
        for match in _DOI_RE.finditer(md_text):
            doi = _clean_doi(match.group(0))
            key = doi.lower()
            if doi and key not in seen:
                seen.add(key)
                found.append(doi)
        return found
    except re.error as exc:  # pragma: no cover - defensive, regex is static
        log.warning("extract_dois: regex failure: %s", exc)
        return []


@dataclass(frozen=True)
class PaywalledPaper:
    """One paper listed in Section L, parsed best-effort from free-text markdown."""

    title: str
    authors: str = ""
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    publisher_url: str = ""
    status: str = ""
    raw: str = ""  # the original markdown block, so nothing is lost


def _strip_quotes(text: str) -> str:
    text = text.strip()
    text = text.strip("*").strip()
    for open_q, close_q in (('"', '"'), ("“", "”"), ("'", "'")):
        if len(text) >= 2 and text.startswith(open_q) and text.endswith(close_q):
            text = text[1:-1].strip()
    return text


def _parse_label_line(line: str) -> Optional[tuple[str, str]]:
    match = _LABEL_LINE_RE.match(line)
    if not match:
        return None
    label_raw = match.group(1).strip().lower()
    value = match.group(2).strip()
    label = _LABEL_ALIASES.get(label_raw)
    if not label or not value:
        return None
    return label, value


def _extract_title_fallback(first_line: str, block: str) -> str:
    """Title from bold text, quoted text, or a heading line — in that order.

    Skips bold spans that are actually a label (e.g. `**DOI:**`) rather than
    a title.
    """
    for bold_match in re.finditer(r"\*\*(.+?)\*\*", block):
        content = bold_match.group(1).strip()
        check = content.rstrip(":").strip().lower()
        if not content or content.endswith(":") or check in _LABEL_ALIASES:
            continue
        return _strip_quotes(content)

    quote_match = re.search(r'["“]([^"”]{5,300})["”]', block)
    if quote_match:
        return quote_match.group(1).strip()

    heading_match = re.match(r"^\s*#{1,6}\s*(?:\d+[.)]\s*)?(.+?)\s*$", first_line)
    if heading_match:
        candidate = _strip_quotes(heading_match.group(1).strip())
        if candidate:
            return candidate

    return ""


def _extract_inline_fields(raw: str, title: str) -> dict[str, str]:
    """Recover authors/year/venue from an inline `Title, Authors (Year). Venue.` tail.

    Only used when the labeled sub-bullet fields didn't already supply a
    value, so this is a fallback for the "bold title + inline tail" style.
    """
    result: dict[str, str] = {}
    text = raw
    if title:
        idx = text.find(title)
        if idx != -1:
            text = text[idx + len(title) :]

    year_match = re.search(r"\(\s*((?:19|20)\d{2})\s*\)", text)
    if not year_match:
        return result
    result["year"] = year_match.group(1)

    before = text[: year_match.start()]
    authors = before.strip().strip("*").strip().lstrip(",").strip().rstrip("*").strip()
    if authors and not authors.lower().startswith(("doi", "link", "http")):
        result["authors"] = authors

    after = text[year_match.end() :]
    venue_match = re.match(r"\s*\.?\s*([^.]{2,150})", after)
    if venue_match:
        venue = venue_match.group(1).strip().rstrip(".").strip()
        if venue and not re.match(
            r"(?i)^(doi|link|publisher|url|http|status)\b", venue
        ):
            result["venue"] = venue
    return result


def _parse_one_paywalled_block(block: str) -> Optional[PaywalledPaper]:
    raw = block.strip()
    if not raw:
        return None
    lines = raw.split("\n")

    fields: dict[str, str] = {}
    for line in lines:
        parsed = _parse_label_line(line)
        if parsed:
            label, value = parsed
            fields.setdefault(label, value)

    title = fields.get("title") or _extract_title_fallback(lines[0], raw)
    title = _strip_quotes(title) if title else ""

    authors = fields.get("authors", "")
    year_str = fields.get("year", "")
    venue = fields.get("venue", "")
    doi = fields.get("doi", "")
    publisher_url = fields.get("publisher_url", "")
    status = fields.get("status", "")

    if not authors or not year_str or not venue:
        inline = _extract_inline_fields(raw, title)
        authors = authors or inline.get("authors", "")
        year_str = year_str or inline.get("year", "")
        venue = venue or inline.get("venue", "")

    year: Optional[int] = None
    year_match = re.search(r"(19|20)\d{2}", year_str)
    if year_match:
        year = int(year_match.group(0))

    if not doi:
        doi_field_dois = extract_dois(fields.get("doi", ""))
        block_dois = doi_field_dois or extract_dois(raw)
        doi = block_dois[0] if block_dois else ""
    else:
        doi = extract_dois(doi)[0] if extract_dois(doi) else doi

    if not publisher_url:
        url_match = re.search(r"https?://\S+", raw)
        if url_match:
            candidate_url = url_match.group(0).rstrip(".,;)")
            if "doi.org" not in candidate_url:
                publisher_url = candidate_url

    if not status:
        low = raw.lower()
        if "abstract-only" in low:
            status = "abstract-only (included with limited extraction)"
        elif "not included" in low:
            status = "not included (inaccessible)"

    if not title and not doi:
        return None

    return PaywalledPaper(
        title=title,
        authors=authors.strip(),
        year=year,
        venue=venue.strip(),
        doi=doi,
        publisher_url=publisher_url,
        status=status.strip(),
        raw=raw,
    )


def _split_paywalled_blocks(body: str) -> list[str]:
    lines = body.split("\n")

    heading_idxs = [
        i for i, line in enumerate(lines) if re.match(r"^\s{0,3}#{2,6}\s+\S", line)
    ]
    marker_idxs = heading_idxs
    if not marker_idxs:
        marker_idxs = [
            i
            for i, line in enumerate(lines)
            if re.match(r"^\d+[.)]\s+\S", line) or re.match(r"^[-*]\s+\S", line)
        ]

    if not marker_idxs:
        stripped = body.strip()
        return [stripped] if stripped else []

    boundaries = marker_idxs + [len(lines)]
    blocks: list[str] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        blk = "\n".join(lines[start:end]).strip()
        if blk:
            blocks.append(blk)
    # Anything before the first marker (rare stray prose) is discarded rather
    # than mis-parsed into a fake paper.
    return blocks


def parse_paywalled_papers(md_text: str) -> list[PaywalledPaper]:
    """Structured parse of Section L. Never raises; returns [] on anything odd.

    Returns [] when the section says no paywalled papers were identified, is
    missing entirely, or when the input is empty/garbage.
    """
    try:
        section = parse_paywalled_section(md_text or "")
    except Exception as exc:  # defensive: this must never take down a report
        log.warning("parse_paywalled_papers: section extraction failed: %s", exc)
        return []

    if not section:
        return []

    try:
        lines = section.split("\n")
        body = "\n".join(lines[1:]) if lines and lines[0].strip().startswith("#") else section

        if _NO_PAPERS_RE.search(body):
            return []

        papers: list[PaywalledPaper] = []
        for block in _split_paywalled_blocks(body):
            try:
                paper = _parse_one_paywalled_block(block)
            except Exception as exc:
                log.warning("parse_paywalled_papers: failed to parse a block: %s", exc)
                continue
            if paper is not None:
                papers.append(paper)
        return papers
    except Exception as exc:  # never raise, per contract
        log.warning("parse_paywalled_papers: unexpected failure: %s", exc)
        return []
