"""Recover omitted reference lists using Crossref's APA citation formatter.

Only DOIs already present in the report are sent to Crossref. Provider prose is
preserved; registry formatting is not evidence that the prose's claims are true.
"""

import hashlib
import re
import time
from urllib.parse import quote

import requests

from .citations import SECTION, _label
from .report_parse import extract_dois


def recover_references(text, *, lookup=None):
    if SECTION.search(text):
        return text, []
    lookup = lookup or _lookup
    entries = []
    deadline = time.monotonic() + 20
    for doi in extract_dois(text)[:20]:
        if time.monotonic() >= deadline:
            break
        try:
            entry = lookup(doi)
            if not entry or not _label(entry) or doi.casefold() not in entry.casefold():
                continue
            # Treat all returned text as bibliography data, never HTML/Markdown.
            entry = re.sub(r"[<>\[\]*`_]", "", " ".join(entry.split()))
            ref_id = "ref-doi-" + hashlib.sha256(doi.lower().encode()).hexdigest()[:12]
            entries.append(
                {
                    "doi": doi,
                    "entry": entry,
                    "anchor": ref_id,
                    "source": "Crossref APA formatter",
                }
            )
        except Exception:
            # Formatting must not discard an expensive research result.
            continue
    if not entries:
        return text, []
    for item in entries:
        doi = re.escape(item["doi"])
        # Retain publisher links and add a separate jump to the APA entry.
        pattern = re.compile(
            r"\[[^\]\n]+\]\(https?://(?:dx\.)?doi\.org/" + doi + r"\)", re.I
        )
        text = pattern.sub(
            lambda match: match[0] + f" [APA reference](#{item['anchor']})", text
        )
    text += "\n\n## References\n\n" + "\n\n".join(
        f'<a id="{item["anchor"]}"></a>{item["entry"]}'
        for item in sorted(entries, key=lambda item: item["entry"].casefold())
    )
    text += (
        "\n\n## Reference metadata note\n\nThe model omitted its reference list. "
        "These APA entries were retrieved from Crossref for DOI links present in the report. "
        "Other sources may require manual citation formatting; metadata does not verify the report's claims.\n"
    )
    return text, entries


def _lookup(doi):
    response = requests.get(
        "https://api.crossref.org/works/"
        + quote(doi, safe="/")
        + "/transform/text/x-bibliography",
        headers={
            "Accept": "text/x-bibliography; style=apa; locale=en-US",
            "User-Agent": "GTLF-Research/8.2",
        },
        timeout=5,
        allow_redirects=False,
    )
    response.raise_for_status()
    if response.status_code != 200:
        return None
    return response.content.decode("utf-8")
