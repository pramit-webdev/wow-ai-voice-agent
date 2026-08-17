"""Provider abstraction for the conversation engine."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..conversation.state import Classification


class ProviderError(RuntimeError):
    """Raised when an LLM provider fails; callers may fall back gracefully."""


class Provider(ABC):
    """Minimal interface: understand a caller message, and speak a reply."""

    name: str = "abstract"

    @abstractmethod
    async def classify(
        self,
        *,
        user_text: str,
        history: list[dict],
        state: str,
        system_prompt: str,
    ) -> Classification:
        """Return a structured Classification of the caller's latest message."""

    @abstractmethod
    async def generate_reply(
        self,
        *,
        snapshot: dict,
        classification: Classification,
        history: list[dict],
        system_prompt: str,
    ) -> str:
        """Return the agent's spoken reply for the current state."""
