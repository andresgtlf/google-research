"""User-facing evidence-source attribution used in exports and the review UI.

This text travels into exported PDFs, so changes affect reviewer-facing
provenance and should not be made casually.

Note the BLANK LINE before the bullet list. Python-Markdown — which
`export.py` uses to produce the PDF — will not start a list that directly
follows a paragraph line: it absorbs the bullets into the paragraph and the
reader gets one run-on sentence with stray "-" characters. `test_attribution`
asserts the rendered HTML contains a real `<ul>`, because asserting only that
this string appears in the markdown passes while the PDF looks broken.
"""

ATTRIBUTION_MARKDOWN: str = (
    "Evidence-source integrations for locating and cross-checking research; "
    "the assessment itself is not theirs.\n"
    "\n"
    "- [Economics Literature Search](https://paulgp.com/econlit-pipeline/), built and hosted by Paul Goldsmith-Pinkham at Yale School of Management; associated paper: Goldsmith-Pinkham, *Tracking the Credibility Revolution across Fields*.\n"
    "- [OpenAlex](https://openalex.org), an openly licensed scholarly database run by OurResearch."
)

ATTRIBUTION_PLAIN: str = (
    "Evidence-source integrations include Economics "
    "Literature Search (Paul Goldsmith-Pinkham, Yale School of Management) and "
    "OpenAlex (OurResearch); the assessment itself is not theirs."
)
