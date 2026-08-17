"""Offline deterministic provider.

Used when no LLM key is configured or when the LLM is unreachable. It performs
rule-based classification (English + Hindi) and selects natural, flow-aware
replies from a template bank. This keeps the demo fully functional offline and
makes the unit tests deterministic (no network).
"""

from __future__ import annotations

import re

from ..config import get_settings
from ..conversation.project import FAQ
from ..conversation.state import CHECKPOINT_ORDER, Classification
from .base import Provider

_HI_YES = {
    "haan", "han", "ha", "hain", "ji haan", "ji", "haa", "yes", "ya", "acha", "theek",
    "theek hai", "ok", "okay", "hmm", "umm", "sure", "bilkul", "zaroor", "ho jao",
    "fine", "works", "good", "great", "perfect", "lovely", "definitely", "correct",
    "go ahead", "go on", "you may", "please do", "please", "speak", "boliye", "bolo",
    "sakta", "sakte", "ho sakta hai",
}
_HI_NO = {
    "nahi", "na", "no", "nope", "nahi nahi", "bilkul nahi", "not", "never", "nahii",
}
_GEO_NO = {"far", "too far", "door", "dur", "duur", "bahut door", "not convenient", "inconvenient"}
_GEO_YES = {"not far", "isn't far", "isnt far", "not too far", "close", "near", "pas"}
_BUDGET_NO = {
    "can't afford", "cannot afford", "too expensive", "out of budget", "expensive",
    "mahanga", "mehnga", "budget nahi", "beyond my budget", "above my budget",
    "over my budget", "not affordable", "more than my budget",
}
_BUDGET_YES = {"affordable", "within budget", "can afford", "fits", "fits my budget"}

_PHONE_RE = re.compile(r"(\+?\d[\d\s\-]{8,}\d)")
_NAME_RE = re.compile(
    r"(?:my name is|i am|i'm|name's|name is|this is)\s+([A-Za-z]+)",
    re.IGNORECASE,
)
_HI_NAME_RE = re.compile(r"(?:mera naam|naam)\s+([\u0900-\u097F\w]+)", re.IGNORECASE)

_INTENT_SELF = [
    "self", "own", "home", "weekend", "holiday home", "second home", "vacation", "myself",
    "personal", "family", "retire", "retirement", "myself and", "for me", "my home",
    "ghar", "khud", "apne ghar", "apna ghar",
]
_INTENT_INVEST = [
    "invest", "investment", "returns", "appreciation", "rental", "yield", "nri",
    "high return", "value growth", "future", "profit", "nivesh", "invest kar",
]
_IRRITATED = [
    "annoying", "waste", "wasting", "don't waste", "stop disturbing", "fed up",
    "irritating", "harassing", "peshan", "peshan mat", "parshan", "parshani",
    "परेशान", "परेशानी", "bahut ho gaya", "chhod do", "chhodho",
]
_STOP = [
    "stop", "bye", "goodbye", "good bye", "hang up", "don't call", "do not call",
    "remove me", "take me off", "not interested", "call band", "band karo",
    "mujhe nahi chahiye", "mujhe nahi", "ना", "nhi chahiye", "nahi chahiye",
    "go away", "leave me alone", "dismiss", "end call", "cancel",
]

_QUESTION_MAP = [
    ("payments", ["payment plan", "payment plans", "emi", "installment", "installments", "financing", "loan", "finance", "kitne mein milega", "emi kaise"]),
    ("project", ["how many plots", "kitne plots", "total plots", "project size", "kitna bada", "how big", "38 acres", "how many villa"]),
    ("infrastructure", ["water", "electricity", "power", "sewage", "drainage", "security", "infrastructure", "paani", "bijli"]),
    ("openspace", ["how much open", "open space kitna", "kitna open", "kitni open", "how much space", "kitna open space"]),
    ("price", ["price", "cost", "rate", "kitna", "kitne", "how much", "pricing", "quotation"]),
    ("size", ["size", "sq ft", "sqft", "square feet", "dimension", "plot size"]),
    ("location", ["where is", "where are", "where can", "where do", "where does", "where will", "where should", "where would", "where exactly", "where's", "location", "address", "kahan", "kaha", "kahaan", "far from", "distance"]),
    ("possession", ["possession", "delivery", "handover", "when is", "when will", "when can", "when do", "when exactly", "when's", "kab tak", "timeline"]),
    ("rera", ["rera", "registered", "approval", "approved", "legal", "document", "trust"]),
    ("clubhouse", ["clubhouse", "amenities", "facilities", "gym", "pool", "club"]),
    ("investment", ["good investment", "investment returns", "roi", "returns"]),
    ("developer", ["divyasree", "divya sree", "builder", "developer", "reputation", "divya"]),
    ("booking", ["book", "booking", "advance", "registration", "apply", "reserve", "buy", "purchase"]),
]

