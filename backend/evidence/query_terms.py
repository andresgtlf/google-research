"""Vocabulary and text-normalization helpers shared by `queries.py`.

Split out of `queries.py` to keep that file focused on the six query
families and under the house style's line-count ceiling. Nothing here is
network- or index-specific: it is pure text manipulation over extracted
fields, which is also why it is trivially unit-testable in isolation.
"""

import re
from collections.abc import Sequence
from datetime import datetime, timezone

from ..schemas import Extraction, Population
from .base import INCOME_OUTCOME_SIGNALS

# ── Vocabulary groups (reviewable, testable) ────────────────────────────────

# Reused from base.py rather than duplicated: these are the exact terms
# ranking.py checks for in title/abstract, so the query that retrieves a
# candidate and the score that judges it speak the same vocabulary.
INCOME_OUTCOME_TERMS: tuple[str, ...] = INCOME_OUTCOME_SIGNALS

# Signals of a causal (not merely correlational) research design. Mirrors the
# vocabulary research_prompt.py's Section B "Core query" pattern uses
# (`RCT OR randomized OR evaluation OR impact`), extended with the
# quasi-experimental designs ranking.py also rewards.
CAUSAL_DESIGN_TERMS: tuple[str, ...] = (
    "randomized controlled trial",
    "RCT",
    "randomized",
    "quasi-experimental",
    "regression discontinuity",
    "difference-in-differences",
    "instrumental variable",
)

YOUTH_TERMS: tuple[str, ...] = ("youth", "young adults", "adolescents")

WOMEN_TERMS: tuple[str, ...] = ("women", "female", "gender")

# ── Subject vocabulary: what the note is ABOUT ──────────────────────────────
#
# Until this existed, every query family was built from `intervention_types`
# alone, so a note about computer-science undergraduates and a note about
# vocational training for rural youth produced the same search: the
# intervention label crossed with the country. The CodePath run's retrieval
# never once mentioned STEM, computer science, college, degree or
# underrepresented, though the extraction contains all of that.
#
# Two distinct problems, both handled here:
#
# 1. TRANSLATION. The terms that actually retrieve this literature are not the
#    terms a concept note uses. Measured against econlit on the CodePath
#    extraction (31 variants, `notes/incident-2026-08-01/`): 16 formulations
#    surfaced NBER w30227 and all but one contained `STEM` — a token absent
#    from the extraction. Likewise the note says "Black, Latino/a, Indigenous,
#    low-income"; the literature says "underrepresented" and "minority".
#    Searching a note's own wording is bug B in a different costume.
#
# 2. COVERAGE. "college", "first-generation" and "degree completion" were
#    already sitting in `population.description` and `intended_outcomes.direct`
#    — fields `build_queries` never read.
#
# Each entry is (group name, trigger words found in the note, search terms
# issued). Triggers are matched as substrings against the note's subject text,
# so "computing" catches "computing students" and "engineer" catches
# "engineers"/"engineering".
SUBJECT_VOCABULARY: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "field",
        (
            "computer science", "computing", "software", "coding", "developer",
            "engineer", "technical", "technology", "STEM", "data science",
        ),
        ("STEM", "computer science", "engineering"),
    ),
    (
        "education_level",
        (
            "college", "university", "undergraduate", "higher education",
            "campus", "postsecondary", "degree", "major",
        ),
        ("college", "undergraduate", "higher education"),
    ),
    (
        "demographic",
        (
            "underrepresented", "underserved", "minority", "black", "latino",
            "latina", "hispanic", "indigenous", "first-generation",
            "low-income", "marginalized", "disadvantaged",
        ),
        ("underrepresented", "minority", "first-generation"),
    ),
    (
        "completion",
        ("degree completion", "graduation", "credential", "dropout", "attainment"),
        ("degree completion", "graduation", "educational attainment"),
    ),
)

# Cap on subject groups AND-ed into one query. Three matched groups reproduced
# the best measured formulation (target at position 1); a fourth narrows the
# result set without adding precision.
SUBJECT_MAX_GROUPS = 3

# ── Tunables (no magic numbers inline) ──────────────────────────────────────

# "Last 15 years by default" per the deterministic research protocol in
# research_prompt.py Section B.
DEFAULT_LOOKBACK_YEARS = 15

