"""Accessible HTML/PDF destinations for generated APA citation anchors."""

import re
from html import escape
from html.parser import HTMLParser

import markdown


class ReferenceLayout(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.output = []
        self.references = False
        self.heading = False
        self.heading_text = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2"):
            self.heading = True
            self.heading_text = ""
        if tag == "p" and self.references:
            attrs = [*attrs, ("class", "apa-reference")]
        self.output.append(
            "<"
            + tag
            + "".join(
                " "
                + key
                + (f'="{escape(value, quote=True)}"' if value is not None else "")
                for key, value in attrs
            )
            + ">"
        )

    def handle_endtag(self, tag):
        if tag in ("h1", "h2"):
            self.references = self.heading_text.strip().lower() == "references"
            self.heading = False
        self.output.append(f"</{tag}>")

    def handle_data(self, data):
        if self.heading:
            self.heading_text += data
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append(f"&{name};")

    def handle_charref(self, name):
        self.output.append(f"&#{name};")

    def handle_startendtag(self, tag, attrs):
        self.output.append(self.get_starttag_text())


def report_html(text: str) -> str:
    rendered = markdown.markdown(
        text, extensions=["tables", "fenced_code", "nl2br", "toc"]
    )
    parser = ReferenceLayout()
    parser.feed(rendered)
    rendered = "".join(parser.output)
    # Backlinks are navigation, not bibliographic entries; no hanging indent.
    return re.sub(
        r'<p class="apa-reference">(?=<a href="#cite-ref-)',
        '<p class="citation-backlinks">',
        rendered,
    )
