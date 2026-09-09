"""OpenAI Deep Research via the Responses API in background mode."""

import os
import time

from ._polling import (
    DEFAULT_TIMEOUT_S,
    POLL_REQUEST_TIMEOUT_S,
    Deadline,
    fetch_with_retry,
)
from .base import EventCallback, ModelOption, ResearchProvider

POLL_INTERVAL_S = 15

# o3-deep-research bills output at $40/M, so an uncapped run is an uncapped
# bill. The report template tops out at 10 studies plus 5 reviews, which fits
# comfortably inside this ceiling.
MAX_OUTPUT_TOKENS = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "32000"))


class OpenAIProvider(ResearchProvider):
    id = "openai"
    label = "OpenAI Deep Research"
    description = "o-series deep research models via the Responses API."
    env_key = "OPENAI_API_KEY"

    def models(self) -> list[ModelOption]:
        return [
            ModelOption(
                id="o4-mini-deep-research",
                label="o4-mini Deep Research (Fast)",
                tier="fast",
                note="Faster and cheaper ($2/M input, $8/M output).",
            ),
            ModelOption(
                id="o3-deep-research",
                label="o3 Deep Research",
                tier="max",
                note="Most thorough synthesis ($10/M input, $40/M output).",
            ),
        ]

    def run(self, prompt: str, model_id: str, on_event: EventCallback) -> str:
        from openai import OpenAI

        client = OpenAI(timeout=POLL_REQUEST_TIMEOUT_S)
        response = client.responses.create(
            model=model_id,
            input=prompt,
            background=True,
            store=True,  # required to retrieve a background response later
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tools=[{"type": "web_search_preview"}],
        )
        response_id = response.id
        on_event(f"Research task created ({model_id})", response_id)

        last_status = None
        deadline = Deadline(DEFAULT_TIMEOUT_S)
        while not deadline.expired():
            response = fetch_with_retry(
                lambda: client.responses.retrieve(response_id),
                on_transient=lambda msg: on_event(msg, response_id),
                what="research status check",
            )
            status = str(response.status)

            if status == "completed":
                text = response.output_text
                if not text:
                    raise RuntimeError("Research completed but returned no output")
                on_event("Research completed", response.id)
                return text

            if status == "incomplete":
                # Usually means the output-token ceiling was reached. A
                # truncated report is still worth far more than discarding a
                # run that has already been paid for.
                partial = response.output_text
                if partial:
                    on_event(
                        "Provider stopped early; returning the partial report",
                        response_id,
                    )
                    return partial

            if status in ("failed", "cancelled", "incomplete"):
                error = getattr(response, "error", None)
                detail = getattr(error, "message", None) if error else None
                raise RuntimeError(
                    f"OpenAI Deep Research ended with status={status}"
                    + (f": {detail}" if detail else "")
                )

            if status != last_status:
                on_event(f"Status: {status}", response_id)
                last_status = status

            time.sleep(POLL_INTERVAL_S)

        raise TimeoutError(
            f"Research did not complete within {deadline.minutes} minutes. "
            f"It may still finish on OpenAI's side (response id: {response_id})"
        )
