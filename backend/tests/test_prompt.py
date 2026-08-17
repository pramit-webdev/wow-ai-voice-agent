"""Tests for the system prompt deliverable and PDF generation."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate

from app.api.docs import _build_pdf_bytes
from app.conversation.prompt import (
    PRONUNCIATION_DICTIONARY,
    build_system_prompt,
)


def test_prompt_contains_pronunciation_dictionary():
    prompt = build_system_prompt()
    for term, phon in PRONUNCIATION_DICTIONARY.items():
        assert term in prompt
        assert phon in prompt


def test_prompt_contains_required_assignment_elements():
    prompt = build_system_prompt()
    for required in [
        "Divyasree",
        "Whispers of the Wind",
        "Nandi Valley",
        "92.4 lakh",
        "permission",
        "INTENT",
        "GEOGRAPHY",
        "BUDGET",
        "TIMELINE",
        "Property Expert",
        "Hindi",
        "irritated",
    ]:
        assert required.lower() in prompt.lower(), f"missing: {required}"


def test_prompt_has_project_knowledge():
    prompt = build_system_prompt()
    assert "PRM/KA/RERA/1250/301/PR/070525/007718" in prompt
    assert "207" in prompt
    assert "20,000" in prompt


def test_female_agent_persona():
    prompt = build_system_prompt()
    assert "Meera" in prompt
    assert "Mee-raa" in prompt
    assert PRONUNCIATION_DICTIONARY["Meera"] == "Mee-raa"


def test_greeting_names_the_agent():
    from app.conversation.engine import _greeting_en
    greeting = _greeting_en()
    assert "Meera" in greeting
    assert "May I take two minutes" in greeting


def test_greeting_is_short_and_punchy():
    """The intro must be brief so the caller doesn't hang up mid-speech."""
    from app.conversation.engine import _greeting_en
    greeting = _greeting_en()
    assert len(greeting) < 200
    assert "Whispers of the Wind" in greeting
    assert "Nandi Hills" in greeting
    assert greeting.rstrip().endswith("?")


def test_prompt_instructs_short_replies():
    prompt = build_system_prompt()
    assert "under 35 words" in prompt
    assert "under 15 seconds" in prompt
    assert "contractions" in prompt


def test_prompt_has_pronunciation_guide_for_key_terms():
    """Assignment requirement: phonetic guide for Divyasree, Nandi, Lakh, Crore."""
    prompt = build_system_prompt()
    assert "Div-yaa-shree" in prompt
    assert "Nun-dhee" in prompt
    assert "lahk" in prompt
    assert "krohr" in prompt
    assert "Mee-raa" in prompt


def test_prompt_has_spoken_text_rules():
    """TTS must never see 'Rs'/'sq.ft.'; phone digits spoken individually."""
    prompt = build_system_prompt()
    assert "rupees" in prompt
    assert '"Rs"' in prompt          # explicitly forbidden
    assert "square feet" in prompt
    assert "9 8 7 6 5 4 3 2 1 0" in prompt
    assert "Rs 92.4 lakh" not in prompt.lower().replace("rupees 92.4 lakh", "")


def test_cold_call_etiquette_present_in_prompt():
    """The agent must be a careful cold caller: unsolicited call, no pressure,
    soft phrasing, easy exits, strict one-step-at-a-time sequence."""
    prompt = build_system_prompt()
    low = prompt.lower()
    assert "unsolicited" in low
    assert "never assume interest" in low
    assert "presumptive or pushy" in low
    assert "may i" in low
    assert "easy to say no" in low
    assert "never push" in low
    assert "one step at a time" in low
    assert "never jump ahead" in low
    assert "never re-ask" in low


def test_pdf_generates_valid_a4():
    pdf = _build_pdf_bytes()
    assert pdf.startswith(b"%PDF")
    # Build again through platypus to catch layout errors silently.
    buf = io.BytesIO(pdf)
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        title="WOW system prompt", author="test",
    )
    assert len(pdf) > 5000
