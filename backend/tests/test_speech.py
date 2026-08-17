"""Tests for the speech layer (TTS synth + STT) with mocked engines.

Real network calls are avoided: edge-tts and gTTS are monkeypatched, and the
Groq transcription path is asserted to require an API key.

Note: coroutines run on a worker thread (see test_fallback.py) because
pytest-playwright keeps an event loop in the main thread.
"""

import asyncio
import threading

import pytest

from app.llm.base import ProviderError
from app.speech import synthesize, transcribe


def _run(coro):
    box = {}

    def _worker():
        try:
            box["value"] = asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001 - re-raised in the main thread
            box["error"] = exc

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def test_transcribe_requires_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(ProviderError):
        _run(transcribe(b"fake audio bytes"))


# ------------------------------------------------------------------ normalization
def test_normalize_money_words():
    from app.speech import normalize_for_speech
    assert normalize_for_speech("Rs 92.4 lakh") == "rupees 92.4 lakh"
    assert normalize_for_speech("starts at Rs. 92.4 lakh") == "starts at rupees 92.4 lakh"
    assert normalize_for_speech("₹3.08 crore") == "rupees 3.08 crore"
    assert normalize_for_speech("Rs 92.4 lakh ki starting price") == "rupees 92.4 lakh ki starting price"


def test_normalize_area_words():
    from app.speech import normalize_for_speech
    assert normalize_for_speech("a 20,000 sq.ft. clubhouse") == "a 20,000 square feet clubhouse"
    assert normalize_for_speech("1,200 sq ft plot") == "1,200 square feet plot"
    assert normalize_for_speech("sqft") == "square feet"


def test_normalize_phone_digits_spoken_individually():
    from app.speech import normalize_for_speech
    assert normalize_for_speech("call me at 98450 12345") == "call me at 9 8 4 5 0 1 2 3 4 5"
    assert normalize_for_speech("number 9988776655") == "number 9 9 8 8 7 7 6 6 5 5"
    assert normalize_for_speech("reach me at +91 98765 43210") == \
        "reach me at plus nine one 9 8 7 6 5 4 3 2 1 0"
    # years and prices stay untouched
    assert normalize_for_speech("2029 is fine") == "2029 is fine"
    assert normalize_for_speech("around 1.5 crore") == "around 1.5 crore"
    assert normalize_for_speech("92.4 lakh") == "92.4 lakh"
    assert normalize_for_speech("1,200 square feet") == "1,200 square feet"


def test_normalize_rera_and_24x7():
    from app.speech import normalize_for_speech
    text = "registered PRM/KA/RERA/1250/301/PR/070525/007718"
    assert normalize_for_speech(text) == \
        "registered P R M K A R E R A 1 2 5 0 3 0 1 P R 0 7 0 5 2 5 0 0 7 7 1 8"
    assert normalize_for_speech("gated 24x7 security") == "gated twenty-four seven security"


def test_normalized_replies_reach_ui_and_history():
    """Engine replies are normalized before they are returned (so the UI shows
    the spoken form and TTS never sees "Rs")."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        await e.respond("Yes, please go ahead")
        await e.respond("For my own weekend home")
        budget_turn = await e.respond("Yes, comfortable with the corridor")
        return budget_turn, e

    budget_turn, engine = _run(run())
    assert "rupees 92.4 lakh" in budget_turn["reply"]
    assert "Rs" not in budget_turn["reply"]
    assert engine.history[-1]["text"] == budget_turn["reply"]


def test_synthesize_edge_primary(monkeypatch, tmp_path):
    async def fake_stream(self):
        yield {"type": "audio", "data": b"MP3DATA" * 100}
        yield {"type": "end", "data": b""}

    import edge_tts
    monkeypatch.setattr(edge_tts.Communicate, "stream", fake_stream)
    from app import speech as speech_mod
    monkeypatch.setattr(speech_mod, "_CACHE_DIR", tmp_path)

    data, engine = _run(synthesize("Hello there", "en"))
    assert engine == "edge-tts"
    assert data == b"MP3DATA" * 100
    # second call hits the disk cache
    data2, _ = _run(synthesize("Hello there", "en"))
    assert data2 == data


def test_synthesize_gtts_fallback(monkeypatch, tmp_path):
    def failing_stream(self):
        raise ProviderError("no ws")

    import edge_tts
    monkeypatch.setattr(edge_tts.Communicate, "stream", failing_stream)
    from app import speech as speech_mod

    class FakeTTS:
        def __init__(self, *a, **k):
            pass

        def write_to_fp(self, buf):
            buf.write(b"GTTSDATA" * 50)

    monkeypatch.setattr(speech_mod, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr("gtts.gTTS", FakeTTS)

    data, engine = _run(synthesize("Namaste", "hi"))
    assert engine == "gtts"
    assert b"GTTSDATA" in data
    # cached entry must remember its engine (regression: it used to lie and
    # say "edge-tts", so demos served robotic cached gTTS audio)
    data2, engine2 = _run(synthesize("Namaste", "hi"))
    assert data2 == data
    assert engine2 == "gtts"