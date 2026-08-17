"""Automated end-to-end browser demo of the WOW voice agent with a real-world
case study, rendered into a single MP3 recording (plus a video with sound).

Case study scenario (real-world):
    Sanjay Kumar - NRI, 14 years in Dubai. Wants a weekend home that also
    works as an investment. Parents live in Devanahalli, so the Nandi Hills
    corridor is familiar. Budget Rs 2.5-3 Cr. Fine with Dec 2029 possession.
    Asks a detailed question during the pitch (returns / price negotiation),
    then accepts a follow-up call with a Property Expert.

What this script does:
    1. Ensures the app is running (starts it if needed).
    2. Drives the REAL browser UI (Playwright) through the journey in text
       mode, asserting every state transition and capturing the live
       transcript.
    3. Renders the exact captured conversation to speech (gTTS) and combines
       it into ONE MP3: demo_audio/case_study_sanjay_nri_investor.mp3.
    4. Re-records the same journey as browser video paced to the audio and
       muxes the MP3 into it: demo_audio/case_study_sanjay_nri_investor.webm.
    5. Writes a full transcript and per-turn screenshots as evidence.

Usage:
    .venv/bin/python scripts/run_case_study_demo.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo_audio"
STUDIO = OUT_DIR / "case_study_sanjay_nri_investor"
BASE_URL = "http://localhost:8001"

CALLER_LINES = [
    "Yes please, go ahead.",
    "I'm looking for a weekend home, but also as an investment for the future.",
    "Yes, I know the Nandi Hills area well - my parents live in Devanahalli, so I'm very comfortable.",
    "Around 2.5 to 3 crore is fine with me.",
    "2029 is fine - I'm in no hurry since I'm based in Dubai.",
    "That sounds nice. What would the returns be like if I don't build immediately, and is the price negotiable?",
    "Sounds good, go ahead.",
    "My name is Sanjay Kumar, you can reach me at 98111 22334, and evenings after 8 PM IST work best.",
]

EXPECTED_STATES = [
    "greeting", "intent", "geography", "budget", "timeline",
    "pitch", "pitch", "cta", None,  # None = call completed, all steps done
]


def _ensure_server() -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as r:
            if r.status == 200:
                print("server: already running on 8001")
                return
    except Exception:
        pass
    print("server: starting uvicorn on 8001 ...")
    cmd = [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", "8001"]
    log = open("/tmp/opencode/uvicorn_case_study.log", "wb")
    subprocess.Popen(
        cmd, cwd=str(ROOT / "backend"),
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as r:
                if r.status == 200:
                    print("server: up")
                    return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server failed to start")


def _active_state(page) -> str | None:
    if page.locator("#flow li.active").count():
        return page.locator("#flow li.active").first.get_attribute("data-state")
    return None


def _agent_text(page, index: int) -> str:
    """Read agent message text, excluding the 'Meera · Divyasree' meta label."""
    msg = page.locator(f"#transcript .msg.agent >> nth={index}")
    text = msg.inner_text()
    if msg.locator(".meta").count():
        text = text.replace(msg.locator(".meta").inner_text(), "", 1).strip()
    return text


def _drive_browser(browser, *, record_video: bool, pause_after_reply: float = 0.0):
    """Drive the real UI through the case study; return the live transcript.

    transcript: list of {"role", "text", "state"}
    """
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        record_video_dir=str(STUDIO / "video") if record_video else None,
    )
    page = ctx.new_page()
    console_errors: list[str] = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))

    page.goto(BASE_URL)
    page.wait_for_selector("#startBtn")
    page.click("#startBtn")
    page.wait_for_selector("#transcript .msg.agent")

    transcript: list[dict] = []
    transcript.append({"role": "agent", "text": _agent_text(page, 0), "state": _active_state(page)})
    page.screenshot(path=str(STUDIO / "screens" / f"turn_{len(transcript):02d}_agent.png"))

    for i, line in enumerate(CALLER_LINES, start=1):
        if pause_after_reply:
            time.sleep(pause_after_reply)
        page.fill("#textInput", line)
        page.click("#sendBtn")
        expected = len([t for t in transcript if t["role"] == "agent"]) + 1
        page.wait_for_function(
            f"document.querySelectorAll('#transcript .msg.agent').length >= {expected}",
            timeout=15000,
        )
        page.wait_for_function("!document.querySelector('.typing')")
        reply = _agent_text(page, expected - 1)
        transcript.append({"role": "caller", "text": line, "state": None})
        transcript.append({"role": "agent", "text": reply, "state": _active_state(page)})
        page.screenshot(path=str(STUDIO / "screens" / f"turn_{len(transcript):02d}_agent.png"))
        print(f"  turn {i:02d}: [{_active_state(page)}] {reply[:70]}...")

    final_state = page.locator("#callState").inner_text()
    qualified = page.locator(".lead .qualified").inner_text() if page.locator(".lead .qualified").count() else ""
    summary = {
        "final_state": final_state,
        "qualified": qualified,
        "console_errors": console_errors,
        "lead_panel": page.locator(".lead").inner_text() if page.locator(".lead").count() else "",
    }
    video = None
    if record_video:
        page.wait_for_timeout(1500)
        video = page.video.path() if page.video else None
    page.close()
    ctx.close()
    return transcript, summary, video


def _probe_duration(mp3: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _tts(text: str, out: Path) -> None:
    from gtts import gTTS
    gTTS(text=text, lang="en", tld="co.in").save(str(out))


def _render_audio(transcript: list[dict]) -> Path:
    clips_dir = STUDIO / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_files: list[str] = []
    durations: list[float] = []
    n = 0
    for turn in transcript:
        n += 1
        clip = clips_dir / f"{n:02d}_{turn['role']}.mp3"
        _tts(turn["text"], clip)
        clip_files.append(str(clip))
        durations.append(_probe_duration(clip))
        print(f"  clip {n:02d} [{turn['role']}] {durations[-1]:.1f}s")
    # interleave 0.45s silence between clips
    silence = clips_dir / "silence.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", "0.45", "-q:a", "5", str(silence)],
        check=True, capture_output=True,
    )
    with open(clips_dir / "concat_list.txt", "w") as f:
        for i, c in enumerate(clip_files):
            f.write(f"file '{Path(c).resolve()}'\n")
            if i < len(clip_files) - 1:
                f.write(f"file '{silence.resolve()}'\n")
    combined = OUT_DIR / "case_study_sanjay_nri_investor.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips_dir / "concat_list.txt"),
         "-c:a", "libmp3lame", "-b:a", "128k", str(combined)],
        check=True, capture_output=True,
    )
    total = _probe_duration(combined)
    print(f"  combined -> {combined} ({total:.1f}s)")
    return combined


def _mux_video(video: str, audio: Path) -> Path:
    out = OUT_DIR / "case_study_sanjay_nri_investor.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "libopus", str(out)],
        check=True, capture_output=True,
    )
    print(f"  video with audio -> {out}")
    return out


def _write_transcript(transcript: list[dict]) -> None:
    lines = [
        "Case study - Sanjay Kumar (NRI, Dubai) - automated browser demo",
        "Rendered from the live UI transcript (Playwright).",
        "",
    ]
    for t in transcript:
        who = "MEERA (agent)" if t["role"] == "agent" else "SANJAY (caller)"
        st = f"  [{t['state']}]" if t["state"] else ""
        lines.append(f"{who}{st}\n  {t['text']}\n")
    (OUT_DIR / "case_study_transcript.txt").write_text("\n".join(lines) + "\n")


def main() -> None:
    STUDIO.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(STUDIO / "video", ignore_errors=True)
    shutil.rmtree(STUDIO / "screens", ignore_errors=True)
    (STUDIO / "screens").mkdir(parents=True)
    for f in OUT_DIR.glob("case_study_*"):
        if f.suffix in (".mp3", ".webm"):
            f.unlink()

    _ensure_server()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        print("pass 1: driving the real UI (transcript capture)")
        transcript, summary, _ = _drive_browser(browser, record_video=False)
        browser.close()

    # ---- verify the journey matches the expected states
    states = [t["state"] for t in transcript if t["role"] == "agent"]
    assert states == EXPECTED_STATES, f"unexpected states: {states}"
    assert summary["final_state"] == "Call completed — follow-up scheduled", summary["final_state"]
    assert summary["qualified"] == "YES ✓", "lead must be qualified"
    assert not summary["console_errors"], f"console errors: {summary['console_errors']}"
    assert "Sanjay" in summary["lead_panel"] and "9811122334" in summary["lead_panel"]
    assert "evening" in summary["lead_panel"] or "8 PM" in summary["lead_panel"]
    print(f"  journey verified: {len(states)} agent turns, lead qualified, no console errors")

    # ---- render the exact conversation to one MP3
    print("pass 2: rendering the conversation to a single MP3")
    audio = _render_audio(transcript)

    # ---- re-drive with video, paced to the audio
    print("pass 3: recording the browser video (paced to audio)")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        total_audio = _probe_duration(audio)
        n_agent = len([t for t in transcript if t["role"] == "agent"])
        pause = (total_audio / n_agent) * 0.55  # per-turn pacing so video ~ audio
        transcript2, summary2, video = _drive_browser(browser, record_video=True, pause_after_reply=pause)
        browser.close()

    a1 = [t["text"] for t in transcript if t["role"] == "agent"]
    a2 = [t["text"] for t in transcript2 if t["role"] == "agent"]
    assert a1 == a2, "replies differ between runs - audio would not match the video"
    assert not summary2["console_errors"]
    assert video, "no video captured"
    final_video = _mux_video(video, audio)

    _write_transcript(transcript)
    print(f"\nDone.")
    print(f"  MP3 (conversation):  {audio}")
    print(f"  Video (UI + audio):  {final_video}")
    print(f"  Transcript:          {OUT_DIR / 'case_study_transcript.txt'}")
    print(f"  Screenshots:         {STUDIO / 'screens'}")


if __name__ == "__main__":
    main()