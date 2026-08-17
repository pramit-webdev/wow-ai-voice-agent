"""API-level tests: full conversations over the FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _start(client) -> str:
    turn = client.post("/api/v1/conversation/start").json()
    assert turn["state"] == "greeting"
    assert "Divyasree" in turn["reply"]
    assert "may i take two minutes" in turn["reply"].lower() or "permission" in turn["reply"].lower()
    return turn["session_id"]


def _say(client, sid, msg):
    resp = client.post(f"/api/v1/conversation/{sid}/respond", json={"message": msg})
    assert resp.status_code == 200
    return resp.json()


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_unknown_session_404(client):
    assert client.post("/api/v1/conversation/abc/respond", json={"message": "hi"}).status_code == 404
    assert client.get("/api/v1/conversation/abc").status_code == 404


def test_empty_message_rejected(client):
    sid = _start(client)
    assert client.post(f"/api/v1/conversation/{sid}/respond", json={"message": ""}).status_code == 422


def test_full_qualified_journey(client):
    sid = _start(client)
    _say(client, sid, "Yes, please go ahead")
    t = _say(client, sid, "For my own weekend home")
    assert t["state"] == "geography"
    _say(client, sid, "Yes, comfortable with the corridor")
    t = _say(client, sid, "Budget is around 2 crore")
    assert t["state"] == "timeline"
    t = _say(client, sid, "2029 works for me")
    assert t["state"] == "pitch"
    assert t["qualified"] is True
    t = _say(client, sid, "Sounds lovely")
    assert t["state"] == "cta"
    t = _say(client, sid, "My name is Rahul, 9876543210, evening is fine")
    assert t["state"] == "done"
    assert t["lead"]["name"] == "Rahul"
    assert t["lead"]["phone"] == "9876543210"
    assert t["lead"]["qualified"] is True

    session = client.get(f"/api/v1/conversation/{sid}").json()
    assert session["snapshot"]["state"] == "done"
    assert len(session["history"]) >= 8


def test_budget_mismatch_closes(client):
    sid = _start(client)
    _say(client, sid, "Go ahead")
    _say(client, sid, "Investment")
    _say(client, sid, "Yes fine")
    t = _say(client, sid, "Too expensive for me")
    assert t["state"] == "budget"
    assert t["closed"] is False
    t = _say(client, sid, "I can't afford more than 70 lakh")
    assert t["closed"] is True
    assert t["closed_reason"] == "budget_mismatch"
    assert t["lead"]["qualified"] is False


def test_hindi_journey(client):
    sid = _start(client)
    t = _say(client, sid, "Ji, bol sakte hain")
    assert t["state"] == "intent"
    _say(client, sid, "Apne ghar ke liye")
    _say(client, sid, "Haan, theek hai")
    t = _say(client, sid, "Haan, budget theek hai")
    assert t["state"] == "timeline"
    t = _say(client, sid, "2029 theek hai")
    assert t["state"] == "pitch"
    assert t["lead"]["language"] in ("hi", "hinglish")


def test_pitch_question_answered_then_flow_continues(client):
    sid = _start(client)
    _say(client, sid, "Yes, please go ahead")
    _say(client, sid, "For my own weekend home")
    _say(client, sid, "Yes, comfortable with the corridor")
    _say(client, sid, "Budget is around 2 crore")
    t = _say(client, sid, "2029 works for me")
    assert t["state"] == "pitch"
    t = _say(client, sid, "That sounds nice. What would the returns be like if I don't build immediately, and is the price negotiable?")
    assert t["state"] == "pitch", "question must not advance past the pitch"
    assert "92.4" in t["reply"] or "lakh" in t["reply"].lower(), "question must be answered from the KB"
    t = _say(client, sid, "Sounds good, go ahead")
    assert t["state"] == "cta"
    t = _say(client, sid, "My name is Sanjay, 9811122334, evening is fine")
    assert t["state"] == "done"
    assert t["lead"]["name"] == "Sanjay"
    assert t["lead"]["phone"] == "9811122334"
    assert t["lead"]["qualified"] is True


def test_system_prompt_pdf(client):
    resp = client.get("/api/v1/system-prompt.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_project_endpoint(client):
    data = client.get("/api/v1/project").json()
    assert data["name"] == "Whispers of the Wind (WOW)"
    assert "92.4 lakh" in data["starting_price"]
    assert data["rera"].startswith("PRM/KA/RERA")


def test_health_reports_speech_capabilities(client):
    h = client.get("/health").json()
    assert "capabilities" in h
    assert h["capabilities"]["tts"] == "edge-tts"
    assert h["capabilities"]["stt"] in ("whisper", None)


def test_speak_endpoint(client, monkeypatch):
    from app.api import speech as speech_api

    async def fake_synth(text, lang):
        return b"ID3fakeaudio" * 30, "edge-tts"

    monkeypatch.setattr(speech_api, "synthesize", fake_synth)
    resp = client.get("/api/v1/speak", params={"text": "Hello there", "lang": "en"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.headers["x-tts-engine"] == "edge-tts"
    assert b"ID3fakeaudio" in resp.content


def test_speak_rejects_too_long(client):
    assert client.get("/api/v1/speak", params={"text": "x" * 2001}).status_code == 422
    assert client.get("/api/v1/speak", params={"text": " "}).status_code == 422


def test_transcribe_without_key_returns_empty(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    resp = client.post(
        "/api/v1/transcribe",
        files={"file": ("caller.webm", b"fake-audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == ""
    assert "error" in resp.json()