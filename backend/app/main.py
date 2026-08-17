"""FastAPI application for the WOW AI Voice Agent."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import conversation, docs, speech
from .config import llm_provider_active, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("wow")

app = FastAPI(
    title="Whispers of the Wind - AI Voice Agent",
    description="Outbound AI voice agent for qualifying leads at Divyasree's WOW project.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversation.router)
app.include_router(docs.router)
app.include_router(speech.router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "provider": llm_provider_active(),
        "model": get_settings().groq_model,
        "capabilities": {
            "stt": "whisper" if get_settings().groq_api_key else None,
            "tts": "edge-tts",
        },
    }

_static = Path(__file__).resolve().parent / "static"
if _static.exists():
    app.mount("/", StaticFiles(directory=_static, html=True), name="static")


@app.on_event("startup")
async def _startup_log() -> None:
    log.info(
        "WOW voice agent started. LLM provider active: %s (set GROQ_API_KEY in .env to enable)",
        llm_provider_active(),
    )