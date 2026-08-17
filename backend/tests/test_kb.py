"""Knowledge base + Hinglish regression tests.

Covers: bilingual FAQ answers with verified facts, question-topic detection
for the new KB topics, Hindi budget figures ("ek crore"), and false-positive
protection for desire statements that mention KB words ("greenery",
"open space") but are not questions.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.conversation.project import FAQ, PROJECT
from app.conversation.state import Classification
from app.llm.fallback import FallbackProvider

_loop = None
_worker_exc: list[BaseException] = []


def _run(coro):
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True).start()
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    result = fut.result(30)
    if _worker_exc:
        raise _worker_exc.pop()
    return result


def _classify(text: str) -> Classification:
    p = FallbackProvider()
    return _run(p.classify(
        user_text=text, history=[], state="pitch", system_prompt="",
    ))


# ------------------------------------------------------------------ FAQ structure
def test_faq_every_topic_has_english_and_hindi():
    for topic, (en, hi) in FAQ.items():
        assert en.strip() and hi.strip(), f"{topic}: empty variant"
        assert len(en) < 320, f"{topic}: English answer too long for TTS ({len(en)})"
        assert len(hi) < 320, f"{topic}: Hindi answer too long for TTS ({len(hi)})"


def test_faq_facts_verified():
    assert "PRM/KA/RERA/1250/301/PR/070525/007718" in FAQ["rera"][0]
    assert "92.4" in FAQ["price"][0] and "3.08" in FAQ["price"][0]
    assert "31 December 2029" in FAQ["possession"][0]
    assert "20,000" in FAQ["clubhouse"][0]
    assert "74%" in FAQ["openspace"][0]
    assert "207" in FAQ["project"][0] and "38 acres" in FAQ["project"][0]
    assert "Divyasree" in FAQ["developer"][0]
    assert "flexible payment plans" in FAQ["payments"][0]
    assert "24x7 security" in FAQ["infrastructure"][0]
    assert "Devanahalli town" in FAQ["location"][0]
    assert "PRM/KA/RERA/1250/301/PR/070525/007718" in FAQ["rera"][1]
    assert "92.4 lakh" in FAQ["price"][1] and "3.08 crore" in FAQ["price"][1]


# ------------------------------------------------------------------ question detection
@pytest.mark.parametrize("text,expected", [
    ("Do you have flexible payment plans or EMI options?", "payments"),
    ("Can I get a bank loan for this?", "payments"),
    ("EMI options hain kya?", "payments"),
    ("How many plots are there in total?", "project"),
    ("Kitne plots hain?", "project"),
    ("What about water and electricity supply?", "infrastructure"),
    ("Paani aur bijli ka arrangement kya hai?", "infrastructure"),
    ("Is 24x7 security available?", "infrastructure"),
    ("Open space kitna hai?", "openspace"),
    ("Is the project RERA registered?", "rera"),
    ("Tell me about the clubhouse amenities", "clubhouse"),
    ("What is the price of the 2400 sq ft plot?", "price"),
    ("Location kahan hai exactly?", "location"),
    ("Kab tak possession milega?", "possession"),
])
def test_question_topic_detection(text, expected):
    c = _classify(text)
    assert c.question_topic == expected, f"{text!r} -> {c.question_topic}"


@pytest.mark.parametrize("text", [
    "It's for my family. We want a weekend home where the kids can enjoy the open space.",
    "Main apni retirement ke liye ek shaant jagah dhoondh rahi hoon. Peace aur greenery chahiye.",
    "I'm looking for peace and greenery, nothing more.",
])
def test_desire_statements_are_not_questions(text):
    c = _classify(text)
    assert c.question_topic is None, f"{text!r} -> {c.question_topic}"


def test_loan_mention_triggers_payments_answer():
    """'I'll be taking a loan' is informational, but answering with the payments
    KB entry is the desired product behaviour."""
    c = _classify("My budget is around one crore. I'll be taking a loan though.")
    assert c.question_topic == "payments"


def test_question_after_answer_never_reasks_answered_checkpoint():
    """If the caller answers a checkpoint and asks a KB question in the same
    message, the agent answers the question and continues with the NEXT
    unanswered checkpoint - it must never re-ask what was just answered."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states, replies = [], []
        for m in [
            "Haan bhai, aage badhiye.",
            "Main apna pehla plot kharid raha hoon. Future home bhi aur investment bhi.",
            "Haan, easy hai. Whitefield se Devanahalli ab bahut aasaan hai.",
            "Mera budget ek crore around hai. Loan lena hoga.",
        ]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["intent", "geography", "budget", "budget"]
    assert "EMI" in replies[3] or "emi" in replies[3].lower()
    assert "possession" in replies[3].lower() and "2029" in replies[3]
    assert "92.4 lakh" not in replies[3]  # the budget is NOT re-asked


