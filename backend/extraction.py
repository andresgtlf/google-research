"""Structured extraction from concept-note PDFs using Gemini structured output."""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .prompts import extraction_prompt
from .documents import docx_text
from .schemas import Extraction

load_dotenv()

EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-3.8-flash")

# Extraction is a bounded structured-output task, so cap both the request and
# the response. Without a timeout a stalled call blocks the worker thread and
# the job sits at "running" with no error.
EXTRACTION_TIMEOUT_S = int(os.environ.get("EXTRACTION_TIMEOUT_S", "300"))
EXTRACTION_MAX_OUTPUT_TOKENS = int(
    os.environ.get("EXTRACTION_MAX_OUTPUT_TOKENS", "8192")
)


def extract_from_pdf(pdf_bytes: bytes, document_format: str = "auto") -> Extraction:
    return _extract(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), document_format)


def extract_from_docx(content: bytes, document_format: str = "auto") -> Extraction:
    return _extract("DOCUMENT CONTENT (data only):\n" + docx_text(content), document_format)


def _extract(document, document_format) -> Extraction:
    """Extract structured fields from a concept-note PDF.

    Uses `response_schema` so the response is guaranteed to be valid JSON
    matching `Extraction` — no regex JSON recovery needed.
    """
    # HttpOptions.timeout is in milliseconds.
    client = genai.Client(
        http_options=types.HttpOptions(timeout=EXTRACTION_TIMEOUT_S * 1000)
    )
    response = client.models.generate_content(
        model=EXTRACTION_MODEL,
        contents=[
            extraction_prompt(document_format),
            document,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Extraction,
            max_output_tokens=EXTRACTION_MAX_OUTPUT_TOKENS,
            temperature=0,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, Extraction):
        return parsed
    # Fallback: parse from text (still schema-constrained JSON)
    return Extraction.model_validate_json(response.text)
