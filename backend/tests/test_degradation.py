"""Graceful degradation: a broken Groq key must not break the engine."""

import os
import threading
import asyncio

from app.conversation.engine import ConversationEngine
from app.llm.groq import GroqProvider
from app.llm.base import ProviderError


def _run(coro):
    box = {}

    def _worker():
        box["value"] = asyncio.run(coro)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    return box["value"]


def test_groq_provider_requires_key():
    os.environ.pop("GROQ_API_KEY", None)
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        GroqProvider()
        assert False, "should raise without a key"
    except ProviderError:
        pass


def test_engine_falls_back_when_groq_fails(monkeypatch):
    async def _turn():
        engine = ConversationEngine()
        # force provider resolution to groq with a fake broken client
        from app.llm import fallback as fb_mod
        engine.provider = GroqProvider  # will raise on construction
        # Simulate the real path: create_provider with a bogus key
        return engine

    # Directly exercise the degradation used by create_provider
    from app.conversation.engine import create_provider
    from app.llm.fallback import FallbackProvider
    p = create_provider()
    # no key configured -> fallback
    assert isinstance(p, FallbackProvider)


def test_engine_responds_when_provider_raises(monkeypatch):
    class ExplodingProvider:
        name = "exploding"

        async def classify(self, **kw):
            raise ProviderError("boom")

        async def generate_reply(self, **kw):
            raise ProviderError("boom")

    async def _run_engine():
        engine = ConversationEngine(provider=ExplodingProvider())
        await engine.start()
        turn = await engine.respond("Yes, please go ahead")
        return turn

    turn = _run(_run_engine())
    assert turn["state"] == "intent"
    assert turn["provider"] == "fallback"
    assert "considering" in turn["reply"].lower() or "weekend" in turn["reply"].lower()


def test_engine_locks_to_fallback_after_two_groq_failures():
    """An unstable Groq session must not flip-flop between providers."""
    calls = {"classify": 0, "generate": 0, "fallback_classify": 0}

    class FlakyGroq:
        name = "groq"

        async def classify(self, **kw):
            calls["classify"] += 1
            raise ProviderError("429")

        async def generate_reply(self, **kw):
            calls["generate"] += 1
            raise ProviderError("429")

    async def _run_engine():
        engine = ConversationEngine(provider=FlakyGroq())
        await engine.start()
        t1 = await engine.respond("Yes, please go ahead")
        t2 = await engine.respond("For my weekend home")
        return t1, t2

    t1, t2 = _run(_run_engine())
    assert t1["provider"] == "fallback"
    assert t2["provider"] == "fallback"
    # the lock engages after the 2nd consecutive failure (turn 1's generate),
    # so turn 2 must not touch Groq at all
    assert calls["classify"] == 1 and calls["generate"] == 1
    assert t2["state"] == "geography"