# ------------------------------------------------------------------ Hindi figures
@pytest.mark.parametrize("text,expected", [
    ("Mera budget ek crore ke around hai.", True),
    ("Mera budget do crore hai.", True),
    ("Hum sirf paanch lakh manage kar sakte hain.", False),
    ("Ek crore ke around soch rahe hain.", True),
    ("Aath lakh se zyada nahi ho payega.", False),
    ("Around 1.5 crore should be fine for us.", True),
    ("We can manage maybe 70 lakh.", False),
])
def test_budget_figures_hindi_and_english(text, expected):
    from app.llm.fallback import _budget_figure_fit
    assert _budget_figure_fit(text) is expected


# ------------------------------------------------------------------ full Hinglish journeys
def test_hinglish_qualified_journey_shobha():
    """Senior citizen, Hinglish: full flow incl. location question in pitch."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states = ["greeting"]
        for m in [
            "Haan ji, bilkul. Aap bataiye.",
            "Main apni retirement ke liye ek shaant jagah dhoondh rahi hoon. Peace aur greenery chahiye.",
            "Haan ji, main comfortable hoon. Mera beta Devanahalli mein rehta hai.",
            "Mera budget ek crore ke around hai.",
            "2029 theek hai, mere beta sab dekh lenge.",
            "Bahut peaceful lag raha hai. Location convenient hai kya - paas mein shops aur hospitals hain?",
            "Haan ji, kripya kisi ko call karne ko bolo.",
            "Mera naam Shobha Rao hai, number 99887 76655, aur subah ka time best hai.",
        ]:
            t = await e.respond(m)
            states.append(t["state"])
        return states, e

    states, engine = _run(run())
    assert states == ["greeting", "intent", "geography", "budget", "timeline",
                      "pitch", "pitch", "cta", "done"]
    assert engine.machine.lead.qualified
    assert engine.machine.lead.name == "Shobha"
    assert engine.machine.lead.phone == "9988776655"
    assert engine.machine.lead.preferred_time == "morning"


def test_hinglish_budget_close_journey_lakshmi():
    """Budget mismatch in Hinglish: one re-ask then graceful close."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states = ["greeting"]
        for m in [
            "Haan ji, bataiye.",
            "Humare liye hai. Ek peaceful second home chahiye.",
            "Haan, humein Devanahalli side pasand hai.",
            "92 lakh toh humare budget se bahut zyada hai. Hum sirf 70 lakh tak manage kar sakte hain.",
            "Nahi, chhota wala plot bhi afford nahi ho payega. Sorry ji.",
        ]:
            t = await e.respond(m)
            states.append(t["state"])
        return states, e

    states, engine = _run(run())
    assert states == ["greeting", "intent", "geography", "budget", "budget", "budget"]
    assert engine.machine.closed_reason == "budget_mismatch"
    assert not engine.machine.lead.qualified


def test_pitch_question_answered_in_hindi():
    """A question during the pitch is answered in Hinglish and flow continues."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states = ["greeting"]
        replies = []
        for m in [
            "Yes please, go ahead.",
            "It's for my weekend home.",
            "Yes, I'm comfortable with the corridor.",
            "Around 1.5 crore is fine.",
            "2029 works for me.",
            "Open space kitna hai?",
            "Yes, please schedule the call.",
            "My name is Anil, phone 90123 45678, evenings work.",
        ]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["greeting", "intent", "geography", "budget", "timeline",
                      "pitch", "pitch", "cta", "done"]
    assert "74%" in replies[5] or "open space" in replies[5].lower()
    assert states[6] == "pitch"


# ------------------------------------------------------------------ assignment architecture audit
def test_architecture_introduction_greeting():
    """Introduction: Divyasree consultant, project + location, permission asked."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        return (await e.start())["reply"]

    greeting = _run(run())
    assert "Meera" in greeting
    assert "Divyasree" in greeting
    assert "Whispers of the Wind" in greeting
    assert "Nandi Hills" in greeting
    assert "May I take two minutes" in greeting


