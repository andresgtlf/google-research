"""Pydantic schemas for structured extraction from concept notes.

Used as the `response_schema` for Gemini structured output, which guarantees
valid JSON and removes the regex-based JSON recovery used in v2.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Population(BaseModel):
    description: str = ""
    youth_pct: Optional[float] = None
    women_pct: Optional[float] = None
    baseline_income_note: str = ""


class ScaleGroup(BaseModel):
    group: str = Field(description="Beneficiary group, e.g. 'farmers', 'entrepreneurs'")
    count: str = Field(description="Number directly served, as stated in the note")


class Scale(BaseModel):
    by_group: list[ScaleGroup] = []
    time_horizon_years: Optional[float] = None


class IntendedOutcomes(BaseModel):
    direct: list[str] = []
    indirect: list[str] = []
    magnitudes: list[str] = Field(
        default=[],
        description="Expected changes with units, e.g. '% yield', 'USD per month'",
    )


class Funding(BaseModel):
    gitlab_request_usd: Optional[float] = None
    total_project_budget_usd: Optional[float] = None


class Extraction(BaseModel):
    organization: str = ""
    project_title: str = ""
    summary: str = ""
    intervention_types: list[str] = Field(
        default=[],
        description=(
            "Controlled vocabulary: training/coaching, job placement, "
            "cash/asset transfer, productivity/inputs, market access/distribution, "
            "entrepreneurship support, policy/ecosystem, other"
        ),
    )
    mechanisms_to_affect_income: str = ""
    country: str = ""
    region: str = ""
    population: Population = Population()
    scale: Scale = Scale()
    intended_outcomes: IntendedOutcomes = IntendedOutcomes()
    funding: Funding = Funding()
    self_reported_evidence: list[str] = []
    # Fields that parameterize the deterministic research protocol template
    primary_research_question: str = Field(
        default="",
        description=(
            "A single-sentence primary research question using ONLY extracted "
            "fields (country, population, intervention type, outcomes), focused "
            "on causal INCOME effects."
        ),
    )
    search_languages: list[str] = Field(
        default=[],
        description=(
            "Languages to search in: English plus the primary local language "
            "if relevant (e.g. Spanish for Colombia)."
        ),
    )
    regional_expansion_contexts: list[str] = Field(
        default=[],
        description=(
            "Pre-declared geographic expansion set if in-country evidence is "
            "scarce, ordered from most to least similar (e.g. for Colombia: "
            "'Andean region (Peru/Ecuador/Bolivia)', 'broader Latin America')."
        ),
    )
    baseline_income_benchmark_sources: list[str] = Field(
        default=[],
        description=(
            "Authoritative national statistics sources for baseline income "
            "benchmarking in this country (e.g. DANE for Colombia, KNBS/KIHBS "
            "for Kenya, BLS/ACS for the U.S., plus World Bank/ILOSTAT)."
        ),
    )
