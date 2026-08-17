"""Playwright E2E tests for the WOW voice-agent demo UI.

The suite is self-contained: it starts its own backend on port 8003 with the
LLM key disabled (deterministic offline fallback engine), so the tests are
repeatable regardless of what the live demo server (8001, Groq) is doing.

Run:  .venv/bin/python -m pytest backend/tests/e2e -q
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

ROOT = Path(__file__).resolve().parents[3]
BASE_URL = os.environ.get("WOW_E2E_BASE_URL", "http://localhost:8003")
E2E_PORT = 8003


def _ensure_server() -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as r:
            if r.status == 200:
                return
    except Exception:
        pass
    env = dict(os.environ)
    env["GROQ_API_KEY"] = ""            # deterministic fallback engine
    cmd = [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", str(E2E_PORT)]
    log = open("/tmp/opencode/uvicorn_e2e.log", "wb")
    subprocess.Popen(
        cmd, cwd=str(ROOT / "backend"),
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True, env=env,
    )
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("e2e backend failed to start")


@pytest.fixture(scope="session", autouse=True)
def _e2e_backend():
    _ensure_server()
    yield


@pytest.fixture()
def app(page: Page):
    page.set_default_timeout(10_000)
    page.goto(BASE_URL)
    return page


def _agent_count(p: Page) -> int:
    return p.locator("#transcript .msg.agent").count()


def start_call(p: Page) -> int:
    p.click("#startBtn")
    expect(p.locator("#transcript .msg.agent").first).to_contain_text("Divyasree")
    return _agent_count(p)


def say(p: Page, text: str) -> None:
    before = _agent_count(p)
    p.fill("#textInput", text)
    p.click("#sendBtn")
    p.wait_for_function(
        f"document.querySelectorAll('#transcript .msg.agent').length > {before}",
        timeout=10_000,
    )
    p.wait_for_function("!document.querySelector('.typing')", timeout=10_000)


def last_agent(p: Page) -> str:
    return p.locator("#transcript .msg.agent").last.inner_text()


def lead_row(p: Page, label: str) -> str:
    return p.locator(".lead .row", has_text=label).locator("b").inner_text()


def test_full_qualified_journey(app: Page):
    start_call(app)

    say(app, "Yes, please go ahead")
    say(app, "It's for my own weekend home")
    say(app, "Yes, comfortable with the corridor")
    say(app, "Budget is around 2 crore")
    assert lead_row(app, "Budget") == "yes"
    say(app, "2029 works for me")
    assert lead_row(app, "Timeline") == "yes"
    assert lead_row(app, "Qualified") == "YES ✓"

    say(app, "That sounds lovely")
    say(app, "My name is Rahul, 9876543210, evening is fine")
    expect(app.locator("#callState")).to_contain_text("Call completed")
    assert lead_row(app, "Name") == "Rahul"
    assert lead_row(app, "Phone") == "9876543210"
    assert lead_row(app, "Qualified") == "YES ✓"


def test_budget_mismatch_ends_call(app: Page):
    start_call(app)
    say(app, "Go ahead")
    say(app, "For investment")
    say(app, "Yes fine")
    say(app, "Too expensive for me")
    say(app, "I can't afford more than 70 lakh")
    expect(app.locator("#callState")).to_contain_text("Call ended")
    assert "budget" in last_agent(app).lower() or "reach out" in last_agent(app).lower()


def test_permission_refused_ends_politely(app: Page):
    start_call(app)
    say(app, "No, I'm not interested")
    expect(app.locator("#callState")).to_contain_text("Call ended")
    assert re.search(r"apologis|sorry|wonderful day", last_agent(app), re.IGNORECASE)


def test_hindi_journey(app: Page):
    start_call(app)
    say(app, "Ji, bol sakte hain")
    say(app, "Apne ghar ke liye")
    say(app, "Haan, theek hai")
    say(app, "Haan, budget theek hai")
    say(app, "2029 theek hai")
    assert lead_row(app, "Qualified") == "YES ✓"
    assert lead_row(app, "Language") != "en"


def test_system_prompt_pdf_download(app: Page):
    with app.expect_download() as dl_info:
        app.click('a.link:has-text("System Prompt")')
    download = dl_info.value
    assert download.suggested_filename.endswith(".pdf")
    path = download.path()
    with open(path, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_call_flow_checklist_updates(app: Page):
    start_call(app)
    say(app, "Yes please")
    expect(app.locator("#flow li[data-state='intent']")).to_have_class(re.compile(r"active"))
    say(app, "For my weekend home")
    expect(app.locator("#flow li[data-state='intent']")).to_have_class(re.compile(r"done"))
    expect(app.locator("#flow li[data-state='geography']")).to_have_class(re.compile(r"active"))