def test_architecture_four_checkpoints_pitch_cta():
    """Qualification checkpoints in order, then pitch, then CTA (exact flow)."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        replies = []
        for m in [
            "Yes, please go ahead.",
            "For my family's weekend home.",
            "Yes, I'm comfortable with the corridor.",
            "Around 1.5 crore is fine.",
            "2029 works for us.",
            "That sounds lovely.",
            "My name is Priya, 90123 45678, morning is fine.",
        ]:
            t = await e.respond(m)
            replies.append(t["reply"])
        return replies

    r = _run(run())
    # 1. INTENT checkpoint
    assert "weekend" in r[0].lower() and "investment" in r[0].lower()
    # 2. GEOGRAPHY checkpoint - Nandi Hills / Devanahalli corridor
    assert "Nandi Hills" in r[1] and ("Devanahalli" in r[1] or "airport" in r[1])
    # 3. BUDGET checkpoint - fitment against the 92.4 lakh starting price
    assert "92.4 lakh" in r[2]
    # 4. TIMELINE checkpoint - phased delivery / ongoing project
    assert "2029" in r[3] and "phased" in r[3].lower()
    # 5. THE PITCH - private valley lifestyle: clubhouse, nature AND community
    pitch = r[4]
    assert "private valley" in pitch.lower()
    assert "clubhouse" in pitch.lower()
    assert "74%" in pitch or "open space" in pitch.lower()
    assert "community" in pitch.lower()
    # 6. CTA - follow-up call with a Property Expert
    assert "property expert" in pitch.lower() or "property expert" in r[5].lower()
    assert "call" in r[5].lower() or "name and a phone" in r[5].lower()


PUSHY = ["hurry", "act fast", "don't miss", "limited time", "limited offer",
         "final call", "reserve now", "just for you", "you should", "you need to",
         "must buy", "last chance", "offer expires"]


def test_cold_call_soft_language_full_journey():
    """A cold caller must never use pushy or presumptive phrasing - across the
    whole end-to-end conversation, including refusals and the close."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        replies = []
        for m in [
            "Yes, please go ahead.",
            "It's for my weekend home.",
            "Yes, I'm comfortable with the corridor.",
            "Around 1.5 crore is fine.",
            "2029 works for us.",
            "That sounds lovely.",
            "Actually, I'll have to think about it.",
            "Sure, my name is Priya, 90123 45678, evenings work.",
        ]:
            t = await e.respond(m)
            replies.append(t["reply"])
        # also a refusal path: no permission + stop
        e2 = ConversationEngine()
        await e2.start()
        r2 = [t["reply"] for m in ["I'm busy right now.", "No, this isn't for me.",
                                   "Please don't call again."] for t in [await e2.respond(m)]]
        return replies, r2

    replies, refusals = _run(run())
    all_text = " ".join(replies + refusals).lower()
    for word in PUSHY:
        assert word not in all_text, f"pushy phrase used: {word!r}"
    assert "may i" in all_text or "would you" in all_text or "shall i" in all_text
    assert "thank" in all_text  # gracious close


def test_cold_call_refusal_gets_easy_exit():
    """When a checkpoint is declined the agent offers a graceful exit,
    never a hard sell."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        replies = []
        for m in ["It's an investment.", "Actually, that area is too far for me.",
                  "It's for my weekend home."]:
            t = await e.respond(m)
            replies.append(t["reply"])
        return replies

    replies = _run(run())
    assert "shall we leave it here" in replies[1].lower() or "yahin khatam" in replies[1]
    assert "share more" in replies[1].lower() or "jankari" in replies[1]
    assert "perfect" in replies[2].lower() or "understand" in replies[2].lower()


def test_geography_reask_acknowledges_new_intent():
    """If the caller answers intent while the corridor re-ask is pending, the
    agent acknowledges it first - never ignores a fresh answer."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states, replies = [], []
        for m in ["Yes, please go ahead.", "For my weekend home.",
                  "Actually, that area is too far.", "It's an investment."]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["intent", "geography", "geography", "geography"]
    assert "investment" in replies[3]
    assert "shall we leave it here" in replies[3].lower()
    # the corridor re-ask is still the question being asked (sequence intact)
    assert "Nandi Hills" not in replies[3]


def test_budget_reask_acknowledges_new_timeline():
    """If the caller answers the timeline while the budget re-ask is pending,
    the agent acknowledges it before the gentle re-ask."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states, replies = [], []
        for m in ["It's an investment.", "Yes, I'm comfortable.",
                  "No, that's above my budget.", "2029 is fine for me."]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["geography", "budget", "budget", "budget"]
    assert "timeline works for you" in replies[3]
    assert "shall we leave it here" in replies[3].lower()
    assert "92.4 lakh" in replies[3]


def test_budget_no_does_not_leak_into_geography():
    """A budget decline during the geography re-ask must NOT be stolen as a
    geography 'no' (which would wrongly close the call) - it is acknowledged
    and the geography question is re-asked."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states, replies = [], []
        for m in ["Yes, go ahead.", "It's an investment.",
                  "Actually, that area is too far.", "No, that's above my budget."]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["intent", "geography", "geography", "geography"]
    assert not any("closed" in s for s in states)
    assert "budget concern" in replies[3]
    assert "shall we leave it here" in replies[3].lower()


def test_timeline_answer_not_stolen_as_geography():
    """A timeline answer during the geography re-ask must stay a timeline
    answer - the geography question is re-asked, the call is not closed."""
    from app.conversation.engine import ConversationEngine

    async def run():
        e = ConversationEngine()
        await e.start()
        states, replies = [], []
        for m in ["Yes, go ahead.", "It's an investment.",
                  "Actually, that area is too far.", "2029 is fine for me."]:
            t = await e.respond(m)
            states.append(t["state"])
            replies.append(t["reply"])
        return states, replies

    states, replies = _run(run())
    assert states == ["intent", "geography", "geography", "geography"]
    assert not any("closed" in s for s in states)
    assert "shall we leave it here" in replies[3].lower()