# No index used here has meaningful coverage before 2000.
MIN_YEAR = 2000

# A population is treated as "focused" on a subgroup once its stated share
# reaches this threshold — high enough that a passing mention (e.g. "5% of
# beneficiaries are women") does not spuriously trigger a dedicated query.
POPULATION_FOCUS_THRESHOLD_PCT = 30.0

# Cap on noun-phrases pulled out of `mechanisms_to_affect_income` — enough to
# capture the claimed pathway without OR-ing in so many phrases that the
# query loses precision.
MECHANISM_MAX_PHRASES = 3

# Longest phrase worth issuing as a search term. Three words covers real
# economics vocabulary ("conditional cash transfer", "active labour market")
# while excluding the run-on phrases that are only ever found in the concept
# note itself. Live check against econlit: the CodePath note's mechanism family
# OR-ed "include AI-enabled developer workflows", "Redesigning technical
# curriculum" and "high-paying technical roles" and returned 0 rows — no index
# contains those strings, and none ever will.
MECHANISM_MAX_WORDS = 3

# Rule-based mechanism-phrase extraction: split on these function words and
# keep the remaining runs of content words as candidate noun phrases. This is
# a coarse stand-in for real NP-chunking (no NLP dependency is available
# here), but on prose like "training increases skills and connects graduates
# to employers via job-matching" it recovers exactly the kind of pathway
# phrases ("job-matching", "occupational skills") the mission cares about.
_MECHANISM_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to",
        "for", "by", "with", "from", "into", "through", "via", "as", "that",
        "this", "these", "those", "is", "are", "was", "were", "be", "been",
        "being", "it", "its", "their", "they", "which", "who", "whom", "so",
        "than", "then", "if", "because", "while", "when", "where", "how",
        "also", "such", "not", "no", "can", "will", "would", "should",
        "could", "may", "might", "must", "do", "does", "did", "has", "have",
        "had", "provide", "provides", "providing", "increase", "increases",
        "increasing", "help", "helps", "helping", "enable", "enables",
        "enabling", "aim", "aims", "aiming", "seek", "seeks", "designed",
        "allow", "allows", "allowing", "will",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")
_BOUNDARY_PUNCT_RE = re.compile(r"^[\W_]+|[\W_]+$")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")

# Separators used inside the extraction schema's controlled-vocabulary labels
# to pack several concepts into one value ("training/coaching", "savings,
# credit", "mentoring & referrals"). They are notation, not something any paper
# writes, so they must be split before the label is used as a search term.
# Hyphens are deliberately absent: "difference-in-differences" and "AI-enabled"
# are single real terms.
_LABEL_SEPARATOR_RE = re.compile(r"\s*(?:[/,;&+]|\band\b)\s*", re.IGNORECASE)


def normalize(term: str) -> str:
    """Strip boundary punctuation, collapse internal whitespace."""
    if not term:
        return ""
    collapsed = _WHITESPACE_RE.sub(" ", term.strip())
    return _BOUNDARY_PUNCT_RE.sub("", collapsed).strip()


def quote(term: str) -> str:
    """Wrap multi-word phrases for the index's phrase syntax; leave single
    tokens bare, since quoting a single word buys nothing."""
    return f'"{term}"' if " " in term else term


def or_group(terms: Sequence[str]) -> str:
    """Build a parenthesized OR clause from a vocabulary group, normalizing
    and deduplicating first so `("earnings" OR "earnings")` never happens."""
    quoted = [quote(normalize(t)) for t in terms if normalize(t)]
    deduped = tuple(dict.fromkeys(quoted))
    if not deduped:
        return ""
    if len(deduped) == 1:
        return deduped[0]
    return "(" + " OR ".join(deduped) + ")"


def clean_terms(raw: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(t for t in (normalize(r) for r in raw) if t))