_HINDI_CHAR = re.compile(r"[\u0900-\u097F]")
_HINDI_ROMAN = {
    "haan", "ha", "nahi", "acha", "achha", "theek", "main", "hai", "kya", "mujhe",
    "chahiye", "kar", "ji", "bahut", "samajh", "apka", "aapka", "aap", "mera",
    "naam", "kaun", "kahaan", "kahan", "kyun", "nivesh", "invest kar", "ghar",
    "zameen", "bol", "sakta", "sakte", "karein", "jao", "kya hai",
}


def _has_budget_signal(low: str) -> bool:
    """True when the message talks about money (amount or budget words)."""
    if _contains_any(low, list(_BUDGET_YES) + list(_BUDGET_NO)):
        return True
    return _budget_figure_fit(low) is not None


def _has_timeline_signal(low: str) -> bool:
    """True when the message talks about the timeline (year or delivery words)."""
    if _contains_any(low, ["too long", "can't wait", "cannot wait", "need soon",
                           "jaldi chahiye", "bahut der"]):
        return True
    return re.search(r"20(2[0-9])", low) is not None


def _contains_any(text: str, words: list[str]) -> bool:
    low = text.lower()
    for w in words:
        if w in low:
            return True
    return False


_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(cr|crore|lakh|lac|cr\.)", re.IGNORECASE)

# Hindi number words -> digits, so "ek crore", "paanch lakh" parse like figures.
_HINDI_NUMBERS = {
    "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5",
    "chhe": "6", "saat": "7", "aath": "8", "nau": "9", "das": "10",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
}
_HINDI_AMOUNT_RE = re.compile(
    r"\b(" + "|".join(_HINDI_NUMBERS) + r")\s*(crore|lakh|lac)\b", re.IGNORECASE)


def _budget_figure_fit(text: str) -> bool | None:
    """Budget fit from an explicit figure: >= 92.4 lakh means it fits."""
    normalized = _HINDI_AMOUNT_RE.sub(
        lambda m: f"{_HINDI_NUMBERS[m.group(1).lower()]} {m.group(2)}", text)
    m = _AMOUNT_RE.search(normalized)
    if not m:
        return None
    amount = float(m.group(1))
    unit = m.group(2).lower()
    if unit in ("cr", "crore"):
        lakhs = amount * 100
    else:
        lakhs = amount
    return lakhs >= 92.4


def _timeline_figure_fit(text: str) -> bool | None:
    """Timeline fit from an explicit year: accepting 2029+ (or a 2029 mention)
    means OK; wanting delivery before 2029 means not OK."""
    years = re.findall(r"20(2[0-9])", text)
    if not years:
        return None
    latest = max(int("20" + y) for y in years)
    if latest >= 2029:
        return True
    return False


def _language(text: str) -> str:
    if _HINDI_CHAR.search(text):
        return "hi"
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    if tokens & _HINDI_ROMAN:
        return "hinglish"
    return "en"


def _b(text: str, yes_words: set[str], no_words: set[str]) -> bool | None:
    """Word-tokenised yes/no matcher.

    Handles attached punctuation ("yes,") and affirmative phrases that contain
    a negation word ("no problem", "no issues" mean YES).
    """
    low = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    tokens = set(low.split())
    affirm_phrases = {
        "no problem", "no issues", "no issue", "no worries", "no tension",
        "no doubt", "no hesitation", "no objection", "no confusion",
        "not a problem", "no matter",
    }
    if any(p in low for p in affirm_phrases):
        return True
    multi_no = {w for w in no_words if " " in w}
    multi_yes = {w for w in yes_words if " " in w}
    if tokens & no_words or any(w in low for w in multi_no):
        return False
    if tokens & yes_words or any(w in low for w in multi_yes):
        return True
    return None


