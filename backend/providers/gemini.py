"""Gemini Deep Research via the Interactions API.

Requires google-genai >= 2.0.0. The May 2026 Interactions API change made the
older schema a hard 400 ("The legacy Interactions API schema is no longer
supported"), so every research run on google-genai 1.x fails at create() and
no report is ever produced. The same change renamed `Interaction.outputs` to
`Interaction.steps` and added an `output_text` convenience property, which is
what this module reads.
"""

import os
import time
from typing import Any

from ._polling import (
    DEFAULT_TIMEOUT_S,
    POLL_REQUEST_TIMEOUT_S,
    Deadline,
    fetch_with_retry,
)
from .base import EventCallback, ModelOption, ResearchProvider

POLL_INTERVAL_S = 10

# How often to confirm in the event log that a quiet run is still alive.
HEARTBEAT_INTERVAL_S = int(os.environ.get("RESEARCH_HEARTBEAT_S", "120"))

# Thought summaries are the only real signal the API gives us about what the
# agent is doing mid-run. They cost a small amount of output on top of an
# 80k-token report, and they are what turns a 20-minute blank wait into
# visible progress, so they are on by default. Set to "none" to save them.
THINKING_SUMMARIES = os.environ.get("GEMINI_THINKING_SUMMARIES", "auto")


def _text_of(block: Any) -> list[str]:
    """Text carried by one output block, skipping thoughts and tool traces."""
    if str(getattr(block, "type", "") or "") == "thought":
        return []  # agent reasoning, not report content
    text = getattr(block, "text", None)
    if isinstance(text, str) and text.strip():
        return [text]
    # `steps`-shaped responses nest their parts under `.content`.
    nested = getattr(block, "content", None)
    if isinstance(nested, (list, tuple)):
        out: list[str] = []
        for part in nested:
            out.extend(_text_of(part))
        return out
    return []


def _trace_blocks(interaction: Any) -> list[Any]:
    """Flatten the step timeline into content blocks.

    A `Step` wraps its blocks under `.content`; the pre-May-2026 `outputs`
    list held the blocks directly.
    """
    raw = getattr(interaction, "steps", None) or getattr(interaction, "outputs", None) or []
    blocks: list[Any] = []
    for item in raw:
        nested = getattr(item, "content", None)
        if isinstance(nested, (list, tuple)):
            blocks.extend(nested)
        else:
            blocks.append(item)
    return blocks


