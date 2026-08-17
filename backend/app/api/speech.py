"""Speech endpoints: TTS playback (mp3) and Whisper STT (multipart upload)."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from ..llm.base import ProviderError
from ..speech import synthesize, transcribe

router = APIRouter(prefix="/api/v1")


@router.get("/speak")
async def speak(text: str, lang: str = "en") -> Response:
    """Synthesize text to speech (mp3). TTS engine reported in X-TTS-Engine."""
    if not text.strip() or len(text) > 2000:
        return Response(status_code=422, content="text must be 1-2000 characters")
    data, engine = await synthesize(text, lang)
    return Response(
        content=data,
        media_type="audio/mpeg",
        headers={"X-TTS-Engine": engine, "Cache-Control": "public, max-age=86400"},
    )


@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)) -> dict:
    """Transcribe caller audio with Groq Whisper (free tier)."""
    try:
        data = await file.read()
        if not data:
            return {"text": ""}
        text = await transcribe(data, filename=file.filename or "caller.webm")
    except ProviderError as exc:
        return {"text": "", "error": str(exc)}
    return {"text": text}