class FallbackProvider(Provider):
    name = "fallback"

    async def classify(
        self,
        *,
        user_text: str,
        history: list[dict],
        state: str,
        system_prompt: str,
    ) -> Classification:
        text = user_text.strip()
        lang = _language(text)

        phone = None
        m = _PHONE_RE.search(text)
        if m:
            phone = re.sub(r"[\s\-]+", "", m.group(1))
        name = None
        m = _NAME_RE.search(text) or _HI_NAME_RE.search(text)
        if m:
            name = m.group(1).strip().strip(".,")

        preferred_time = None
        _TIME_ALIASES = {"sham": "evening", "subah": "morning"}
        for tok in ("evening", "morning", "afternoon", "tomorrow", "weekend", "night", "sham", "subah"):
            if tok in text.lower():
                preferred_time = _TIME_ALIASES.get(tok, tok)
                break

        question_topic = None
        low = text.lower()
        for topic, words in _QUESTION_MAP:
            if _contains_any(low, words):
                question_topic = topic
                break

        # Early checkpoint answers can arrive in any state (e.g. right after the
        # introduction). Detect them from clear context signals only.
        geography_comfortable = None
        if _contains_any(low, _GEO_YES) or (
            ("comfortable" in low or "nandi" in low) and _b(text, _HI_YES, _HI_NO) is True
        ):
            geography_comfortable = True
        elif _contains_any(low, _GEO_NO):
            geography_comfortable = False

        budget_fit = None
        if _contains_any(low, _BUDGET_YES) and _b(text, _HI_YES, _HI_NO) is not False:
            budget_fit = True
        elif _contains_any(low, _BUDGET_NO):
            budget_fit = False
        else:
            budget_fit = _budget_figure_fit(text)

        timeline_ok = None
        if _contains_any(low, ["too long", "can't wait", "cannot wait", "need soon", "jaldi chahiye", "bahut der"]):
            timeline_ok = False
        else:
            timeline_ok = _timeline_figure_fit(text)

        # An answered checkpoint is an answer, not a question.
        if question_topic in ("location", "price", "investment", "possession") and (
            geography_comfortable is not None or budget_fit is not None or timeline_ok is not None
        ):
            question_topic = None

        stop = _contains_any(low, _STOP)
        irritated = _contains_any(low, _IRRITATED)
        if irritated and stop:
            stop = True

        intent = None
        if _contains_any(low, _INTENT_SELF) and _contains_any(low, _INTENT_INVEST):
            intent = "both"
        elif _contains_any(low, _INTENT_SELF):
            intent = "self_use"
        elif _contains_any(low, _INTENT_INVEST):
            intent = "investment"

        permission_granted = permission_refused = None
        if state == "greeting":
            answered_early = intent is not None or (
                geography_comfortable is not None or budget_fit is not None or timeline_ok is not None
            )
            if _b(text, _HI_YES, _HI_NO) is True and question_topic is None and not stop:
                permission_granted = True
            elif _b(text, _HI_YES, _HI_NO) is False:
                permission_refused = True
            elif answered_early and not stop:
                # Engaging by answering a checkpoint early = implicit permission.
                permission_granted = True

        if state == "geography":
            if geography_comfortable is None:
                # A money/timeline mention means they are answering a different
                # checkpoint - never steal it as a geography answer.
                if not _has_budget_signal(low) and not _has_timeline_signal(low):
                    geography_comfortable = _b(text, _HI_YES, _HI_NO)
        elif state == "budget":
            if budget_fit is None:
                # A year/delivery mention is a timeline answer, not a budget answer.
                if not _has_timeline_signal(low):
                    budget_fit = _b(text, _HI_YES, _HI_NO)
                    if budget_fit is None:
                        budget_fit = _budget_figure_fit(text)
        elif state == "timeline":
            if timeline_ok is None:
                # A money mention is a budget answer, not a timeline answer.
                if not _has_budget_signal(low):
                    timeline_ok = _b(text, _HI_YES, _HI_NO)
                    if timeline_ok is None:
                        timeline_ok = _timeline_figure_fit(text)

        return Classification(
            language=lang,
            permission_granted=permission_granted,
            intent=intent,
            geography_comfortable=geography_comfortable,
            budget_fit=budget_fit,
            timeline_ok=timeline_ok,
            stop_requested=stop,
            irritated=irritated,
            question_topic=question_topic,
            contact_name=name,
            contact_phone=phone,
            preferred_time=preferred_time,
            source_text=text,
        )

    # ------------------------------------------------------------------ replies
    async def generate_reply(
        self,
        *,
        snapshot: dict,
        classification: Classification,
        history: list[dict],
        system_prompt: str,
    ) -> str:
        return _fallback_reply(snapshot, classification)


