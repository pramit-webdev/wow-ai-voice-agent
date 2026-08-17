"""Groq LLM provider (free tier, OpenAI-compatible API).

Uses httpx directly so the demo has no extra SDK dependencies. Falls back to
`fallback.Provider` at the engine level if anything fails, so the app keeps
working without a key or when Groq is unreachable.

Free-tier rate limits (429) are handled with retry + backoff so the demo
does not degrade mid-call on a burst.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from ..config import get_settings
from ..conversation.state import Classification
from .base import Provider, ProviderError

log = logging.getLogger(__name__)

JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

MAX_RETRIES = 2


def extract_json(text: str) -> dict | None:
    """Best-effort JSON extraction from an LLM response."""
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    fenced = JSON_FENCE_RE.search(text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class GroqProvider(Provider):
    name = "groq"

    def __init__(self) -> None:
        self._settings = get_settings()
        if not self._settings.groq_api_key:
            raise ProviderError("GROQ_API_KEY not configured")

    async def _chat(self, messages: list[dict], *, temperature: float | None = None) -> str:
        settings = self._settings
        payload = {
            "model": settings.groq_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": 700,
        }
        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
                    resp = await client.post(settings.groq_base_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                if resp.status_code == 429 or resp.status_code >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (1.0 * (attempt + 1))
                    log.warning(
                        "Groq HTTP %s (attempt %d/%d); retrying in %.1fs",
                        resp.status_code, attempt + 1, MAX_RETRIES + 1, wait,
                    )
                    await asyncio.sleep(min(wait, 5.0))
                    continue
                raise ProviderError(f"Groq API error: HTTP {resp.status_code} {resp.text[:200]}")
            except httpx.HTTPError as exc:  # network / timeout
                last_exc = exc
                log.warning("Groq network error (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, exc)
                await asyncio.sleep(1.0 * (attempt + 1))
        raise ProviderError(f"Groq request failed after {MAX_RETRIES + 1} attempts: {last_exc}")

    async def classify(
        self,
        *,
        user_text: str,
        history: list[dict],
        state: str,
        system_prompt: str,
    ) -> Classification:
        transcript = _transcript_messages(history)
        messages = [
            {"role": "system", "content": system_prompt},
            *transcript,
            {
                "role": "user",
                "content": (
                    f"Caller's latest message: \"{user_text}\"\n"
                    f"Current flow state: {state}\n"
                    "Return the JSON for THIS message only."
                ),
            },
        ]
        raw = await self._chat(messages, temperature=0.2)
        payload = extract_json(raw)
        if payload is None:
            raise ProviderError("Groq returned non-JSON classification")
        return classification_from_payload(payload)

    async def generate_reply(
        self,
        *,
        snapshot: dict,
        classification: Classification,
        history: list[dict],
        system_prompt: str,
    ) -> str:
        transcript = _transcript_messages(history)
        state = snapshot["state"]
        messages = [
            {"role": "system", "content": system_prompt},
            *transcript,
            {
                "role": "user",
                "content": _reply_task(snapshot, classification),
            },
        ]
        raw = await self._chat(messages)
        text = raw.strip()
        if not text:
            raise ProviderError("Groq returned an empty reply")
        return text


def _transcript_messages(history: list[dict]) -> list[dict]:
    out: list[dict] = []
    for turn in history[-12:]:
        role = "assistant" if turn["role"] == "agent" else "user"
        out.append({"role": role, "content": turn["text"]})
    return out


def _reply_task(snapshot: dict, c: Classification) -> str:
    state = snapshot["state"]
    closed = snapshot.get("closed")
    closed_reason = snapshot.get("closed_reason")
    expected_question = snapshot.get("expected_question")
    needs_reask = snapshot.get("needs_reask", False)
    lead = snapshot.get("lead", {})

    flow = f"Current flow state: {state}"
    if state == "greeting":
        flow += (
            " - you introduced the project and asked permission to speak. "
            "If the caller asked a question, answer it briefly from the knowledge base, "
            "then re-ask permission."
        )
    elif state == "intent":
        flow += (
            " - ask the intent checkpoint question. If already answered earlier, "
            "acknowledge and move to the geography checkpoint question."
        )
    elif state == "geography":
        flow += (
            " - ask the geography checkpoint. "
            + ("The caller already declined once; explain the corridor benefits once more and re-ask gently."
               if needs_reask else "")
        )
    elif state == "budget":
        flow += (
            " - ask the budget checkpoint. "
            + ("The caller already said the budget does not fit; mention the 1,200 sq.ft. starting "
               "size at Rs 92.4 lakh once more and re-ask gently."
               if needs_reask else "")
        )
    elif state == "timeline":
        flow += (
            " - ask the timeline checkpoint. If the caller is concerned about Dec 2029, "
            "acknowledge and explain phased delivery, then proceed to the pitch."
        )
    elif state == "pitch":
        flow += " - deliver the aspirational Private Valley pitch in 3-4 sentences, end by inviting a follow-up call."
    elif state == "cta":
        flow += " - ask for a follow-up call with a Property Expert; capture name, phone and preferred time and confirm them."
    elif state == "done":
        flow += " - thank the caller warmly and end the call."
    if closed:
        flow += (
            f" The conversation has ended ({closed_reason}): deliver a polite, brief, "
            "apologetic closing line. Do NOT ask further questions."
        )

    extras = []
    answered_now = snapshot.get("answered_now") or []
    if answered_now:
        extras.append(
            "This turn the caller newly answered: "
            + ", ".join(answered_now)
            + ". Acknowledge each new answer briefly before continuing."
        )
    if c.question_topic:
        extras.append(f"The caller asked about: {c.question_topic} - answer briefly from the knowledge base.")
    if c.contact_name:
        extras.append(f"The caller gave their name: {c.contact_name}.")
    if c.contact_phone:
        extras.append(f"The caller gave their phone: {c.contact_phone}.")
    if lead.get("qualified"):
        extras.append("The caller is fully qualified - be warm and inviting toward the follow-up.")

    return (
        "Task: write ONLY the agent's spoken reply for the NEXT turn (2-3 sentences, "
        "one question max, spoken-language style, no JSON, no labels).\n"
        f"{flow}\n"
        + ("\n".join(f"- {e}" for e in extras) + "\n" if extras else "")
    )


def classification_from_payload(payload: dict) -> Classification:
    """Map a Groq classification JSON payload onto the dataclass."""
    cls = payload.get("classification", payload)
    allowed_bool = ("permission_granted", "geography_comfortable", "budget_fit", "timeline_ok")

    def _b(key: str) -> bool | None:
        val = cls.get(key)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            v = val.strip().lower()
            if v in ("true", "yes", "1"):
                return True
            if v in ("false", "no", "0"):
                return False
        return None

    intent_raw = (cls.get("intent") or "").strip().lower()
    intent = None
    if intent_raw in ("self_use", "self-use", "self"):
        intent = "self_use"
    elif intent_raw in ("investment", "invest"):
        intent = "investment"
    elif intent_raw in ("both", "hybrid"):
        intent = "both"

    lang = (cls.get("language") or "en").strip().lower()
    if lang not in ("en", "hi", "hinglish"):
        lang = "en"

    return Classification(
        language=lang,
        permission_granted=_b("permission_granted"),
        intent=intent,
        geography_comfortable=_b("geography_comfortable"),
        budget_fit=_b("budget_fit"),
        timeline_ok=_b("timeline_ok"),
        stop_requested=_b("stop_requested") is True,
        irritated=_b("irritated") is True,
        question_topic=(cls.get("question_topic") or None),
        contact_name=(cls.get("contact_name") or None),
        contact_phone=(cls.get("contact_phone") or None),
        preferred_time=(cls.get("preferred_time") or None),
    )