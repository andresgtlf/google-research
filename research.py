import json
import time
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from google import genai

load_dotenv()


def perform_deep_research(
    research_prompt: str,
    interaction_id: Optional[str] = None,
    poll_interval: int = 10,
    agent: str = "deep-research-pro-preview-12-2025",
) -> dict:
    """
    Perform deep research using Gemini Deep Research API.
    
    Args:
        research_prompt: The research prompt to execute
        interaction_id: Optional existing interaction ID to check status
        poll_interval: Seconds to wait between status checks
        agent: The agent name to use for research
        
    Returns:
        Dictionary with interaction details and results
    """
    client = genai.Client()
    
    if interaction_id:
        # Check status of existing interaction
        interaction = client.interactions.get(interaction_id)
        print(f"Checking status of existing interaction: {interaction.id}")
    else:
        # Start new research task
        print(f"Starting deep research...")
        print(f"Research prompt preview: {research_prompt[:100]}...")
        
        interaction = client.interactions.create(
            input=research_prompt,
            agent=agent,
            background=True,
        )
        
        print(f"Research started: {interaction.id}")
        print(f"Status: {interaction.status}")
    
    # Poll for completion
    while True:
        interaction = client.interactions.get(interaction.id)
        
        if interaction.status == "completed":
            print(f"\n✓ Research completed successfully!")
            result_text = interaction.outputs[-1].text if interaction.outputs else "No output available"
            
            return {
                "interaction_id": interaction.id,
                "status": interaction.status,
                "research_prompt": research_prompt,
                "result": result_text,
                "outputs_count": len(interaction.outputs) if interaction.outputs else 0,
            }
            
        elif interaction.status == "failed":
            error_msg = interaction.error if hasattr(interaction, 'error') else "Unknown error"
            print(f"\n✗ Research failed: {error_msg}")
            
            return {
                "interaction_id": interaction.id,
                "status": interaction.status,
                "research_prompt": research_prompt,
                "error": error_msg,
            }
            
        elif interaction.status in ["running", "pending"]:
            print(f"Status: {interaction.status}... (waiting {poll_interval}s)")
            time.sleep(poll_interval)
        else:
            print(f"Status: {interaction.status}... (waiting {poll_interval}s)")
            time.sleep(poll_interval)


def process_json_file(
    json_path: Path,
    results_dir: Path,
    poll_interval: int = 10,
    agent: str = "deep-research-pro-preview-12-2025",
) -> Path:
    """
    Process a single JSON file: extract research prompt and perform deep research.
    
    Args:
        json_path: Path to the JSON file containing extraction and research_prompt
        results_dir: Directory to save research results
        poll_interval: Seconds to wait between status checks
        agent: The agent name to use for research
        
    Returns:
        Path to the saved research results file
    """
    # Read JSON file
    print(f"\n{'='*60}")
    print(f"Processing: {json_path.name}")
    print(f"{'='*60}")
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Extract research prompt
    if "research_prompt" not in data:
        raise ValueError(f"No 'research_prompt' field found in {json_path}")
    
    research_prompt = data["research_prompt"]
    
    if not research_prompt or not research_prompt.strip():
        raise ValueError(f"Empty 'research_prompt' in {json_path}")
    
    # Perform deep research
    result = perform_deep_research(
        research_prompt=research_prompt,
        poll_interval=poll_interval,
        agent=agent,
    )
    
    # Combine original data with research results
    output_data = {
        "source_json": str(json_path),
        "extraction": data.get("extraction", {}),
        "original_research_prompt": research_prompt,
        "research_result": result,
    }
    
    # Save results
    results_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"{json_path.stem}_research.json"
    output_path = results_dir / output_filename
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Research results saved to: {output_path}")
    
    return output_path


def process_all_json_files(
    json_dir: Path = Path("json"),
    results_dir: Path = Path("research_results"),
    poll_interval: int = 10,
    agent: str = "deep-research-pro-preview-12-2025",
) -> List[Path]:
    """
    Process all JSON files in the json directory.
    
    Args:
        json_dir: Directory containing JSON files
        results_dir: Directory to save research results
        poll_interval: Seconds to wait between status checks
        agent: The agent name to use for research
        
    Returns:
        List of paths to saved research results files
    """
    json_files: List[Path] = sorted(json_dir.glob("*.json"))
    
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {json_dir}")
    
    print(f"Found {len(json_files)} JSON file(s) to process")
    
    results = []
    for json_file in json_files:
        try:
            result_path = process_json_file(
                json_path=json_file,
                results_dir=results_dir,
                poll_interval=poll_interval,
                agent=agent,
            )
            results.append(result_path)
        except Exception as e:
            print(f"\n✗ Error processing {json_file.name}: {e}")
            continue
    
    return results


if __name__ == "__main__":
    import sys
    
    # Allow specifying a specific JSON file or process all
    if len(sys.argv) > 1:
        # Process specific file
        json_path = Path(sys.argv[1])
        if not json_path.exists():
            print(f"Error: File not found: {json_path}")
            sys.exit(1)
        
        results_dir = Path("research_results")
        process_json_file(json_path, results_dir)
    else:
        # Process all JSON files
        json_dir = Path("json")
        results_dir = Path("research_results")
        process_all_json_files(json_dir, results_dir)

