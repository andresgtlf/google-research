import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import markdown
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


def setup_weasyprint_library_paths():
    """Set up library paths for WeasyPrint on macOS with Homebrew."""
    try:
        # Try to find brew
        brew_prefix = subprocess.check_output(
            ["brew", "--prefix"], stderr=subprocess.DEVNULL
        ).decode().strip()
        
        # Get library paths for required packages
        lib_paths = []
        packages = ["pango", "glib", "gdk-pixbuf", "harfbuzz", "fontconfig"]
        
        for package in packages:
            try:
                prefix = subprocess.check_output(
                    ["brew", "--prefix", package], stderr=subprocess.DEVNULL
                ).decode().strip()
                lib_path = f"{prefix}/lib"
                if os.path.exists(lib_path):
                    lib_paths.append(lib_path)
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        
        if lib_paths:
            lib_path_str = ":".join(lib_paths)
            # Set both LIBRARY_PATH and DYLD_LIBRARY_PATH
            os.environ["LIBRARY_PATH"] = lib_path_str + (
                f":{os.environ.get('LIBRARY_PATH', '')}" 
                if os.environ.get("LIBRARY_PATH") else ""
            )
            os.environ["DYLD_LIBRARY_PATH"] = lib_path_str + (
                f":{os.environ.get('DYLD_LIBRARY_PATH', '')}" 
                if os.environ.get("DYLD_LIBRARY_PATH") else ""
            )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Homebrew not found or not available, skip setup
        pass


# Set up library paths before importing WeasyPrint
setup_weasyprint_library_paths()

# Try to import PDF libraries
WEASYPRINT_AVAILABLE = False
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    # OSError can occur if system libraries are missing
    WEASYPRINT_AVAILABLE = False

# Debug logging helpers
DEBUG_LOG_PATH = Path("/Users/andressolarte/Library/CloudStorage/GoogleDrive-andres@gitlabfoundation.org/My Drive/GitLab_IA/Google_Research/.cursor/debug.log")


def _dbg_log(message: str, data: dict, hypothesis_id: str, run_id: str = "run1", location: str = "export.py"):
    """Append a single NDJSON debug log line."""
    try:
        log_entry = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        # Never let logging break the main flow
        pass


def _max_word_length(text: str) -> int:
    """Compute longest whitespace-delimited token length."""
    if not text:
        return 0
    return max((len(word) for word in text.split()), default=0)


def format_extraction_summary(extraction: dict) -> str:
    """Format the extraction data into a readable summary section."""
    lines = []
    
    lines.append("## Project Overview\n")
    
    if extraction.get("organization"):
        lines.append(f"**Organization:** {extraction['organization']}\n")
    
    if extraction.get("project_title"):
        lines.append(f"**Project Title:** {extraction['project_title']}\n")
    
    if extraction.get("summary"):
        lines.append(f"\n**Summary:**\n{extraction['summary']}\n")
    
    if extraction.get("intervention_types"):
        types = ", ".join(extraction["intervention_types"])
        lines.append(f"\n**Intervention Types:** {types}\n")
    
    if extraction.get("mechanisms_to_affect_income"):
        lines.append(f"\n**Mechanisms to Affect Income:**\n{extraction['mechanisms_to_affect_income']}\n")
    
    # Geography & Population
    lines.append("\n## Geography & Population\n")
    
    if extraction.get("country"):
        lines.append(f"**Country:** {extraction['country']}")
        if extraction.get("region"):
            lines.append(f" ({extraction['region']})")
        lines.append("\n")
    
    if extraction.get("population"):
        pop = extraction["population"]
        if pop.get("description"):
            lines.append(f"\n**Target Population:** {pop['description']}\n")
        
        if pop.get("youth_pct") is not None:
            lines.append(f"**Youth Percentage:** {pop['youth_pct']}%\n")
        
        if pop.get("women_pct") is not None:
            lines.append(f"**Women Percentage:** {pop['women_pct']}%\n")
        
        if pop.get("baseline_income_note"):
            lines.append(f"\n**Baseline Income Note:** {pop['baseline_income_note']}\n")
    
    # Scale
    if extraction.get("scale"):
        scale = extraction["scale"]
        lines.append("\n## Scale\n")
        
        if scale.get("by_group"):
            lines.append("**Directly Served:**\n")
            for group, count in scale["by_group"].items():
                lines.append(f"- {group}: {count}\n")
        
        if scale.get("time_horizon_years"):
            lines.append(f"\n**Time Horizon:** {scale['time_horizon_years']} years\n")
    
    # Intended Outcomes
    if extraction.get("intended_outcomes"):
        outcomes = extraction["intended_outcomes"]
        lines.append("\n## Intended Outcomes\n")
        
        if outcomes.get("direct"):
            lines.append("**Direct Outcomes:**\n")
            for outcome in outcomes["direct"]:
                lines.append(f"- {outcome}\n")
        
        if outcomes.get("indirect"):
            lines.append("\n**Indirect Outcomes:**\n")
            for outcome in outcomes["indirect"]:
                lines.append(f"- {outcome}\n")
        
        if outcomes.get("magnitudes"):
            lines.append("\n**Expected Magnitudes:**\n")
            for magnitude in outcomes["magnitudes"]:
                lines.append(f"- {magnitude}\n")
    
    # Funding
    if extraction.get("funding"):
        funding = extraction["funding"]
        lines.append("\n## Funding\n")
        
        if funding.get("gitlab_request_usd"):
            lines.append(f"**GitLab Foundation Request:** ${funding['gitlab_request_usd']:,}\n")
        
        if funding.get("total_project_budget_usd"):
            lines.append(f"**Total Project Budget:** ${funding['total_project_budget_usd']:,}\n")
    
    # Self-reported Evidence
    if extraction.get("self_reported_evidence"):
        lines.append("\n## Self-Reported Evidence\n")
        for evidence in extraction["self_reported_evidence"]:
            lines.append(f"- {evidence}\n")
    
    return "\n".join(lines)