def _hi_flag(c: Classification) -> bool:
    return c.language in ("hi", "hinglish")


_CONTINUATIONS = {
    "greeting": (
        "May I continue and ask you a couple of quick questions?",
        "Kya main aage badh sakti hoon?",
    ),
    "intent": (
        "Are you considering this for your own weekend home, or as an investment?",
        "Kya aap ye apne weekend ghar ke liye soch rahe hain, ya investment ke liye?",
    ),
    "geography": (
        "And are you comfortable with the Nandi Hills and Devanahalli corridor, "
        "about 20 minutes from the airport?",
        "Aur kya aap Nandi Hills aur Devanahalli corridor se comfortable hain, "
        "airport se kareeb 20 minute?",
    ),
    "budget": (
        "And may I ask - does a starting price of Rs 92.4 lakh, inclusive of "
        "taxes, fit within your budget?",
        "Aur kya main pooch sakti hoon - kya Rs 92.4 lakh ki starting price, "
        "taxes ke saath, aapke budget mein fit hoti hai?",
    ),
    "timeline": (
        "Possession is expected by December 2029, with phased delivery. "
        "Would that timeline work for you?",
        "Possession December 2029 tak expected hai, phased delivery ke saath. "
        "Kya wo timeline aapke liye theek hai?",
    ),
    "pitch": (
        "Shall I have one of our property experts call you to walk through "
        "the available plots?",
        "Kya main hamare property expert ko aapko call karne ke liye keh sakti hoon?",
    ),
    "cta": (
        "May I have your name and a phone number, and a good time to call - "
        "so our property expert can reach you?",
        "Kya main aapka naam aur phone number le sakti hoon, aur kaunse time "
        "par call karein - taaki hamare property expert aap tak pahunch sakein?",
    ),
    "done": ("", ""),
}

# lead key holding the answer for each checkpoint state.
_ANSWERED_LEAD_KEY = {
    "intent": "intent",
    "geography": "geography_comfortable",
    "budget": "budget_fit",
    "timeline": "timeline_ok",
}


def _question_continuation(state: str, snapshot: dict, hi: bool) -> str:
    """After answering a caller question, resume with the NEXT unanswered step.

    A checkpoint question is never re-asked once it has been answered, so the
    flow keeps its proper sequence even when the caller answers early while a
    question is pending."""
    pair = _CONTINUATIONS[state]
    if state in ("greeting", "pitch", "cta", "done"):
        return pair[1] if hi else pair[0]
    # A checkpoint was declined once: keep the gentle re-ask, not a new question.
    if snapshot.get("needs_reask") and state == "geography":
        return ("Would you like me to share more, or shall we leave it here?",
                "Kya main aapko aur jankari doon, ya yahin khatam karein?")[1 if hi else 0]
    if snapshot.get("needs_reask") and state == "budget":
        return ("Would flexible payment planning help, or shall we leave it here?",
                "Kya flexible payment planning se madad milegi, ya yahin khatam karein?")[1 if hi else 0]
    lead = snapshot.get("lead", {})
    for s in CHECKPOINT_ORDER[CHECKPOINT_ORDER.index(state):]:
        if not lead.get(_ANSWERED_LEAD_KEY[s]):
            p = _CONTINUATIONS[s]
            return p[1] if hi else p[0]
    p = _CONTINUATIONS["pitch"]
    return p[1] if hi else p[0]


