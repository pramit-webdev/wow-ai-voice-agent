"""System prompt deliverable: JSON + generated PDF."""

from __future__ import annotations

import io

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..conversation.prompt import (
    PRONUNCIATION_DICTIONARY,
    build_system_prompt,
)
from ..conversation.project import PROJECT
from ..config import get_settings

router = APIRouter(prefix="/api/v1")


@router.get("/system-prompt")
def system_prompt_json() -> dict:
    return {
        "agent_name": get_settings().agent_name,
        "system_prompt": build_system_prompt(),
        "pronunciation_dictionary": PRONUNCIATION_DICTIONARY,
    }


def _build_pdf_bytes() -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title="WOW AI Voice Agent - System Prompt",
        author="Divyasree Developers",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=20, spaceAfter=4)
    subtitle = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=11, textColor=colors.HexColor("#555555"),
        alignment=TA_CENTER, spaceAfter=10,
    )
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11.5, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, leading=14)
    mono = ParagraphStyle("Mono", parent=body, fontName="Courier", fontSize=7.6, leading=9.6)

    story: list = []
    story.append(Paragraph("Whispers of the Wind (WOW)", title))
    story.append(Paragraph("AI Voice Agent &mdash; System Prompt Deliverable", subtitle))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"<b>Developer:</b> {PROJECT['developer']}<br/>"
            f"<b>Project:</b> {PROJECT['name']}<br/>"
            f"<b>Location:</b> {PROJECT['location']}<br/>"
            f"<b>Pricing:</b> {PROJECT['starting_price']} &ndash; {PROJECT['price_range']}<br/>"
            f"<b>Possession:</b> {PROJECT['possession']}<br/>"
            f"<b>RERA:</b> {PROJECT['rera']}",
            body,
        )
    )

    # ---- Section 1: pronunciation dictionary
    story.append(PageBreak())
    story.append(Paragraph("1. Pronunciation Dictionary (Phonetic Guide)", h1))
    story.append(
        Paragraph(
            "Every project term must be spoken exactly as written below. "
            "This prevents mispronunciations that sound unprofessional on a call.",
            body,
        )
    )
    pron_rows = [[Paragraph("<b>Term</b>", body), Paragraph("<b>Phonetic</b>", body)]]
    for term, phon in PRONUNCIATION_DICTIONARY.items():
        pron_rows.append([Paragraph(term, body), Paragraph(phon, body)])
    pron_table = Table(pron_rows, colWidths=[60 * mm, 95 * mm])
    pron_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(pron_table)

    # ---- Section 2: full system prompt
    story.append(Paragraph("2. Full System Message", h1))
    story.append(
        Paragraph(
            "This is the complete system message used to configure the voice agent "
            "(Groq, free tier, model openai/gpt-oss-120b).",
            body,
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(build_system_prompt().replace("&", "&amp;"), mono))

    # ---- Section 3: architecture summary
    story.append(PageBreak())
    story.append(Paragraph("3. Conversation Architecture", h1))
    steps = [
        ("Step 1 - Introduction", "Professional greeting as a Divyasree consultant; mention project & location; ASK PERMISSION to speak."),
        ("Step 2 - Qualification 1: Intent", "Self-use vs. Investment."),
        ("Step 2 - Qualification 2: Geography", "Comfort with the Nandi Hills / Devanahalli corridor."),
        ("Step 2 - Qualification 3: Budget", "Fitment for the Rs 92.4 lakh+ starting price."),
        ("Step 2 - Qualification 4: Timeline", "Comfort with phased delivery / December 2029 possession."),
        ("Step 3 - The Pitch", "Aspirational 'Private Valley' lifestyle: 74% open space, 20,000 sq.ft. clubhouse, nature, community."),
        ("Step 4 - CTA", "Request a follow-up call with a Property Expert; capture name, phone, preferred time."),
    ]
    flow_rows = [[Paragraph("<b>Step</b>", body), Paragraph("<b>Action</b>", body)]]
    for step, desc in steps:
        flow_rows.append([Paragraph(step, body), Paragraph(desc, body)])
    flow_table = Table(flow_rows, colWidths=[65 * mm, 90 * mm])
    flow_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(flow_table)
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            "<b>Edge-case handling:</b> irritated user, budget-fit-but-location-not-fit, "
            "permission refusal, early answers (never re-ask answered checkpoints), and "
            "multilingual English + Hindi.",
            body,
        )
    )

    doc.build(story)
    return buf.getvalue()


@router.get("/system-prompt.pdf")
def system_prompt_pdf() -> StreamingResponse:
    pdf = _build_pdf_bytes()
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="WOW_AI_Voice_Agent_System_Prompt.pdf"'},
    )