def _collect_report_text(interaction: Any) -> str:
    """Pull the final report out of a finished interaction.

    Prefer the SDK's `output_text`, which joins the text parts of the final
    model output for us. Fall back to walking the step timeline: `steps` (and
    the pre-May-2026 `outputs`) is a heterogeneous list of content blocks
    (thoughts, search calls, search results, URL fetches, report text), and
    only text blocks carry `.text` — so indexing the last element blindly
    raises AttributeError whenever a run ends on a tool-trace block.
    """
    direct = getattr(interaction, "output_text", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    for attr in ("steps", "outputs"):
        blocks = getattr(interaction, attr, None) or []
        chunks: list[str] = []
        for block in blocks:
            chunks.extend(_text_of(block))
        text = "\n".join(chunks).strip()
        if text:
            return text
    return ""


def _summarize_progress(interaction: Any) -> str:
    """A short, real description of what the agent has done so far."""
    blocks = _trace_blocks(interaction)
    searches = sum(
        1
        for b in blocks
        if "search" in str(getattr(b, "type", "") or "") and "call" in str(getattr(b, "type", "") or "")
    )
    thoughts = [
        (getattr(b, "summary", None) or "").strip()
        for b in blocks
        if str(getattr(b, "type", "") or "") == "thought"
    ]
    latest = next((t for t in reversed(thoughts) if t), "")
    parts: list[str] = []
    if searches:
        parts.append(f"{searches} searches run")
    if latest:
        parts.append(latest.splitlines()[0][:180])
    return " — ".join(parts) if parts else ""


class GeminiProvider(ResearchProvider):
    recommended_tier = "max"
    id = "gemini"
    label = "Gemini Deep Research"
    description = "Google's autonomous Deep Research agent (Interactions API)."
    env_key = "GOOGLE_API_KEY"

    def models(self) -> list[ModelOption]:
        return [
            ModelOption(
                id="deep-research-preview-04-2026",
                label="Deep Research (Fast)",
                tier="fast",
                note="Faster, lighter research. Choose Max for a comprehensive literature review.",
            ),
            ModelOption(
                id="deep-research-max-preview-04-2026",
                label="Deep Research Max (recommended)",
                tier="max",
                note="Recommended for literature reviews: deeper context gathering and synthesis. Allow up to 60 minutes; costs more than Fast.",
            ),
            ModelOption(
                id="deep-research-pro-preview-12-2025",
                label="Deep Research Pro (Dec 2025, legacy)",
                tier="legacy",
                note="Legacy compatibility only. Prefer Max or Fast for new reviews.",
            ),
        ]

    def run(self, prompt: str, model_id: str, on_event: EventCallback) -> str:
        from google import genai
        from google.genai import types

        # HttpOptions.timeout is in MILLISECONDS. Without it a stalled socket
        # blocks the worker thread indefinitely and the job hangs at
        # "running" with no error and no way out.
        client = genai.Client(
            http_options=types.HttpOptions(timeout=POLL_REQUEST_TIMEOUT_S * 1000)
        )

        agent_config: dict[str, Any] = {
            "type": "deep-research",
            # Human-in-the-loop planning makes the agent return a plan and
            # then wait for the user to confirm it in a following turn. A
            # background job has no way to confirm, so the interaction would
            # sit in `requires_action` until our deadline and deliver nothing.
            # Set explicitly rather than relying on the API default.
            "collaborative_planning": False,
            "thinking_summaries": THINKING_SUMMARIES,
        }
        interaction = client.interactions.create(
            input=prompt,
            agent=model_id,
            background=True,
            agent_config=agent_config,
        )
        interaction_id = interaction.id
        on_event(f"Research task created ({model_id})", interaction_id)

        last_status = None
        last_progress = ""
        started = time.monotonic()
        next_heartbeat = started + HEARTBEAT_INTERVAL_S
        deadline = Deadline(DEFAULT_TIMEOUT_S)

        while not deadline.expired():
            interaction = fetch_with_retry(
                lambda: client.interactions.get(interaction_id),
                on_transient=lambda msg: on_event(msg, interaction_id),
                what="research status check",
            )
            status = str(getattr(interaction, "status", "") or "unknown")

            if status == "completed":
                report = _collect_report_text(interaction)
                if not report:
                    raise RuntimeError(
                        "Research completed but no report text was returned "
                        f"(interaction id: {interaction_id})"
                    )
                on_event("Research completed", interaction_id)
                return report

            if status in ("failed", "cancelled"):
                error = getattr(interaction, "error", None) or f"status={status}"
                raise RuntimeError(f"Gemini Deep Research failed: {error}")

            if status == "requires_action":
                # The agent is blocked waiting for input we have no path to
                # supply from a background job. Fail immediately rather than
                # polling a stalled task until the deadline.
                raise RuntimeError(
                    "The research agent paused and asked for additional input, "
                    "which this app cannot supply mid-run. Try the Fast tier or "
                    f"rerun the request (interaction id: {interaction_id})"
                )

            if status != last_status:
                on_event(f"Status: {status}", interaction_id)
                last_status = status

            progress = _summarize_progress(interaction)
            if progress and progress != last_progress:
                on_event(progress, interaction_id)
                last_progress = progress
                next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_S
            elif time.monotonic() >= next_heartbeat:
                # A background interaction often reports only its status, with
                # no step detail, so a long run would otherwise show a single
                # log line for 20 minutes and read as hung. This states only
                # what we actually know: the agent is still working and we
                # just confirmed it.
                minutes = int((time.monotonic() - started) // 60)
                on_event(
                    f"Still running after {minutes} min (provider reports "
                    f"{status})",
                    interaction_id,
                )
                next_heartbeat = time.monotonic() + HEARTBEAT_INTERVAL_S

            time.sleep(POLL_INTERVAL_S)

        raise TimeoutError(
            f"Research did not complete within {deadline.minutes} minutes. "
            f"It may still finish on Google's side (interaction id: {interaction_id})"
        )
