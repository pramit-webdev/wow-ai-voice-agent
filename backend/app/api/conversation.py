"""Conversation REST API + in-memory session store."""

from __future__ import annotations

import time
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..conversation.engine import ConversationEngine
from ..conversation.project import PROJECT, FAQ

router = APIRouter(prefix="/api/v1")

# In-memory session store (one engine per phone call). Fine for a demo; swap for
# Redis/Postgres when scaling.
_sessions: dict[str, ConversationEngine] = {}
_sessions_lock = Lock()
SESSION_TTL_SECONDS = 1800  # 30 minutes


class RespondRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _prune_sessions() -> None:
    now = time.monotonic()
    stale = [sid for sid, e in _sessions.items() if e.created_at + SESSION_TTL_SECONDS < now]
    for sid in stale:
        _sessions.pop(sid, None)


@router.get("/health")
def health() -> dict:
    _prune_sessions()
    return {"status": "ok", "active_sessions": len(_sessions)}


@router.get("/project")
def project_info() -> dict:
    return {
        "name": PROJECT["name"],
        "developer": PROJECT["developer"],
        "location": PROJECT["location"],
        "starting_price": PROJECT["starting_price"],
        "price_range": PROJECT["price_range"],
        "possession": PROJECT["possession"],
        "rera": PROJECT["rera"],
        "usp": PROJECT["usp"],
        "connectivity": PROJECT["connectivity"],
        "faq": FAQ,
    }


@router.post("/conversation/start")
async def start_conversation() -> dict:
    _prune_sessions()
    engine = ConversationEngine()
    with _sessions_lock:
        _sessions[engine.session_id] = engine
    return await engine.start()


@router.post("/conversation/{session_id}/respond")
async def respond(session_id: str, body: RespondRequest) -> dict:
    engine = _sessions.get(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="session not found or expired")
    return await engine.respond(body.message)


@router.get("/conversation/{session_id}")
def get_session(session_id: str) -> dict:
    engine = _sessions.get(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="session not found or expired")
    return {
        "session_id": engine.session_id,
        "history": engine.history,
        "snapshot": engine.machine.snapshot(),
    }
