"""Speech AI: server-side TTS (edge-tts neural, gTTS fallback) and STT
(Groq Whisper free tier).

Both engines are free:
  - TTS: Microsoft Edge neural voices (e.g. en-IN-SwaraNeural, female) via
    edge-tts; falls back to Google gTTS when Microsoft is unreachable.
  - STT: whisper-large-v3 via the Groq free tier (requires GROQ_API_KEY);
    the frontend falls back to the browser's Web Speech API otherwise.
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
import time
from pathlib import Path

import httpx

from ..config import get_settings
from ..llm.base import ProviderError

log = logging.getLogger(__name__)

_GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_CACHE_DIR = Path(tempfile.gettempdir()) / "wow_tts_cache"

# --------------------------------------------------------------------- text->speech
_RERA_NUMBER_RE = re.compile(r"\b[A-Z]{2,3}/KA/RERA/\d+/\d+/[A-Z]{2}/\d+/\d+\b")
_DIGIT_RUN_RE = re.compile(r"(?<!\d)(\d{5,})(?!\d)")


def normalize_for_speech(text: str) -> str:
    """Convert reply text into what it should SOUND like when spoken by TTS.

    Fixes the classic TTS mis-reads:
      - "Rs"/"Rs."/"₹"  -> "rupees"   (never "R-S")
      - "sq.ft."/sq ft  -> "square feet"
      - "24x7"/"24/7"   -> "twenty-four seven"
      - RERA numbers    -> spaced letters/digits ("P R M K A R E R A 1 2 5 0 ...")
      - long digit runs -> spaced digits, so phone numbers are read as
        "nine eight seven..." instead of "ninety-eight thousand seven hundred..."
      - "+91"           -> "plus nine one"
    Short digit groups (years "2029", prices "92.4", "3.08") are untouched.
    """
    t = _RERA_NUMBER_RE.sub(
        lambda m: " ".join(m.group(0).replace("/", "")), text)
    t = re.sub(r"\bRs\b\.?", "rupees", t, flags=re.IGNORECASE)
    t = re.sub(r"₹\s?", "rupees ", t)
    t = re.sub(r"\bsq\.?\s?ft\b\.?", "square feet", t, flags=re.IGNORECASE)
    t = t.replace("24x7", "twenty-four seven").replace("24/7", "twenty-four seven")
    t = t.replace("+91", "plus nine one")
    t = _DIGIT_RUN_RE.sub(lambda m: " ".join(m.group(1)), t)
    return t


def _tts_voice(lang: str) -> str:
    s = get_settings()
    return s.tts_voice_hi if lang == "hi" else s.tts_voice_en


def _cache_path(text: str, lang: str, voice: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{lang}|{voice}|{text}".encode()).hexdigest()
    return _CACHE_DIR / f"{key}.mp3"


def _cached_or_none(path: Path) -> tuple[bytes, str] | None:
    """Cached mp3 + the engine that produced it (sidecar file).
    Entries without a sidecar predate the fix: treat as gtts (conservative -
    callers fall back to a neural voice instead of trusting the label)."""
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < get_settings().tts_cache_seconds:
            engine = "gtts"
            sidecar = path.with_suffix(".engine")
            if sidecar.exists():
                engine = sidecar.read_text().strip()
            return path.read_bytes(), engine
        path.unlink()
    return None


async def _synthesize_edge(text: str, voice: str) -> bytes:
    import edge_tts

    chunks: list[bytes] = []
    async for chunk in edge_tts.Communicate(text, voice).stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    if not chunks:
        raise ProviderError("edge-tts returned no audio")
    return b"".join(chunks)


async def _synthesize_gtts(text: str, lang: str) -> bytes:
    from gtts import gTTS

    tts = gTTS(text=text, lang=lang, tld="co.in" if lang == "en" else None)
    import io

    buf = io.BytesIO()
    tts.write_to_fp(buf)
    return buf.getvalue()


async def synthesize(text: str, lang: str = "en") -> tuple[bytes, str]:
    """Return (mp3 bytes, engine_used). engine: 'edge-tts' or 'gtts'."""
    lang = "hi" if lang == "hi" else "en"
    voice = _tts_voice(lang)
    path = _cache_path(text, lang, voice)
    cached = _cached_or_none(path)
    if cached:
        return cached
    try:
        data = await _synthesize_edge(text, voice)
        engine = "edge-tts"
    except Exception as exc:
        log.warning("edge-tts failed (%s); falling back to gTTS", exc)
        data = await _synthesize_gtts(text, lang)
        engine = "gtts"
    if len(data) < 100:  # silence/empty guard
        raise ProviderError("TTS produced no usable audio")
    path.write_bytes(data)
    path.with_suffix(".engine").write_text(engine)
    return data, engine


async def transcribe(audio_bytes: bytes, filename: str = "caller.webm") -> str:
    """Transcribe spoken audio with Groq Whisper (free tier)."""
    settings = get_settings()
    if not settings.groq_api_key:
        raise ProviderError("Groq API key not configured (STT unavailable)")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            files={"file": (filename, audio_bytes, "audio/webm")},
            data={"model": settings.whisper_model},
        )
    if resp.status_code != 200:
        raise ProviderError(f"Groq STT failed: HTTP {resp.status_code}")
    text = resp.json().get("text", "").strip()
    if not text:
        raise ProviderError("Groq STT returned empty text")
    return text