def split_label_terms(raw: Sequence[str]) -> tuple[str, ...]:
    """Turn controlled-vocabulary labels into atomic, searchable terms.

    `clean_terms` only strips punctuation at the boundaries, so the schema
    label "training/coaching" survived intact and was issued as a search term.
    Nothing matches it. The query it anchored — `training/coaching "United
    States"`, title-scoped — therefore degenerated into a search for the
    country name, and econlit answered with 50 rows of "The Industrial
    Revolution in the United States: 1790-1870" and similar. That single
    inert token is why the CodePath run's top-ranked candidates were about
    acid rain and life-cycle consumption: the ranker was never handed anything
    on topic to rank.

    Applies to intervention labels only. Country and region names are NOT run
    through this — "Trinidad and Tobago" is one place, not two.
    """
    terms: list[str] = []
    for label in raw:
        for piece in _LABEL_SEPARATOR_RE.split(label or ""):
            cleaned = normalize(piece)
            if cleaned:
                terms.append(cleaned)
    return tuple(dict.fromkeys(terms))


def year_start(lookback_years: int = DEFAULT_LOOKBACK_YEARS) -> int:
    current_year = datetime.now(timezone.utc).year
    return max(MIN_YEAR, current_year - lookback_years)


def extract_mechanism_phrases(
    text: str, max_phrases: int = MECHANISM_MAX_PHRASES
) -> tuple[str, ...]:
    """Pull the searchable noun phrases out of a mechanism description.

    Tokenizes, drops stopwords, and treats each surviving run of content words
    as one phrase. SHORTER phrases are preferred, and anything over
    `MECHANISM_MAX_WORDS` is discarded outright.

    This inverts the original rule, which took the longest runs on the theory
    that longer meant more specific. Length does track specificity — but
    specific *to this concept note*, which is the opposite of useful. The
    longest runs in a note's mechanism prose are its own phrasing
    ("Redesigning technical curriculum"), and no index contains them. The short
    ones are the phrases the note shares with the literature ("placement
    rates"), and those are the only ones that can retrieve anything.

    Ties break on character length, then on order of appearance, so the result
    is deterministic — `retrieval.py` asserts repeated calls are identical.
    """
    words = _WORD_RE.findall(text)
    phrases: list[str] = []
    current: list[str] = []
    for word in words:
        if word.lower() in _MECHANISM_STOPWORDS:
            if current:
                phrases.append(" ".join(current))
                current = []
        else:
            current.append(word)
    if current:
        phrases.append(" ".join(current))

    searchable = [
        p
        for p in dict.fromkeys(phrases)
        if len(p) > 2 and len(p.split()) <= MECHANISM_MAX_WORDS
    ]
    ordered = sorted(searchable, key=lambda p: (len(p.split()), len(p)))
    return tuple(ordered[:max_phrases])


def subject_text(extraction: "Extraction") -> str:
    """The note's own description of what it is about, lowercased.

    Deliberately excludes `mechanisms_to_affect_income` — that field feeds the
    mechanism family, and mixing it in here would let one field trigger two
    families on the same words.
    """
    outcomes = extraction.intended_outcomes
    parts: list[str] = [
        extraction.project_title or "",
        extraction.summary or "",
        extraction.population.description or "",
        " ".join(outcomes.direct or []),
        " ".join(outcomes.indirect or []),
        " ".join(extraction.intervention_types or []),
    ]
    return " ".join(p for p in parts if p).lower()


def subject_groups(
    extraction: "Extraction", max_groups: int = SUBJECT_MAX_GROUPS
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Which subject groups this note triggers, with the terms to search on.

    Returns `()` for a note with no matching subject — a cash-transfer note
    gets no STEM query. Order follows `SUBJECT_VOCABULARY`, so the result is
    deterministic, which `retrieval.py` requires.
    """
    text = subject_text(extraction)
    matched: list[tuple[str, tuple[str, ...]]] = []
    for name, triggers, search_terms in SUBJECT_VOCABULARY:
        if any(trigger.lower() in text for trigger in triggers):
            matched.append((name, search_terms))
    return tuple(matched[:max_groups])


def population_focus(population: Population) -> tuple[bool, bool]:
    """Whether the note's population is youth-focused and/or women-focused,
    per pre-specified heterogeneity cuts the Foundation always wants."""
    description = (population.description or "").lower()

    youth = (
        population.youth_pct is not None
        and population.youth_pct >= POPULATION_FOCUS_THRESHOLD_PCT
    ) or any(term in description for term in YOUTH_TERMS)

    women = (
        population.women_pct is not None
        and population.women_pct >= POPULATION_FOCUS_THRESHOLD_PCT
    ) or any(term in description for term in WOMEN_TERMS)

    return youth, women
