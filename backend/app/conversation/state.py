"""Conversation state machine for the WOW outbound voice agent.

Flow (per the assignment):
    greeting (intro + ask permission)
        -> intent (self-use vs investment)
        -> geography (Nandi Hills / Devanahalli corridor comfort)
        -> budget   (fitment vs Rs 92.4 lakh+ starting price)
        -> timeline (comfort with phased delivery / Dec 2029 possession)
        -> pitch    (aspirational Private Valley lifestyle)
        -> cta      (follow-up call with a Property Expert)
        -> done

Edge cases handled in the machine:
    - permission refused              -> closed(permission_refused)
    - not comfortable with location   -> one re-ask, then closed(location_mismatch)
    - budget does not fit             -> one re-ask (payment/planning help), then closed(budget_mismatch)
    - timeline not ok                 -> acknowledged, flagged, flow continues
    - stop request / irritated user   -> closed(stop_requested | irritated)
    - early answers                   -> machine skips already-answered checkpoints
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional

CHECKPOINT_ORDER = ["intent", "geography", "budget", "timeline"]

# Question asked by the bot when entering each state.
STATE_QUESTIONS = {
    "greeting": (
        "May I have your permission to speak with you for a couple of minutes? "
        "I promise to keep it brief."
    ),
    "permission_refused": None,
    "intent": (
        "Are you considering this for your own weekend or holiday home, "
        "or as an investment?"
    ),
    "geography": (
        "Are you comfortable with the Nandi Hills and Devanahalli corridor, "
        "about 20 minutes from the airport?"
    ),
    "budget": (
        "And may I ask, does a starting price of Rs 92.4 lakh, inclusive of taxes, "
        "fit within your budget?"
    ),
    "timeline": (
        "One last thing before I share more — possession is expected by December 2029, "
        "with phased delivery. Does that timeline work for you?"
    ),
    "pitch": (
        "Let me paint a picture of what awaits you at Whispers of the Wind..."
    ),
    "cta": (
        "Would it be okay if one of our property experts gives you a call to walk "
        "you through the details?"
    ),
    "done": None,
}


class ClosedReason(str, Enum):
    PERMISSION_REFUSED = "permission_refused"
    LOCATION_MISMATCH = "location_mismatch"
    BUDGET_MISMATCH = "budget_mismatch"
    STOP_REQUESTED = "stop_requested"
    IRRITATED = "irritated"


@dataclass
class LeadProfile:
    """Accumulated qualification data for the lead."""

    intent: Optional[str] = None            # self_use | investment | both
    geography_comfortable: Optional[bool] = None
    budget_fit: Optional[bool] = None
    timeline_ok: Optional[bool] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    preferred_time: Optional[str] = None
    language: str = "en"                    # en | hi | hinglish
    notes: list[str] = field(default_factory=list)

    @property
    def qualified(self) -> bool:
        """Qualified = passed intent + geography + budget + timeline."""
        return (
            self.intent is not None
            and self.geography_comfortable is True
            and self.budget_fit is True
            and self.timeline_ok is True
        )

    def summary(self) -> dict:
        return {
            "intent": self.intent,
            "geography_comfortable": self.geography_comfortable,
            "budget_fit": self.budget_fit,
            "timeline_ok": self.timeline_ok,
            "name": self.name,
            "phone": self.phone,
            "preferred_time": self.preferred_time,
            "language": self.language,
            "qualified": self.qualified,
            "notes": self.notes,
        }


@dataclass
class Classification:
    """Structured understanding of the user's latest message."""

    language: str = "en"
    permission_granted: Optional[bool] = None   # True | False | None (not addressed)
    intent: Optional[str] = None
    geography_comfortable: Optional[bool] = None
    budget_fit: Optional[bool] = None
    timeline_ok: Optional[bool] = None
    stop_requested: bool = False
    irritated: bool = False
    question_topic: Optional[str] = None        # e.g. "price", "rera", "location"
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    preferred_time: Optional[str] = None
    source_text: str = ""               # raw caller message this classification refers to


