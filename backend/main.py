import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

import fastapi
import fastapi.middleware.cors
from google import genai
from pydantic import BaseModel

from prompts import EXTRACT_DEEP_RESEARCH_PROMPT_PRO

app = fastapi.FastAPI()

app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory task store (for production, use Redis or a database)
tasks: dict[str, dict[str, Any]] = {}


def extract_json_from_text(text: str) -> str:
    """Extract JSON object from text, handling markdown code blocks and plain text."""
    # First, try to extract from markdown code blocks
    code_block_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if code_block_match:
        potential_json = code_block_match.group(1)
        brace_count = 0
        start_idx = 0
        for i, char in enumerate(potential_json):
            if char == '{':
                if brace_count == 0:
                    start_idx = i
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return potential_json[start_idx:i+1]
    
    # If no code block, find JSON object directly using balanced brace matching
    brace_count = 0
    start_idx = text.find('{')
    if start_idx != -1:
        for i in range(start_idx, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx:i+1]
    
    return text


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


def create_markdown_report(extraction: dict, research_result: str) -> str:
    """Create a formatted Markdown report from extraction and research result."""
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
    lines.append(research_result)
    
    # Footer
    lines.append("\n\n---\n")
    lines.append(f"\n*Report generated by Impact Evidence Research Tool*\n")
    
    return "\n".join(lines)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


class ResearchRequest(BaseModel):
    taskId: str
    researchPrompt: str


class ExportRequest(BaseModel):
    taskId: str
    format: str  # "markdown", "pdf", or "both"
    extraction: dict
    researchResult: str


@app.post("/extract")
async def extract_from_pdf(file: fastapi.UploadFile = fastapi.File(...)):
    """Extract information from uploaded PDF using Gemini."""
    try:
        # Read PDF bytes
        pdf_bytes = await file.read()
        
        # Initialize Gemini client
        client = genai.Client()
        
        # Call Gemini to extract information
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-05-20",
            contents=[
                EXTRACT_DEEP_RESEARCH_PROMPT_PRO,
                genai.types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            ],
        )
        
        # Parse response
        response_text = response.text.strip()
        json_str = extract_json_from_text(response_text)
        parsed_json = json.loads(json_str)
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Store task data
        tasks[task_id] = {
            "status": "extracted",
            "extraction": parsed_json.get("extraction", {}),
            "research_prompt": parsed_json.get("research_prompt", ""),
            "created_at": datetime.now().isoformat(),
        }
        
        return {
            "taskId": task_id,
            "extraction": parsed_json.get("extraction", {}),
            "researchPrompt": parsed_json.get("research_prompt", ""),
        }
        
    except json.JSONDecodeError as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Failed to parse extraction: {str(e)}")
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@app.post("/research")
async def start_research(request: ResearchRequest):
    """Start deep research task."""
    task_id = request.taskId
    
    if task_id not in tasks:
        raise fastapi.HTTPException(status_code=404, detail="Task not found")
    
    # Update task status
    tasks[task_id]["status"] = "pending"
    tasks[task_id]["research_prompt"] = request.researchPrompt
    
    # Start research in background
    asyncio.create_task(run_deep_research(task_id, request.researchPrompt))
    
    return {"taskId": task_id, "status": "started"}


async def run_deep_research(task_id: str, research_prompt: str):
    """Run deep research in background."""
    try:
        tasks[task_id]["status"] = "running"
        
        client = genai.Client()
        
        # Start deep research interaction
        interaction = client.interactions.create(
            input=research_prompt,
            agent="deep-research-pro-preview-12-2025",
            background=True,
        )
        
        tasks[task_id]["interaction_id"] = interaction.id
        
        # Poll for completion
        while True:
            interaction = client.interactions.get(interaction.id)
            
            if interaction.status == "completed":
                result_text = interaction.outputs[-1].text if interaction.outputs else "No output available"
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["result"] = result_text
                break
                
            elif interaction.status == "failed":
                error_msg = interaction.error if hasattr(interaction, 'error') else "Unknown error"
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = error_msg
                break
                
            else:
                await asyncio.sleep(10)
                
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """Get status of a research task."""
    if task_id not in tasks:
        raise fastapi.HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    
    response = {
        "status": task.get("status", "unknown"),
    }
    
    if task.get("interaction_id"):
        response["interactionId"] = task["interaction_id"]
    
    if task.get("result"):
        response["result"] = task["result"]
    
    if task.get("error"):
        response["error"] = task["error"]
    
    return response


@app.post("/export")
async def export_report(request: ExportRequest):
    """Generate and return downloadable report files."""
    try:
        # Create markdown content
        markdown_content = create_markdown_report(
            request.extraction,
            request.researchResult
        )
        
        result = {}
        
        if request.format in ["markdown", "both"]:
            # Return markdown as data URL for download
            result["markdownContent"] = markdown_content
            # Create a simple data URL for the markdown
            import base64
            markdown_b64 = base64.b64encode(markdown_content.encode()).decode()
            result["markdownUrl"] = f"data:text/markdown;base64,{markdown_b64}"
        
        if request.format in ["pdf", "both"]:
            # PDF generation requires additional dependencies
            # For now, we'll just return markdown and note that PDF is not available
            try:
                import markdown as md
                
                html_content = md.markdown(
                    markdown_content,
                    extensions=['tables', 'fenced_code', 'nl2br']
                )
                
                # Create HTML document
                css_style = """
                body { font-family: Georgia, serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
                h2 { color: #34495e; border-bottom: 2px solid #95a5a6; padding-bottom: 5px; }
                table { border-collapse: collapse; width: 100%; margin: 20px 0; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #3498db; color: white; }
                """
                
                full_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>{css_style}</style></head>
<body>{html_content}</body>
</html>"""
                
                html_b64 = base64.b64encode(full_html.encode()).decode()
                result["pdfUrl"] = f"data:text/html;base64,{html_b64}"
                
            except ImportError:
                # If markdown package not available, skip PDF
                pass
        
        return result
        
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
