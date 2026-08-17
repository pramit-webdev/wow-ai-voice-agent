"""Unit tests for the conversation state machine."""

from app.conversation.state import Classification, ConversationStateMachine


def _cls(**kw) -> Classification:
    kw.setdefault("source_text", "")
    return Classification(**kw)


def _drive(machine, c: Classification):
    machine.advance(c)
    return machine


def test_full_qualification_flow():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True))
    assert m.state == "intent"
    _drive(m, _cls(intent="self_use"))
    assert m.state == "geography"
    _drive(m, _cls(geography_comfortable=True))
    assert m.state == "budget"
    _drive(m, _cls(budget_fit=True))
    assert m.state == "timeline"
    _drive(m, _cls(timeline_ok=True))
    assert m.state == "pitch"
    assert m.lead.qualified
    _drive(m, _cls())
    assert m.state == "cta"
    _drive(m, _cls(contact_name="Rahul", contact_phone="9876543210"))
    assert m.state == "done"
    assert m.lead.name == "Rahul"
    assert m.lead.qualified


def test_early_answers_cascade_to_pitch():
    m = ConversationStateMachine()
    _drive(
        m,
        _cls(
            permission_granted=True,
            intent="investment",
            geography_comfortable=True,
            budget_fit=True,
            timeline_ok=True,
        ),
    )
    assert m.state == "pitch"
    assert m.lead.qualified


def test_permission_refused_closes():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=False))
    assert m.closed
    assert m.closed_reason == "permission_refused"


def test_location_mismatch_closes_after_reask():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="self_use"))
    _drive(m, _cls(geography_comfortable=False))
    assert m.state == "geography"
    assert m.needs_reask()
    _drive(m, _cls(geography_comfortable=False))
    assert m.closed
    assert m.closed_reason == "location_mismatch"


def test_budget_mismatch_closes_after_reask():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="self_use"))
    _drive(m, _cls(geography_comfortable=True))
    _drive(m, _cls(budget_fit=False))
    assert m.state == "budget"
    assert m.needs_reask()
    _drive(m, _cls(budget_fit=False))
    assert m.closed
    assert m.closed_reason == "budget_mismatch"


def test_timeline_concern_is_flagged_not_fatal():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="self_use"))
    _drive(m, _cls(geography_comfortable=True))
    _drive(m, _cls(budget_fit=True))
    _drive(m, _cls(timeline_ok=False))
    assert m.state == "pitch"
    assert m.lead.timeline_ok is False
    assert any("timeline" in n for n in m.lead.notes)
    assert not m.lead.qualified


def test_stop_request_closes():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, stop_requested=True))
    assert m.closed
    assert m.closed_reason == "stop_requested"


def test_irritated_user_closes():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="both", irritated=True))
    assert m.closed
    assert m.closed_reason == "irritated"


def test_question_does_not_advance():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True))
    assert m.state == "intent"
    _drive(m, _cls(question_topic="price"))
    assert m.state == "intent"  # stayed put; question answered in-reply


def test_question_in_pitch_does_not_advance():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="both"))
    _drive(m, _cls(geography_comfortable=True))
    _drive(m, _cls(budget_fit=True))
    _drive(m, _cls(timeline_ok=True))
    assert m.state == "pitch"
    _drive(m, _cls(question_topic="price"))
    assert m.state == "pitch", "a pitch-stage question must not skip to the CTA"
    _drive(m, _cls(permission_granted=True))
    assert m.state == "cta"


def test_contact_captured_anytime():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, contact_name="Priya", contact_phone="9988776655"))
    assert m.lead.name == "Priya"
    assert m.lead.phone == "9988776655"


def test_cta_decline_closes_politely():
    m = ConversationStateMachine()
    _drive(m, _cls(permission_granted=True, intent="self_use"))
    _drive(m, _cls(geography_comfortable=True))
    _drive(m, _cls(budget_fit=True))
    _drive(m, _cls(timeline_ok=True))
    _drive(m, _cls())
    assert m.state == "cta"
    _drive(m, _cls(permission_granted=False))
    assert m.state == "done"
    assert any("declined" in n for n in m.lead.notes)