def _fallback_reply(snapshot: dict, c: Classification) -> str:
    hi = _hi_flag(c)
    state = snapshot["state"]
    closed_reason = snapshot.get("closed_reason")
    needs_reask = snapshot.get("needs_reask", False)
    settings = get_settings()
    agent = settings.agent_name

    if closed_reason:
        return _closing(closed_reason, hi)

    if c.question_topic:
        entry = FAQ.get(c.question_topic)
        if entry:
            answer = entry[1] if hi else entry[0]
        else:
            answer = (
                "That's a great question - let me share the details with you."
                if not hi else
                "Bahut achha sawaal - main aapko details bata deti hoon."
            )
        tail = _question_continuation(state, snapshot, hi)
        return f"{answer} {tail}" if tail else answer

    if state == "greeting":
        if c.permission_granted is True:
            return (
                "Perfect, thank you! So, are you considering this for your own weekend "
                "or holiday home, or as an investment?"
                if not hi else
                "Badhiya, dhanyavaad! Toh kya aap ye apne weekend ya holiday ghar ke liye "
                "soch rahe hain, ya investment ke liye?"
            )
        return _greeting(hi, agent)

    if state == "intent":
        if c.intent == "self_use":
            return (
                "Understood, a personal weekend home is a lovely choice. Now, are you "
                "comfortable with the Nandi Hills and Devanahalli corridor, about 20 "
                "minutes from the airport?"
                if not hi else
                "Samajh gayi, apna weekend ghar - bahut badhiya. Kya aap Nandi Hills aur "
                "Devanahalli corridor se comfortable hain, airport se kareeb 20 minute?"
            )
        if c.intent == "investment":
            return (
                "Excellent, that's a smart move given the Devanahalli growth corridor. "
                "Are you comfortable with the Nandi Hills area, about 20 minutes from "
                "the airport?"
                if not hi else
                "Bahut badhiya, ye samajhdari wala decision hai. Kya aap Nandi Hills "
                "ke area se comfortable hain, airport se kareeb 20 minute?"
            )
        if c.intent == "both":
            return (
                "Perfect - a home that works as an investment too. Now, are you "
                "comfortable with the Nandi Hills and Devanahalli corridor, about 20 "
                "minutes from the airport?"
                if not hi else
                "Badhiya - ghar bhi aur investment bhi. Kya aap Nandi Hills aur "
                "Devanahalli corridor se comfortable hain?"
            )
        # Permission was just granted -> acknowledge before the first question.
        if c.permission_granted is True:
            return (
                "Perfect, thank you! So, are you considering this for your own weekend "
                "home, or as an investment?"
                if not hi else
                "Badhiya, dhanyavaad! Toh kya aap ye apne weekend ya holiday ghar ke "
                "liye soch rahe hain, ya investment ke liye?"
            )
        # not answered -> ask
        return (
            "No problem at all - are you considering this for your own weekend home, "
            "or as an investment?"
            if not hi else
            "Koi baat nahi - kya aap ye apne weekend ghar ke liye soch rahe hain, "
            "ya investment ke liye?"
        )

    if state == "geography":
        if needs_reask:
            ack_en = ack_hi = ""
            if "intent" in (snapshot.get("answered_now") or []) and c.intent:
                if c.intent == "investment":
                    ack_en = "Understood - noted for investment. "
                    ack_hi = "Samajh gayi - investment ke liye note kar liya. "
                elif c.intent == "both":
                    ack_en = "Understood - a home and an investment. "
                    ack_hi = "Samajh gayi - ghar aur investment dono. "
                else:
                    ack_en = "Understood - for your weekend home. "
                    ack_hi = "Samajh gayi - aapke weekend ghar ke liye. "
            if c.budget_fit is False:
                ack_en += "And I understand the budget concern as well. "
                ack_hi += "Aur budget ki pareshani bhi samajh sakti hoon. "
            return (
                ack_en + "I completely understand. Just to note - it's only about 20 "
                "minutes from the airport and close to the Devanahalli Business Park "
                "and the upcoming gondola project. Would you like me to share more, "
                "or shall we leave it here?"
                if not hi else
                ack_hi + "Main samajh gayi. Bas itna bata doon - airport se sirf 20 "
                "minute aur Devanahalli Business Park ke paas hai. Kya main aapko "
                "aur jankari doon, ya yahin khatam karein?"
            )
        if c.geography_comfortable is True:
            return (
                "That's great to hear! Moving on - does a starting price of Rs 92.4 "
                "lakh, inclusive of taxes, fit within your budget?"
                if not hi else
                "Bahut achha sunne ko mila! Agla sawal - kya Rs 92.4 lakh ki starting "
                "price, taxes ke saath, aapke budget mein fit hoti hai?"
            )
        # Geography not yet answered -> ask the geography checkpoint question.
        return (
            "Perfect, thank you. And are you comfortable with the Nandi Hills and "
            "Devanahalli corridor, about 20 minutes from the airport?"
            if not hi else
            "Badhiya, dhanyavaad. Aur kya aap Nandi Hills aur Devanahalli corridor "
            "se comfortable hain, airport se kareeb 20 minute?"
        )

    if state == "budget":
        if needs_reask:
            ack_en = ack_hi = ""
            if "timeline" in (snapshot.get("answered_now") or []) and c.timeline_ok is True:
                ack_en = "Good to know that timeline works for you. "
                ack_hi = "Achha, wo timeline aapko theek lagti hai, badhiya. "
            return (
                ack_en + "Understood, I appreciate your honesty. Just for reference, "
                "the entry plot is 1,200 sq.ft. at Rs 92.4 lakh - could that work "
                "for you, or shall we leave it here?"
                if not hi else
                ack_hi + "Main samajh gayi, aapki sachchai ke liye dhanyavaad. Chhota "
                "plot 1,200 sq.ft. Rs 92.4 lakh se shuru hota hai - kya wo kaam kar "
                "sakta hai, ya yahin khatam karein?"
            )
        if c.budget_fit is True:
            return (
                "Perfect, that works. And one more - possession is expected by December "
                "2029, with phased delivery. Does that timeline work for you?"
                if not hi else
                "Badhiya. Aur ek aur - possession December 2029 tak expected hai, "
                "phased delivery ke saath. Kya wo timeline aapko theek lagti hai?"
            )
        # Budget not yet answered -> ask the budget checkpoint question.
        return (
            "Understood. And may I ask - does a starting price of Rs 92.4 lakh, "
            "inclusive of taxes, fit within your budget?"
            if not hi else
            "Samajh gayi. Aur kya main poochh sakti hoon - kya Rs 92.4 lakh ki "
            "starting price, taxes ke saath, aapke budget mein fit hoti hai?"
        )

    if state == "timeline":
        if c.timeline_ok is False:
            return (
                "I completely understand, and it's worth noting the project is being "
                "delivered in phases. Let me still share what makes it special... "
                "Whispers of the Wind is a private valley where 74% of the 38 acres "
                "is open space - eco-parks, a 20,000 sq.ft. clubhouse, panoramic "
                "Nandi Hills views and a like-minded community of discerning buyers. "
                "Would it be okay if one of our property experts gave you a call to "
                "share more?"
                if not hi else
                "Main poori tarah samajhti hoon. Phir bhi aapko batati hoon ki kya "
                "khaas hai... Whispers of the Wind ek private valley hai jahan 38 "
                "acres ka 74% open space hai - eco-parks, 20,000 sq.ft. clubhouse, "
                "charo taraf Nandi Hills ke nazare aur ek jaise sochne walon ka "
                "behtareen community. Kya hamare property expert aapko ek baar "
                "call kar sakte hain?"
            )
        if c.timeline_ok is True:
            return (
                "Wonderful - that gives you time to plan your dream home. Picture "
                "this: a private valley where 74% of the 38 acres is open space, a "
                "20,000 sq.ft. clubhouse and eco-parks, all framed by the Nandi "
                "Hills - with a like-minded community of discerning buyers. May I "
                "have one of our property experts call you to share more?"
                if not hi else
                "Badhiya - aapko apne dream home ki planning ke liye time milega. "
                "Sochiye: ek private valley jahan 38 acres ka 74% open space hai, "
                "20,000 sq.ft. clubhouse, eco-parks, Nandi Hills ke nazare - aur "
                "ek jaise sochne walon ka behtareen community. Kya hamare property "
                "expert aapko call kar sakte hain?"
            )
        # Timeline not yet answered -> ask the possession question.
        return (
            "Just one more thing - possession is expected by December 2029, with "
            "phased delivery. Would that timeline work for you?"
            if not hi else
            "Bas ek aur sawal - possession December 2029 tak expected hai, phased "
            "delivery ke saath. Kya wo timeline aapke liye theek hai?"
        )

    if state == "pitch":
        return (
            "Whispers of the Wind is more than a plot - it's a private valley where "
            "74% of the 38 acres stays open: eco-parks, gardens and a 20,000 sq.ft. "
            "clubhouse, all framed by the Nandi Hills - a like-minded community of "
            "discerning buyers. May I have one of our property experts call you to "
            "walk you through the available plots?"
            if not hi else
            "Whispers of the Wind sirf ek plot nahi - ye ek private valley hai jahan "
            "38 acres ka 74% khula hai: eco-parks, baag aur 20,000 sq.ft. clubhouse, "
            "Nandi Hills ke beech - ek jaise sochne walon ka behtareen community. "
            "Kya main hamare property expert ko aapko call karne ke liye keh sakti "
            "hoon?"
        )

    if state == "cta":
        if c.contact_phone or c.contact_name:
            parts = []
            if c.contact_name:
                parts.append(c.contact_name)
            if c.contact_phone:
                parts.append(c.contact_phone)
            who = " ".join(parts)
            return (
                f"Thank you, {who} - our property expert will call you "
                f"{('in the ' + c.preferred_time) if c.preferred_time else 'shortly'} "
                "to walk you through the details. Have a wonderful day, and we look "
                "forward to welcoming you to Whispers of the Wind!"
                if not hi else
                f"Dhanyavaad {c.contact_name or ''} - hamare property expert aapko "
                f"{('shaam ko ' + c.preferred_time) if c.preferred_time else 'jald hi'} "
                "call karenge. Aapka din shubh ho, aur hum aapka intezaar karenge "
                "Whispers of the Wind mein!"
            )
        return (
            "Of course! May I have your name and a phone number, and a good time to "
            "call - so our property expert can reach you?"
            if not hi else
            "Zaroor! Kya main aapka naam aur phone number le sakti hoon, aur kaunse "
            "time par call karein - taaki hamare property expert aap tak pahunch "
            "sakein?"
        )

    if state == "done":
        return (
            "Thank you so much for your time - our property expert will be in touch. "
            "Have a wonderful day!"
            if not hi else
            "Aapke waqt ke liye bahut dhanyavaad - hamare property expert aapko "
            "contact karenge. Aapka din shubh ho!"
        )

    return "Thank you for your time. Have a great day!"