def create_markdown_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Create a formatted Markdown report from a research JSON file.
    
    Args:
        research_json_path: Path to the research JSON file
        output_dir: Directory to save the markdown file (default: same as JSON file)
        
    Returns:
        Path to the created markdown file
    """
    # Read JSON file
    with open(research_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Extract data
    extraction = data.get("extraction", {})
    research_result = data.get("research_result", {})
    research_text = research_result.get("result", "")
    
    # Build markdown content
    lines = []
    
    # Title
    org_name = extraction.get("organization", "Unknown Organization")
    project_title = extraction.get("project_title", "Research Report")
    lines.append(f"# {org_name}\n")
    lines.append(f"## {project_title}\n")
    lines.append(f"\n*Generated on {datetime.now().strftime('%B %d, %Y')}*\n")
    lines.append("\n---\n")
    
    # Project Overview
    lines.append(format_extraction_summary(extraction))
    
    # Research Results
    lines.append("\n---\n")
    lines.append("\n# Deep Research Results\n")
    lines.append("\n")
    lines.append(research_text)
    
    # Footer
    lines.append("\n\n---\n")
    lines.append(f"\n*Report generated from: {research_json_path.name}*\n")
    
    # Write markdown file
    if output_dir is None:
        output_dir = research_json_path.parent
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_filename = f"{research_json_path.stem}.md"
    output_path = output_dir / output_filename
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    return output_path


def create_pdf_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
    markdown_path: Optional[Path] = None,
) -> Path:
    """
    Create a PDF report from a research JSON file.
    
    Args:
        research_json_path: Path to the research JSON file
        output_dir: Directory to save the PDF file (default: same as JSON file)
        markdown_path: Optional path to existing markdown file (will create if not provided)
        
    Returns:
        Path to the created PDF file
    """
    if not PDF_AVAILABLE:
        raise ImportError(
            "PDF generation requires 'markdown' package. "
            "Install it with: uv pip install markdown"
        )
    
    if not WEASYPRINT_AVAILABLE:
        raise ImportError(
            "PDF generation requires 'weasyprint' package and system libraries. "
            "Install weasyprint with: uv pip install weasyprint\n"
            "On macOS, install system dependencies with: brew install pango gdk-pixbuf libffi\n"
            "On Linux (Ubuntu/Debian): sudo apt-get install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0\n"
            "Alternatively, you can export to Markdown and convert to PDF using other tools."
        )
    
    # Create markdown first if not provided
    if markdown_path is None:
        markdown_path = create_markdown_report(research_json_path, output_dir)
    
    #region agent log
    _dbg_log(
        "create_pdf_report_entry",
        {
            "research_json_path": str(research_json_path),
            "output_dir": str(output_dir) if output_dir else None,
            "markdown_path": str(markdown_path),
        },
        hypothesis_id="H1",
        run_id="run1",
        location="export.py:create_pdf_report:entry",
    )
    #endregion

    # Read markdown content
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_content = f.read()
    
    max_word_len = _max_word_length(markdown_content)

    #region agent log
    _dbg_log(
        "markdown_loaded",
        {
            "markdown_len": len(markdown_content),
            "max_word_len": max_word_len,
        },
        hypothesis_id="H2",
        run_id="run1",
        location="export.py:create_pdf_report:markdown",
    )
    #endregion

    # Convert markdown to HTML
    html_content = markdown.markdown(
        markdown_content,
        extensions=['tables', 'fenced_code', 'nl2br']
    )

    table_count = html_content.count("<table")

    #region agent log
    _dbg_log(
        "html_converted",
        {
            "html_len": len(html_content),
            "table_count": table_count,
        },
        hypothesis_id="H3",
        run_id="run1",
        location="export.py:create_pdf_report:html",
    )
    #endregion
    
    # Add CSS styling
    css_style = """
    @page {
        size: A4;
        margin: 1cm;
    }
    body {
        font-family: 'Georgia', 'Times New Roman', serif;
        line-height: 1.6;
        color: #333;
        max-width: 100%;
    }
    h1 {
        color: #2c3e50;
        border-bottom: 3px solid #3498db;
        padding-bottom: 10px;
        margin-top: 30px;
    }
    h2 {
        color: #34495e;
        border-bottom: 2px solid #95a5a6;
        padding-bottom: 5px;
        margin-top: 25px;
    }
    h3 {
        color: #555;
        margin-top: 20px;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 20px 0;
        font-size: 0.7em;
        table-layout: fixed;
        word-wrap: break-word;
        overflow-wrap: break-word;
        max-width: 100%;
        box-sizing: border-box;
    }
    table th, table td {
        border: 1px solid #ddd;
        padding: 3px 4px;
        text-align: left;
        word-wrap: break-word;
        overflow-wrap: break-word;
        hyphens: auto;
        box-sizing: border-box;
    }
    table th {
        background-color: #3498db;
        color: white;
        font-weight: bold;
        font-size: 0.8em;
    }
    table td {
        font-size: 0.7em;
        vertical-align: top;
    }
    table tr:nth-child(even) {
        background-color: #f2f2f2;
    }
    /* Ensure tables don't overflow page */
    table {
        page-break-inside: auto;
    }
    table tr {
        page-break-inside: avoid;
        page-break-after: auto;
    }
    /* Wrap table in container to prevent overflow */
    body > * {
        max-width: 100%;
        box-sizing: border-box;
    }
    code {
        background-color: #f4f4f4;
        padding: 2px 4px;
        border-radius: 3px;
        font-family: 'Courier New', monospace;
    }
    pre {
        background-color: #f4f4f4;
        padding: 10px;
        border-radius: 5px;
        overflow-x: auto;
    }
    ul, ol {
        margin-left: 20px;
    }
    blockquote {
        border-left: 4px solid #3498db;
        padding-left: 15px;
        margin-left: 0;
        color: #555;
        font-style: italic;
    }
    """

    #region agent log
    _dbg_log(
        "css_applied",
        {
            "page_margin_cm": 1,
            "table_font_size_em": 0.7,
            "table_layout": "fixed",
        },
        hypothesis_id="H4",
        run_id="run1",
        location="export.py:create_pdf_report:css",
    )
    #endregion
    
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>{css_style}</style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # Convert HTML to PDF
    if output_dir is None:
        output_dir = research_json_path.parent
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_filename = f"{research_json_path.stem}.pdf"
    output_path = output_dir / output_filename
    
    HTML(string=full_html).write_pdf(output_path)

    try:
        pdf_size = output_path.stat().st_size
    except Exception:
        pdf_size = None

    #region agent log
    _dbg_log(
        "pdf_written",
        {
            "output_path": str(output_path),
            "pdf_size_bytes": pdf_size,
            "html_len": len(full_html),
            "table_count": table_count,
            "max_word_len": max_word_len,
        },
        hypothesis_id="H1",
        run_id="run1",
        location="export.py:create_pdf_report:write",
    )
    #endregion
    
    return output_path


def export_research_report(
    research_json_path: Path,
    output_dir: Optional[Path] = None,
    formats: list[str] = ["markdown", "pdf"],
) -> dict[str, Path]:
    """
    Export research report in multiple formats.
    
    Args:
        research_json_path: Path to the research JSON file
        output_dir: Directory to save exported files (default: 'exports' directory)
        formats: List of formats to export ('markdown', 'pdf')
        
    Returns:
        Dictionary mapping format names to output file paths
    """
    if output_dir is None:
        output_dir = Path("exports")
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    markdown_path = None
    
    if "markdown" in formats:
        markdown_path = create_markdown_report(research_json_path, output_dir)
        results["markdown"] = markdown_path
        print(f"✓ Markdown exported to: {markdown_path}")
    
    if "pdf" in formats:
        try:
            pdf_path = create_pdf_report(research_json_path, output_dir, markdown_path)
            results["pdf"] = pdf_path
            print(f"✓ PDF exported to: {pdf_path}")
        except ImportError as e:
            print(f"✗ PDF export failed: {e}")
            if markdown_path:
                print(f"\n  Note: Markdown file is available at: {markdown_path}")
                print("  You can convert it to PDF using:")
                print("    - pandoc: pandoc file.md -o file.pdf")
                print("    - Online tools: https://www.markdowntopdf.com/")
                print("    - VS Code: Install 'Markdown PDF' extension")
    
    return results


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python export.py <research_json_file> [output_dir] [formats]")
        print("Example: python export.py research_results/ConceptNote-FutureFit_research.json exports markdown,pdf")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)
    
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("exports")
    formats = sys.argv[3].split(",") if len(sys.argv) > 3 else ["markdown", "pdf"]
    
    export_research_report(json_path, output_dir, formats)

