import json
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from prompts import EXTRACT_DEEP_RESEARCH_PROMPT_PRO

load_dotenv()

notes_dir = Path("notes")
pdf_paths = sorted(notes_dir.glob("*.pdf"))
if not pdf_paths:
    raise FileNotFoundError("No PDF files found in ./notes")

pdf_path = pdf_paths[0]
pdf_bytes = pdf_path.read_bytes()

client = genai.Client()
response = client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=[
        EXTRACT_DEEP_RESEARCH_PROMPT_PRO,
        genai.types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
    ],
)

# Extract JSON from response text (handle markdown code blocks if present)
response_text = response.text.strip()

def extract_json_from_text(text):
    """Extract JSON object from text, handling markdown code blocks and plain text."""
    # First, try to extract from markdown code blocks
    # Match ```json or ``` followed by JSON, handling nested braces
    code_block_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if code_block_match:
        # Use balanced brace matching for the content inside code blocks
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
    
    # Fallback: return the text as-is (might fail parsing, but we'll handle that)
    return text

json_str = extract_json_from_text(response_text)

# Clean up the JSON string (remove any trailing text after closing brace)
json_str = json_str.strip()

# Parse the JSON
try:
    parsed_json = json.loads(json_str)
except json.JSONDecodeError as e:
    print(f"Error parsing JSON: {e}")
    print(f"JSON string (first 1000 chars): {json_str[:1000]}...")
    print(f"\nFull response text (first 500 chars): {response_text[:500]}...")
    raise

# Save the parsed JSON structure
json_dir = Path("json")
json_dir.mkdir(parents=True, exist_ok=True)
output_path = json_dir / f"{pdf_path.stem}.json"
output_path.write_text(json.dumps(parsed_json, ensure_ascii=False, indent=2))

print(f"Successfully saved JSON to {output_path}")
