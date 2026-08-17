"""Unit tests for the offline fallback NLU.

Note: these run coroutines on a worker thread because pytest-playwright keeps
an event loop running in the main thread when E2E tests share the session.
"""

import asyncio
import threading

from app.llm.fallback import FallbackProvider


async def _classify(fb: FallbackProvider, text: str, state: str):
    return await fb.classify(user_text=text, history=[], state=state, system_prompt="")


def _run(coro):
    box = {}

    def _worker():
        box["value"] = asyncio.run(coro)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()
    return box["value"]


def test_greeting_permission_granted():
    fb = FallbackProvider()
    c = _run(_classify(fb, "Yes, please go ahead", "greeting"))
    assert c.permission_granted is True


def test_greeting_permission_refused():
    fb = FallbackProvider()
    c = _run(_classify(fb, "No, I'm not interested", "greeting"))
    assert c.permission_granted is False or c.stop_requested is True


def test_greeting_question_does_not_grant_permission():
    fb = FallbackProvider()
    c = _run(_classify(fb, "How much does it cost?", "greeting"))
    assert c.question_topic == "price"
    assert c.permission_granted is None


def test_early_answers_imply_permission():
    fb = FallbackProvider()
    c = _run(_classify(fb, "It's for investment, I'm comfortable with Nandi Hills, budget is around 2 crore, and 2029 works fine", "greeting"))
    assert c.permission_granted is True
    assert c.intent == "investment"
    assert c.geography_comfortable is True
    assert c.budget_fit is True
    assert c.timeline_ok is True


def test_intent_detection():
    fb = FallbackProvider()
    assert _run(_classify(fb, "For my own weekend home", "intent")).intent == "self_use"
    assert _run(_classify(fb, "For investment returns", "intent")).intent == "investment"
    assert _run(_classify(fb, "Both - a home and an investment", "intent")).intent == "both"
    assert _run(_classify(fb, "Apne ghar ke liye", "intent")).intent == "self_use"


def test_geography_answer():
    fb = FallbackProvider()
    assert _run(_classify(fb, "Yes, comfortable", "geography")).geography_comfortable is True
    assert _run(_classify(fb, "Too far for me", "geography")).geography_comfortable is False


def test_geography_answer_with_area_word_is_not_a_question():
    fb = FallbackProvider()
    c = _run(_classify(
        fb,
        "Yes, I know the Nandi Hills area well - my parents live in Devanahalli, so I'm very comfortable.",
        "geography",
    ))
    assert c.geography_comfortable is True
    assert c.question_topic is None, "'area' must not trigger a size question"


def test_permission_acknowledged_in_intent_reply():
    fb = FallbackProvider()
    c = _run(_classify(fb, "Yes, please go ahead", "greeting"))
    reply = _run(fb.generate_reply(
        snapshot={"state": "intent", "closed_reason": None, "needs_reask": False},
        classification=c, history=[], system_prompt="",
    ))
    assert "Perfect, thank you!" in reply
    assert "weekend" in reply.lower()


def test_budget_answer():
    fb = FallbackProvider()
    assert _run(_classify(fb, "Yes, budget is fine", "budget")).budget_fit is True
    assert _run(_classify(fb, "That's too expensive", "budget")).budget_fit is False
    assert _run(_classify(fb, "Around 2 crore", "budget")).budget_fit is True
    assert _run(_classify(fb, "Only 70 lakh", "budget")).budget_fit is False


def test_timeline_answer():
    fb = FallbackProvider()
    assert _run(_classify(fb, "2029 is fine, no problem", "timeline")).timeline_ok is True
    assert _run(_classify(fb, "Too long, I can't wait", "timeline")).timeline_ok is False


def test_stop_and_irritation():
    fb = FallbackProvider()
    assert _run(_classify(fb, "Please stop calling me", "intent")).stop_requested is True
    assert _run(_classify(fb, "You are so annoying, stop wasting my time", "budget")).irritated is True


def test_hindi_language_detection():
    fb = FallbackProvider()
    assert _run(_classify(fb, "Haan, theek hai", "geography")).language in ("hi", "hinglish")
    assert _run(_classify(fb, "हाँ, ठीक है", "geography")).language == "hi"
    assert _run(_classify(fb, "Yes, it's fine", "geography")).language == "en"


def test_pitch_question_answered_from_kb():
    fb = FallbackProvider()
    c = _run(_classify(fb, "That sounds nice. What would the returns be like if I don't build immediately, and is the price negotiable?", "pitch"))
    assert c.question_topic is not None
    reply = _run(fb.generate_reply(
        snapshot={"state": "pitch", "closed_reason": None, "needs_reask": False},
        classification=c, history=[], system_prompt="",
    ))
    assert "lakh" in reply.lower() or "92.4" in reply
    assert "property expert" in reply


def test_intent_stage_question_answered_then_reasked():
    fb = FallbackProvider()
    c = _run(_classify(fb, "How much do the plots cost?", "intent"))
    assert c.question_topic == "price"
    reply = _run(fb.generate_reply(
        snapshot={"state": "intent", "closed_reason": None, "needs_reask": False},
        classification=c, history=[], system_prompt="",
    ))
    assert "lakh" in reply.lower()
    assert "weekend home" in reply.lower() or "investment" in reply.lower()


def test_contact_capture():
    fb = FallbackProvider()
    c = _run(_classify(fb, "My name is Rahul and my number is 9876543210", "cta"))
    assert c.contact_name == "Rahul"
    assert c.contact_phone == "9876543210"
    c2 = _run(_classify(fb, "Mera naam Priya hai, 9988776655", "cta"))
    assert c2.contact_name == "Priya"
    assert c2.contact_phone == "9988776655"