"""Extraction prompt for concept notes.

In v2 this prompt also asked the model to re-generate the full research
protocol, which was lossy and wasted ~4k output tokens per run. In v5 the
model only extracts structured fields (enforced by `response_schema`); the
research protocol itself is a fixed template in `research_prompt.py`.
"""

EXTRACTION_PROMPT = """\
You are an Impact Evidence Agent. Read the attached concept note end-to-end and \
extract the requested fields, verbatim where possible, inferring cautiously when \
needed. Leave a field empty (or null) if the note does not support it.

Extract:

1. Organization & project: organization name; project title / short summary; \
intervention type(s) using the controlled vocabulary {training/coaching, job \
placement, cash/asset transfer, productivity/inputs, market access/distribution, \
entrepreneurship support, policy/ecosystem, other}; core mechanism(s) to affect \
income (1-2 sentences).

2. Geography & population: country (and region if given); target population \
descriptors (e.g. smallholder farmers, youth %, women %, baseline income level, \
typical occupation/sector); scale (# directly served, by role if relevant); time \
horizon of activities in years.

3. Intended outcomes & magnitudes: primary income pathway(s), direct and \
indirect; expected changes with units (e.g. % yield, % income, USD/month).

4. Funding: amount requested from GitLab Foundation; total project budget if \
provided.

5. Self-reported evidence: any stated evidence/claims used to substantiate \
effects (quotes or figures).

6. Research parameterization (used to configure a downstream evidence scan — \
base these ONLY on the extracted fields, do not broaden the topic):
   - primary_research_question: ONE sentence asking about the causal INCOME \
effects (wages/earnings, household income, profits, revenues) of the extracted \
intervention type(s) for the extracted population in the extracted country.
   - search_languages: English plus the primary local language if relevant.
   - regional_expansion_contexts: a pre-declared geographic expansion set for \
this country, ordered from most to least similar (used only if in-country \
evidence is scarce).
   - baseline_income_benchmark_sources: authoritative national statistics \
sources for baseline income benchmarking in this country.
"""
