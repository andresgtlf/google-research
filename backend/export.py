"""Report export: Markdown + PDF (WeasyPrint), ported from v2 export.py.

v5 additions: provider/model metadata in the header and GTLF-branded PDF
styling with a highlighted "Paywalled High-Value Papers" section.
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


from .evidence.attribution import ATTRIBUTION_MARKDOWN
from .citations import prepare_citations
from .report_html import report_html
from .report_filename import report_filename

log = logging.getLogger(__name__)


def _setup_weasyprint_library_paths():
    """Set up library paths for WeasyPrint on macOS with Homebrew."""
    try:
        lib_paths = []
        for package in ["pango", "glib", "gdk-pixbuf", "harfbuzz", "fontconfig"]:
            try:
                prefix = subprocess.check_output(
                    ["brew", "--prefix", package], stderr=subprocess.DEVNULL
                ).decode().strip()
                if os.path.exists(f"{prefix}/lib"):
                    lib_paths.append(f"{prefix}/lib")
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        if lib_paths:
            joined = ":".join(lib_paths)
            for var in ("LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
                existing = os.environ.get(var, "")
                os.environ[var] = joined + (f":{existing}" if existing else "")
    except Exception:
        pass


_setup_weasyprint_library_paths()

try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False

PROVIDER_LABELS = {
    "gemini": "Gemini Deep Research",
    "openai": "OpenAI Deep Research",
    "claude": "Claude Research (web search agent)",
}


def format_extraction_summary(extraction: dict) -> str:
    """Format the extraction data into a readable summary section."""
    lines = ["## Project Overview\n"]
    if extraction.get("source_format"):
        lines.append("**Document format:** " + extraction["source_format"].replace("_", " ") + "\n")
    if extraction.get("source_format") == "next_ladder_intake":
        lines.append("### Intake claims and model inputs\n\nSource-reported; not independently verified.\n")
        for key, value in extraction.get("intake", {}).items():
            if value:
                rendered = "; ".join(value) if isinstance(value, list) else str(value)
                lines.append(f"**{key.replace('_', ' ').capitalize()}:** {rendered}\n")

    if extraction.get("organization"):
        lines.append(f"**Organization:** {extraction['organization']}\n")
    if extraction.get("project_title"):
        lines.append(f"**Project Title:** {extraction['project_title']}\n")
    if extraction.get("summary"):
        lines.append(f"\n**Summary:**\n{extraction['summary']}\n")
    if extraction.get("intervention_types"):
        lines.append(
            f"\n**Intervention Types:** {', '.join(extraction['intervention_types'])}\n"
        )
    if extraction.get("mechanisms_to_affect_income"):
        lines.append(
            f"\n**Mechanisms to Affect Income:**\n"
            f"{extraction['mechanisms_to_affect_income']}\n"
        )

    lines.append("\n## Geography & Population\n")
    if extraction.get("country"):
        region = f" ({extraction['region']})" if extraction.get("region") else ""
        lines.append(f"**Country:** {extraction['country']}{region}\n")

    pop = extraction.get("population") or {}
    if pop.get("description"):
        lines.append(f"\n**Target Population:** {pop['description']}\n")
    if pop.get("youth_pct") is not None:
        lines.append(f"**Youth Percentage:** {pop['youth_pct']}%\n")
    if pop.get("women_pct") is not None:
        lines.append(f"**Women Percentage:** {pop['women_pct']}%\n")
    if pop.get("baseline_income_note"):
        lines.append(f"\n**Baseline Income Note:** {pop['baseline_income_note']}\n")

    scale = extraction.get("scale") or {}
    if scale.get("by_group") or scale.get("time_horizon_years"):
        lines.append("\n## Scale\n")
        if scale.get("by_group"):
            lines.append("**Directly Served:**\n")
            for item in scale["by_group"]:
                lines.append(f"- {item.get('group', '')}: {item.get('count', '')}\n")
        if scale.get("time_horizon_years"):
            lines.append(f"\n**Time Horizon:** {scale['time_horizon_years']} years\n")

    outcomes = extraction.get("intended_outcomes") or {}
    if any(outcomes.get(k) for k in ("direct", "indirect", "magnitudes")):
        lines.append("\n## Intended Outcomes\n")
        for key, label in (
            ("direct", "Direct Outcomes"),
            ("indirect", "Indirect Outcomes"),
            ("magnitudes", "Expected Magnitudes"),
        ):
            if outcomes.get(key):
                lines.append(f"**{label}:**\n")
                lines.extend(f"- {o}\n" for o in outcomes[key])
                lines.append("\n")

    funding = extraction.get("funding") or {}
    if funding.get("gitlab_request_usd") or funding.get("total_project_budget_usd"):
        lines.append("\n## Funding\n")
        if funding.get("gitlab_request_usd"):
            lines.append(
                f"**GitLab Foundation Request:** ${funding['gitlab_request_usd']:,.0f}\n"
            )
        if funding.get("total_project_budget_usd"):
            lines.append(
                f"**Total Project Budget:** ${funding['total_project_budget_usd']:,.0f}\n"
            )

    if extraction.get("self_reported_evidence"):
        lines.append("\n## Self-Reported Evidence\n")
        lines.extend(f"- {ev}\n" for ev in extraction["self_reported_evidence"])

    return "\n".join(lines)


def create_markdown_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
) -> Path:
    with open(research_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    extraction = data.get("extraction", {})
    research_text = data.get("result", "") or data.get("research_result", {}).get(
        "result", ""
    )
    citation_document = prepare_citations(research_text)
    research_text = citation_document.markdown
    provider = data.get("provider", "")
    model = data.get("model", "")

    org = extraction.get("organization", "Unknown Organization")
    title = extraction.get("project_title", "Research Report")

    lines = [
        '<a id="report-start"></a>\n',
        f"# {org}\n",
        f"## {title}\n",
        f"\n*Generated on {data.get('created_at') or datetime.now().strftime('%B %d, %Y')}*\n",
    ]
    if '## References' in research_text:
        lines.append("[Jump to references](#references) · Select an author–date citation to see its reference; use its return links to come back.\n")
    if provider:
        engine = PROVIDER_LABELS.get(provider, provider)
        lines.append(f"\n*Research engine: {engine}" + (f" — `{model}`*\n" if model else "*\n"))
    lines += [
        "\n---\n",
        format_extraction_summary(extraction),
        "\n---\n",
        "\n# Deep Research Results\n",
        "\n",
        research_text,
        "\n\n## Access and citation checks\n" if data.get("enrichment") else "",
        data.get("enrichment", {}).get("resolutions_markdown", ""),
        data.get("enrichment", {}).get("verification_markdown", ""),
        "\n\n## Citation notes\n" + "\n".join(citation_document.warnings) if citation_document.warnings else "",
        "\n\n## Run provenance\n",
        f"Protocol: {data.get('protocol_version', 'legacy')}\n",
        f"Run fingerprint: `{data.get('run_fingerprint', 'not recorded')}`\n",
        "Fresh AI synthesis can vary. Reopening a saved run preserves its original evidence and text.\n",
        "\n\n---\n",
        f"\n*Report generated from: {research_json_path.name}*\n",
        "\n## Evidence sources\n",
        f"\n{ATTRIBUTION_MARKDOWN}\n",
    ]

    output_dir = Path(output_dir or research_json_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / report_filename(extraction.get("organization"), "md")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


_PDF_CSS = """
@page { size: A4; margin: 1.6cm; @bottom-right { content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #78716C; } }
h1, h2, h3 { break-after: avoid; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
h2 + ul { break-inside: avoid; }
p { orphans: 3; widows: 3; }
.apa-reference { padding-left: 1.27cm; text-indent: -1.27cm; line-height: 2; break-inside: avoid; overflow-wrap: anywhere; }
.citation-backlinks { font-size: 8pt; margin-top: -4px; }
#references { break-before: page; }
body {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.55; color: #1C1917; font-size: 10.5pt;
}
h1 { color: #1C1917; border-bottom: 3px solid #FC6D26; padding-bottom: 8px; margin-top: 24px; }
h2 { color: #292524; border-bottom: 1.5px solid #D6D3D1; padding-bottom: 4px; margin-top: 22px; }
h3 { color: #44403C; margin-top: 16px; }
a { color: #C2410C; }
table {
    border-collapse: collapse; width: 100%; margin: 16px 0;
    font-size: 7pt; table-layout: fixed; word-wrap: break-word;
}
table th, table td {
    border: 1px solid #E7E5E4; padding: 3px 4px; text-align: left;
    word-wrap: break-word; overflow-wrap: break-word; hyphens: auto;
    vertical-align: top;
}
table th { background-color: #FC6D26; color: white; font-weight: 600; }
table tr:nth-child(even) { background-color: #FAF9F7; }
table { page-break-inside: auto; }
table tr { page-break-inside: avoid; }
code { background-color: #F5F5F4; padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
blockquote { border-left: 4px solid #FC6D26; padding-left: 14px; margin-left: 0; color: #57534E; }
"""


def create_pdf_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
    markdown_path: Optional[Path] = None,
) -> Path:
    if not WEASYPRINT_AVAILABLE:
        raise ImportError(
            "PDF generation requires WeasyPrint and its system libraries. "
            "macOS: brew install pango gdk-pixbuf libffi · "
            "Debian/Ubuntu: apt-get install libpango-1.0-0 libpangoft2-1.0-0"
        )

    if markdown_path is None:
        markdown_path = create_markdown_report(research_json_path, output_dir)

    md_content = markdown_path.read_text(encoding="utf-8")
    html_content = report_html(md_content)

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        f"<style>{_PDF_CSS}</style></head><body>{html_content}</body></html>"
    )

    output_dir = Path(output_dir or research_json_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(research_json_path.read_text(encoding="utf-8"))
    output_path = output_dir / report_filename(
        (data.get("extraction") or {}).get("organization"), "pdf"
    )
    HTML(string=full_html).write_pdf(output_path)
    return output_path


def export_research_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
    formats: Optional[list[str]] = None,
    on_warning: Optional[Callable[[str], None]] = None,
) -> dict[str, Path]:
    """Write the requested export formats, never failing the caller.

    A PDF failure must not discard a research run that already succeeded, so
    it is reported through `on_warning` rather than raised. Without that the
    Download PDF button simply disappears with no explanation.
    """
    formats = formats or ["markdown", "pdf"]
    output_dir = Path(output_dir or "exports")
    output_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}
    markdown_path = None
    if "markdown" in formats:
        markdown_path = create_markdown_report(research_json_path, output_dir)
        results["markdown"] = markdown_path
    if "pdf" in formats:
        try:
            results["pdf"] = create_pdf_report(
                research_json_path, output_dir, markdown_path
            )
        except Exception as exc:
            # Markdown is still available; PDF failure shouldn't sink the job.
            log.exception("PDF export failed")
            if on_warning:
                on_warning(
                    f"PDF generation failed, Markdown is still available: {exc}"
                )
    return results