def _greeting(hi: bool, agent: str) -> str:
    if hi:
        return (
            "Namaste! Main Divyasree Developers se baat kar rahi hoon - Nandi Hills "
            "ke paas premium villa plots ke baare mein. Kya main aapke do minute le "
            "sakti hoon?"
        )
    return (
        f"Good evening! This is {agent} from Divyasree Developers, calling about "
        "Whispers of the Wind - premium villa plots near Nandi Hills, North "
        "Bengaluru. May I take two minutes of your time?"
    )


def _closing(reason: str, hi: bool) -> str:
    hi_msgs = {
        "permission_refused": (
            "Koi baat nahi, main samajhti hoon. Call karne ke liye khed hai. "
            "Aapka din shubh ho!"
        ),
        "location_mismatch": (
            "Main samajh gayi. Agar kabhi aap Nandi Valley dekhna chahein, hum "
            "yahan hain. Dhanyavaad aur aapka din shubh ho!"
        ),
        "budget_mismatch": (
            "Bilkul samajh gayi. Agar future mein aapki plan badle, toh humse zaroor "
            "baat karein. Dhanyavaad, aapka din shubh ho!"
        ),
        "stop_requested": (
            "Bilkul, main turant rukta hoon. Interruption ke liye khed hai. "
            "Aapka din shubh ho!"
        ),
        "irritated": (
            "Mujhe bahut khed hai ki aapko pareshani hui. Main aapka naam list se "
            "hata dunga. Dhanyavaad aur aapka din shubh ho!"
        ),
    }
    en_msgs = {
        "permission_refused": (
            "No problem at all, I completely understand. I apologise for the "
            "interruption. Have a wonderful day!"
        ),
        "location_mismatch": (
            "I completely understand. If you ever reconsider the Nandi Valley, we "
            "would love to show you around. Thank you and have a wonderful day!"
        ),
        "budget_mismatch": (
            "I completely understand. If your plans change in the future, please "
            "do reach out. Thank you and have a wonderful day!"
        ),
        "stop_requested": (
            "Of course, I'll stop right away. I apologise for the interruption. "
            "Have a wonderful day!"
        ),
        "irritated": (
            "I'm truly sorry for any inconvenience. I'll make sure your number is "
            "removed from our list. Thank you and have a wonderful day!"
        ),
    }
    return (hi_msgs if hi else en_msgs).get(reason, "Thank you for your time.")
