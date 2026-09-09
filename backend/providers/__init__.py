"""Deep research provider registry."""

from .base import ProviderInfo, ResearchProvider
from .gemini import GeminiProvider
from .openai_dr import OpenAIProvider
from .claude import ClaudeProvider

PROVIDERS: dict[str, ResearchProvider] = {
    p.id: p for p in (GeminiProvider(), OpenAIProvider(), ClaudeProvider())
}


def get_provider(provider_id: str) -> ResearchProvider:
    if provider_id not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider_id}")
    return PROVIDERS[provider_id]


def list_providers() -> list[ProviderInfo]:
    return [p.info() for p in PROVIDERS.values()]