class ConversationStateMachine:
    """Tracks where the conversation is and advances it based on classifications."""

    def __init__(self) -> None:
        self.state: str = "greeting"
        self.lead = LeadProfile()
        self.closed_reason: Optional[str] = None
        self._reask_count = 0
        self._pitch_delivered = False
        self._answered_now: set[str] = set()

    # ------------------------------------------------------------------ helpers
    @property
    def closed(self) -> bool:
        return self.closed_reason is not None

    def _close(self, reason: ClosedReason) -> None:
        self.closed_reason = reason.value

    def _answer_question(self, c: Classification) -> None:
        """A user question is answered in-place; flow does not advance."""
        if c.question_topic:
            self.lead.notes.append(f"asked about: {c.question_topic}")

    # ------------------------------------------------------------------ advance
    def advance(self, c: Classification) -> None:
        """Apply a classification to the machine; may change state or close the call."""
        self._answered_now = set()
        if self.closed:
            return

        # Contact info can arrive at any point.
        if c.contact_name:
            self.lead.name = c.contact_name
        if c.contact_phone:
            self.lead.phone = c.contact_phone
        if c.preferred_time:
            self.lead.preferred_time = c.preferred_time
        if c.language in ("hi", "hinglish") and self.lead.language == "en":
            self.lead.language = c.language

        # Early answers: any checkpoint answered is recorded on the lead at once.
        if c.intent:
            self.lead.intent = c.intent
            self._answered_now.add("intent")
        if c.geography_comfortable is True:
            self.lead.geography_comfortable = True
            self._answered_now.add("geography")
        if c.budget_fit is True:
            self.lead.budget_fit = True
            self._answered_now.add("budget")
        if c.timeline_ok is True:
            self.lead.timeline_ok = True
            self._answered_now.add("timeline")

        # ---- global overrides: stop / irritation
        if c.stop_requested:
            self._close(ClosedReason.STOP_REQUESTED)
            return
        if c.irritated:
            self._close(ClosedReason.IRRITATED)
            return

        # ---- state-specific transitions, cascading over already-answered checkpoints
        while not self.closed:
            before = self.state
            self._step(c)
            if self.state == before or self.state not in CHECKPOINT_ORDER:
                break

        # Re-answer questions raised while transitioning.
        self._answer_question(c)

    def _step(self, c: Classification) -> None:
        # A caller question is answered in place; the flow must NOT advance.
        if c.question_topic:
            return
        if self.state == "greeting":
            self._advance_greeting(c)
        elif self.state == "intent":
            self._advance_intent(c)
        elif self.state == "geography":
            self._advance_geography(c)
        elif self.state == "budget":
            self._advance_budget(c)
        elif self.state == "timeline":
            self._advance_timeline(c)
        elif self.state == "pitch":
            self._advance_pitch(c)
        elif self.state == "cta":
            self._advance_cta(c)
        # done: no further transitions

    def _advance_greeting(self, c: Classification) -> None:
        if c.permission_granted is True:
            self.state = "intent"
        elif c.permission_granted is False:
            self._close(ClosedReason.PERMISSION_REFUSED)
        # None (question asked / ambiguous) -> stay in greeting, re-ask permission.

    def _advance_intent(self, c: Classification) -> None:
        if self.lead.intent is not None:
            self.state = "geography"

    def _advance_geography(self, c: Classification) -> None:
        val = self.lead.geography_comfortable if self.lead.geography_comfortable is not None else c.geography_comfortable
        if val is True:
            self.lead.geography_comfortable = True
            self.state = "budget"
            self._reask_count = 0
        elif val is False:
            if self._reask_count == 0:
                self._reask_count = 1
                self.lead.notes.append("location concern (Nandi corridor)")
            else:
                self.lead.geography_comfortable = False
                self._close(ClosedReason.LOCATION_MISMATCH)

    def _advance_budget(self, c: Classification) -> None:
        val = self.lead.budget_fit if self.lead.budget_fit is not None else c.budget_fit
        if val is True:
            self.lead.budget_fit = True
            self.state = "timeline"
            self._reask_count = 0
        elif val is False:
            if self._reask_count == 0:
                self._reask_count = 1
                self.lead.notes.append("budget concern")
            else:
                self.lead.budget_fit = False
                self._close(ClosedReason.BUDGET_MISMATCH)

    def _advance_timeline(self, c: Classification) -> None:
        val = self.lead.timeline_ok if self.lead.timeline_ok is not None else c.timeline_ok
        if val is False:
            self.lead.timeline_ok = False
            self.lead.notes.append("timeline concern (Dec 2029 possession)")
        elif val is True:
            self.lead.timeline_ok = True
        # Either way we proceed to the pitch (timeline concern is flagged, not fatal).
        if val is not None:
            self.state = "pitch"
            self._pitch_delivered = True  # pitch text is delivered in this turn's reply

    def _advance_pitch(self, c: Classification) -> None:
        # The caller has heard the pitch; move to the CTA.
        self.state = "cta"

    def _advance_cta(self, c: Classification) -> None:
        if c.contact_phone or c.contact_name:
            self.state = "done"
            return
        # Caller declined the follow-up -> close politely.
        if c.permission_granted is False or c.stop_requested:
            self.state = "done"
            self.lead.notes.append("declined follow-up")
            return
        # Otherwise we stay in "cta" and (re-)ask for contact details.

    def expected_question(self) -> Optional[str]:
        """The question the bot should ask in the current state."""
        return STATE_QUESTIONS.get(self.state)

    def needs_reask(self) -> bool:
        """True when the machine is waiting for a second confirmation on a check."""
        return self.state in ("geography", "budget") and self._reask_count == 1

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "closed": self.closed,
            "closed_reason": self.closed_reason,
            "expected_question": self.expected_question(),
            "needs_reask": self.needs_reask(),
            "answered_now": sorted(self._answered_now),
            "lead": self.lead.summary(),
        }


def demo_profile() -> LeadProfile:
    """A fully-qualified profile, useful for tests and demo mode."""
    return LeadProfile(
        intent="self_use",
        geography_comfortable=True,
        budget_fit=True,
        timeline_ok=True,
        name="Rahul",
        language="en",
    )
