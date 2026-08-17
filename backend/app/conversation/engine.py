"""Conversation engine: ties provider, state machine and prompt together."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from ..config import get_settings, llm_provider_active
from ..llm.base import Provider, ProviderError
from ..llm.fallback import FallbackProvider
from ..llm.groq import GroqProvider
from .prompt import build_system_prompt
from .state import Classification, ConversationStateMachine

log = logging.getLogger(__name__)


def create_provider() -> Provider:
    """Return the active provider, falling back to offline mode when needed."""
    mode = llm_provider_active()
    if mode == "groq":
        try:
            return GroqProvider()
        except ProviderError as exc:
            log.warning("Groq unavailable (%s); using offline fallback provider", exc)
    return FallbackProvider()


class ConversationEngine:
    """One engine instance == one phone call session."""

    def __init__(self, provider: Provider | None = None) -> None:
        self.session_id = uuid4().hex
        self.created_at: float = time.monotonic()
        self.machine = ConversationStateMachine()
        self.history: list[dict] = []
        self._provider = provider or create_provider()
        self._sticky_fallback: FallbackProvider | None = None
        self._consecutive_failures = 0
        self.system_prompt = build_system_prompt()

    # ------------------------------------------------------------------ public
    async def start(self) -> dict:
        """Produce the agent's greeting (deterministic, always flow-correct)."""
        reply = self._greeting()
        self.history.append({"role": "agent", "text": reply})
        return self._turn(reply, "fallback")

    async def respond(self, user_text: str) -> dict:
        user_text = (user_text or "").strip()
        if not user_text:
            raise ValueError("empty user message")
        self.history.append({"role": "user", "text": user_text})

        classification = await self._classify(user_text)
        self.machine.advance(classification)
        reply, provider = await self._reply(classification)

        self.history.append({"role": "agent", "text": reply})
        return self._turn(reply, provider)

    # ------------------------------------------------------------------ internals
    async def _call(self, with_provider) -> tuple:
        """Run a provider call, counting failures so an unstable Groq session
        locks onto the offline fallback instead of flip-flopping.
        Returns (result, provider_name)."""
        if self._sticky_fallback:
            return await with_provider(self._sticky_fallback), self._sticky_fallback.name
        try:
            result = await with_provider(self._provider)
            self._consecutive_failures = 0
            return result, self._provider.name
        except ProviderError as exc:
            self._consecutive_failures += 1
            log.warning("%s call failed (%s); using offline fallback", self._provider.name, exc)
            if self._consecutive_failures >= 2 and self._provider.name == "groq":
                log.warning("Groq unstable for this session - locking to offline fallback")
                self._sticky_fallback = FallbackProvider()
            fb = self._sticky_fallback or FallbackProvider()
            return await with_provider(fb), fb.name

    async def _classify(self, user_text: str) -> Classification:
        result, _ = await self._call(
            lambda p: p.classify(
                user_text=user_text,
                history=self.history,
                state=self.machine.state,
                system_prompt=self.system_prompt,
            )
        )
        return result

    async def _reply(self, classification: Classification) -> tuple[str, str]:
        snapshot = self.machine.snapshot()
        reply, provider = await self._call(
            lambda p: p.generate_reply(
                snapshot=snapshot,
                classification=classification,
                history=self.history,
                system_prompt=self.system_prompt,
            )
        )
        # make the text read naturally when spoken ("rupees", "square feet",
        # spaced phone digits, spelled RERA number) - no matter what the
        # provider wrote
        from ..speech import normalize_for_speech
        return normalize_for_speech(reply), provider

    def _greeting(self) -> str:
        return _greeting_en()

    def _turn(self, reply: str, provider: str) -> dict:
        snap = self.machine.snapshot()
        return {
            "session_id": self.session_id,
            "reply": reply,
            "reply_language": "hi" if self.machine.lead.language != "en" else "en",
            "state": snap["state"],
            "expected_question": snap["expected_question"],
            "closed": snap["closed"],
            "closed_reason": snap["closed_reason"],
            "qualified": self.machine.lead.qualified,
            "lead": self.machine.lead.summary(),
            "provider": provider,
            "turn": len(self.history) // 2,
        }


_GREETING_EN = (
    "Good evening! This is {agent} from Divyasree Developers, calling about "
    "Whispers of the Wind - premium villa plots near Nandi Hills, North Bengaluru. "
    "May I take two minutes of your time?"
)


def _greeting_en() -> str:
    return _GREETING_EN.format(agent=get_settings().agent_name)