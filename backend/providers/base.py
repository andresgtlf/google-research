"""Common interface for deep research providers.

Each provider exposes blocking `run(prompt, model_id, on_event)` that performs
the full research (starting the remote task and polling until completion) and
returns the final markdown report. `on_event` receives REAL status updates
only — no fabricated progress messages.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

# on_event(message, remote_id) — remote_id is passed once known so the job
# manager can persist it (useful to recover results manually if needed).
EventCallback = Callable[[str, Optional[str]], None]


@dataclass
class ModelOption:
    id: str
    label: str
    tier: str  # "fast" | "max" | "legacy"
    note: str = ""


@dataclass
class ProviderInfo:
    id: str
    label: str
    description: str
    env_key: str
    available: bool
    models: list[ModelOption] = field(default_factory=list)


class ResearchProvider(ABC):
    id: str
    label: str
    description: str
    env_key: str

    def available(self) -> bool:
        return bool(os.environ.get(self.env_key))

    @abstractmethod
    def models(self) -> list[ModelOption]: ...

    @abstractmethod
    def run(self, prompt: str, model_id: str, on_event: EventCallback) -> str:
        """Run research to completion; return final markdown. Raises on failure."""

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            id=self.id,
            label=self.label,
            description=self.description,
            env_key=self.env_key,
            available=self.available(),
            models=self.models(),
        )

    def default_model(self, tier: str = "fast") -> str:
        for m in self.models():
            if m.tier == tier:
                return m.id
        return self.models()[0].id
