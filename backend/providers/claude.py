"""Claude research agent via the Messages API + native web search tool.

Anthropic does not expose a dedicated "deep research" API. The closest
equivalent is a Claude model with the built-in web search tool, which runs
multiple progressive searches and cites sources. This is labeled honestly in
the UI as "Claude Research (web search agent)".
"""

import os
from typing import Any

from ._polling import POLL_REQUEST_TIMEOUT_S
from .base import EventCallback, ModelOption, ResearchProvider

MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "32000"))
MAX_SEARCHES = 25
# Newest web search tool version first; fall back if the API rejects it.
WEB_SEARCH_VERSIONS = ("web_search_20260209", "web_search_20250305")
# Agentic search turns can pause; cap continuation rounds defensively.
MAX_PAUSE_CONTINUATIONS = 12

# A long search run is billed for the whole conversation prefix on every
# continuation round. Caching that prefix makes the repeated portion far
# cheaper without changing what the model sees.
_CACHE_CONTROL = {"type": "ephemeral"}


class ClaudeProvider(ResearchProvider):
    id = "claude"
    label = "Claude Research"
    description = (
        "Claude with the native web search tool (no dedicated deep-research "
        "API exists; this is an agentic web-search research run)."
    )
    env_key = "ANTHROPIC_API_KEY"

    def models(self) -> list[ModelOption]:
        return [
            ModelOption(
                id="claude-sonnet-5",
                label="Claude Sonnet 5 (Fast)",
                tier="fast",
                note="Web-search research agent. Faster and cheaper.",
            ),
            ModelOption(
                id="claude-opus-5",
                label="Claude Opus 5",
                tier="max",
                note="Web-search research agent. Most capable.",
            ),
        ]

    def _stream_once(self, client, model_id: str, tool: dict, messages: list):
        with client.messages.stream(
            model=model_id,
            max_tokens=MAX_TOKENS,
            tools=[tool],
            messages=messages,
        ) as stream:
            for _ in stream:
                pass
            return stream.get_final_message()

    @staticmethod
    def _assistant_turn(message: Any, *, cached: bool) -> dict[str, Any]:
        """Serialize an assistant turn for resending, optionally cache-marked."""
        blocks = [
            b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else dict(b)
            for b in message.content
        ]
        if cached and blocks:
            blocks[-1] = {**blocks[-1], "cache_control": _CACHE_CONTROL}
        return {"role": "assistant", "content": blocks}

    @staticmethod
    def _text_blocks(message: Any) -> str:
        return "".join(
            block.text
            for block in message.content
            if getattr(block, "type", "") == "text"
        )

    @staticmethod
    def _count_searches(message: Any) -> int:
        return sum(
            1
            for block in message.content
            if getattr(block, "type", "") == "server_tool_use"
        )

    def run(self, prompt: str, model_id: str, on_event: EventCallback) -> str:
        import anthropic

        client = anthropic.Anthropic(timeout=POLL_REQUEST_TIMEOUT_S)
        on_event(f"Starting Claude research run ({model_id})", None)

        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        message = None
        tool = None
        last_error = None
        for version in WEB_SEARCH_VERSIONS:
            tool = {"type": version, "name": "web_search", "max_uses": MAX_SEARCHES}
            try:
                message = self._stream_once(client, model_id, tool, messages)
                break
            except anthropic.BadRequestError as exc:
                last_error = exc
                if "web_search" not in str(exc):
                    raise
        if message is None or tool is None:
            raise RuntimeError(f"Claude web search tool unavailable: {last_error}")

        # Text can arrive across several rounds. Accumulate it: keeping only
        # the final round's text silently truncates the report.
        transcript = [self._text_blocks(message)]
        searches = self._count_searches(message)

        rounds = 0
        while message.stop_reason == "pause_turn" and rounds < MAX_PAUSE_CONTINUATIONS:
            rounds += 1
            on_event(
                f"Continuing research (round {rounds + 1}, {searches} searches so far)",
                None,
            )
            try:
                next_messages = messages + [
                    self._assistant_turn(message, cached=True)
                ]
                message = self._stream_once(client, model_id, tool, next_messages)
            except anthropic.BadRequestError as exc:
                if "cache_control" not in str(exc):
                    raise
                # This model or tool version will not accept a cache breakpoint
                # here; continue uncached rather than losing the run.
                next_messages = messages + [
                    self._assistant_turn(message, cached=False)
                ]
                message = self._stream_once(client, model_id, tool, next_messages)
            messages = next_messages
            transcript.append(self._text_blocks(message))
            searches += self._count_searches(message)

        if message.stop_reason == "pause_turn":
            on_event(
                f"Stopped after {MAX_PAUSE_CONTINUATIONS} continuation rounds; "
                "returning the report as written so far",
                None,
            )

        if searches:
            on_event(f"Performed {searches} web searches", None)

        text = "".join(transcript)
        if not text.strip():
            raise RuntimeError(
                f"Claude returned no text (stop_reason={message.stop_reason})"
            )
        on_event("Research completed", None)
        return text
