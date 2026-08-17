"""Automated persona demo generator: 5 real-world use cases, one agent.

Same female agent (Meera) every time; the client persona changes per demo
(adult female, NRI adult male, senior citizen female, young adult male,
budget-mismatch close). Every demo follows the project requirements flow:

    greeting + permission -> intent -> geography -> budget -> timeline
    -> pitch (incl. answering the caller's question from the knowledge base)
    -> CTA -> done (or graceful close for the edge-case demo)

Each demo is driven through the REAL browser UI twice:
    pass 1: transcript capture + journey assertions (states, lead, console)
    pass 2: video recording paced to the audio, muxed with the exact audio
            of pass 1 (fallback provider => replies are deterministic, so the
            audio always matches the video).
Deliverables per demo (demo_audio/persona_N_<slug>/..):
    persona_N_<slug>.mp4            <- submission-ready video (h264 + aac)
    persona_N_<slug>.m4a            <- conversation audio only
    persona_N_<slug>_transcript.txt <- full transcript
    studio/ screenshots + video clips

Voices + realism:
    agent : Meera, always the same female voice (neural edge-tts when reachable,
            otherwise a neural piper voice - never robotic gTTS)
    caller: male personas -> piper "ryan-high" (male), female -> "lessac-high";
            Hinglish scenarios -> gTTS Hindi voice
    pacing: human-like variable gaps (thinking beats, prompt replies, a pause
            before the pitch) plus expressiveness flags (noise/length scale,
            sentence-level pauses)

Usage:
    .venv/bin/python scripts/run_persona_demos.py --only 1
    .venv/bin/python scripts/run_persona_demos.py            # all five
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo_audio"
BASE_URL = "http://localhost:8002"          # demo server (fallback provider => deterministic)
PIPER_DIR = Path("/tmp/opencode/piper_voices")

CALLER_VOICES = {
    "male": PIPER_DIR / "en_US-ryan-high.onnx",
    "female": PIPER_DIR / "en_US-lessac-high.onnx",
    # "hi": caller speaks Hinglish -> gTTS Hindi voice (natural for Hinglish)
}
AGENT_VOICE = PIPER_DIR / "en_US-lessac-high.onnx"   # fallback when edge-tts is unreachable

# Human-like gap table (fixed, deterministic):
#   caller -> agent : agent responds promptly
#   agent -> caller : caller takes a moment to think
#   before pitch    : a beat, then the pitch lands
#   before closing  : a softer beat
PIPER_FLAGS = ["--length-scale", "1.02", "--noise-scale", "0.8", "--sentence-silence", "0.28"]


def _gap_before(transcript: list[dict], i: int) -> float:
    if i == 0:
        return 0.0
    turn = transcript[i]
    if turn["role"] == "caller":
        return 0.6
    if "more than a plot" in turn["text"]:
        return 0.85
    if turn["text"].startswith("Thank you so much") or turn["text"].startswith("I understand"):
        return 0.6
    return 0.35

SCENARIOS = [
    {
        "id": 1,
        "slug": "persona_1_kavitha_weekend_home",
        "title": "Kavitha (adult female, 42) - weekend home for the family",
        "caller": "KAVITHA (caller)",
        "caller_voice": "female",
        "caller_lines": [
            "Yes, please go ahead.",
            "It's for my family. We want a weekend home where the kids can enjoy the open space.",
            "Yes, I'm very comfortable. We already drive up to Nandi Hills sometimes.",
            "Around 1.5 crore should be fine for us.",
            "2029 is okay with us, we're in no hurry.",
            "That sounds lovely. Could you tell me more about the clubhouse and the amenities?",
            "That's wonderful. Please go ahead and schedule the call.",
            "My name is Kavitha Reddy, you can call me at 98450 12345, and Saturday mornings are best.",
        ],
        "expected_states": [
            "greeting", "intent", "geography", "budget", "timeline",
            "pitch", "pitch", "cta", None,
        ],
        "final_state": "Call completed — follow-up scheduled",
        "qualified": "YES ✓",
        "lead_contains": ["Kavitha", "9845012345", "morning"],
    },
    {
        "id": 2,
        "slug": "persona_2_rahul_nri_investment",
        "title": "Rahul (adult male, 38, NRI in Singapore) - investment",
        "caller": "RAHUL (caller)",
        "caller_voice": "male",
        "caller_lines": [
            "Yes, you may speak.",
            "This is purely for investment. I want good long-term appreciation.",
            "Yes, the corridor works well for me. It's close to the new airport road.",
            "My budget is around 2.5 crore.",
            "2029 works well for an investment horizon.",
            "Sounds good. Is the project RERA registered? And how is the developer's track record?",
            "Yes, please arrange a call for me.",
            "I'm Rahul Menon. You can reach me at 98765 43210, and evenings work best for me.",
        ],
        "expected_states": [
            "greeting", "intent", "geography", "budget", "timeline",
            "pitch", "pitch", "cta", None,
        ],
        "final_state": "Call completed — follow-up scheduled",
        "qualified": "YES ✓",
        "lead_contains": ["Rahul", "9876543210", "evening"],
    },
    {
        "id": 3,
        "slug": "persona_3_shobha_retirement",
        "title": "Shobha (senior citizen female, 67, retired teacher) - peaceful retirement home - Hinglish",
        "caller": "SHOBHA (caller)",
        "caller_voice": "hi",
        "caller_lines": [
            "Haan ji, bilkul. Aap bataiye.",
            "Main apni retirement ke liye ek shaant jagah dhoondh rahi hoon. Peace aur greenery chahiye.",
            "Haan ji, main comfortable hoon. Mera beta Devanahalli mein rehta hai.",
            "Mera budget ek crore ke around hai.",
            "2029 theek hai, mere beta sab dekh lenge.",
            "Bahut peaceful lag raha hai. Location convenient hai kya - paas mein shops aur hospitals hain?",
            "Haan ji, kripya kisi ko call karne ko bolo.",
            "Mera naam Shobha Rao hai, number 99887 76655, aur subah ka time best hai.",
        ],
        "expected_states": [
            "greeting", "intent", "geography", "budget", "timeline",
            "pitch", "pitch", "cta", None,
        ],
        "final_state": "Call completed — follow-up scheduled",
        "qualified": "YES ✓",
        "lead_contains": ["Shobha", "9988776655", "morning"],
    },
    {
        "id": 4,
        "slug": "persona_4_arjun_first_plot",
        "title": "Arjun (adult male, 31, tech professional) - first plot, future home + investment - Hinglish",
        "caller": "ARJUN (caller)",
        "caller_voice": "hi",
        "caller_lines": [
            "Haan bhai, aage badhiye.",
            "Main apna pehla plot kharid raha hoon. Future home bhi aur investment bhi.",
            "Haan, easy hai. Whitefield se Devanahalli ab bahut aasaan hai.",
            "Mera budget ek crore around hai. Loan lena hoga.",
            "2029 theek hai, tab tak main aur save kar lunga.",
            "Interesting. Payment plans ya EMI options hain kya?",
            "Haan, that works for me.",
            "Mera naam Arjun Nair hai, number 97400 32211, Sunday afternoons achhe hain.",
        ],
        "expected_states": [
            "greeting", "intent", "geography", "budget", "budget",
            "pitch", "pitch", "cta", None,
        ],
        "final_state": "Call completed — follow-up scheduled",
        "qualified": "YES ✓",
        "lead_contains": ["Arjun", "9740032211", "afternoon"],
    },
    {
        "id": 5,
        "slug": "persona_5_lakshmi_budget_close",
        "title": "Lakshmi (adult female, 55) - budget mismatch, graceful close (edge case) - Hinglish",
        "caller": "LAKSHMI (caller)",
        "caller_voice": "hi",
        "caller_lines": [
            "Haan ji, bataiye.",
            "Humare liye hai. Ek peaceful second home chahiye.",
            "Haan, humein Devanahalli side pasand hai.",
            "92 lakh toh humare budget se bahut zyada hai. Hum sirf 70 lakh tak manage kar sakte hain.",
            "Nahi, chhota wala plot bhi afford nahi ho payega. Sorry ji.",
        ],
        "expected_states": [
            "greeting", "intent", "geography", "budget", "budget", None,
        ],
        "final_state": "Call ended — budget_mismatch",
        "qualified": "no",
        "lead_contains": [],
    },
]


def _ensure_server() -> None:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as r:
            if r.status == 200:
                print("server: already running on 8002")
                return
    except Exception:
        pass
    print("server: starting uvicorn on 8002 (fallback provider, deterministic)")
    env = dict(os.environ)
    env["GROQ_API_KEY"] = ""                # demos must be deterministic
    cmd = [str(ROOT / ".venv/bin/uvicorn"), "app.main:app", "--port", "8002"]
    log = open("/tmp/opencode/uvicorn_persona.log", "wb")
    subprocess.Popen(
        cmd, cwd=str(ROOT / "backend"),
        stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        start_new_session=True, env=env,
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
    msg = page.locator(f"#transcript .msg.agent >> nth={index}")
    text = msg.inner_text()
    if msg.locator(".meta").count():
        text = text.replace(msg.locator(".meta").inner_text(), "", 1).strip()
    return text


def _drive_browser(browser, scenario: dict, *, record_video: bool, pause_after_reply: float = 0.0):
    """Drive the real UI through the scenario; return (transcript, summary, video)."""
    studio = OUT_DIR / scenario["slug"]
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        record_video_dir=str(studio / "video") if record_video else None,
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
    page.screenshot(path=str(studio / "screens" / f"turn_{len(transcript):02d}_agent.png"))

    for i, line in enumerate(scenario["caller_lines"], start=1):
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
        page.screenshot(path=str(studio / "screens" / f"turn_{len(transcript):02d}_agent.png"))
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


def _probe_duration(media: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _tts_agent(text: str, out: Path) -> None:
    """Meera - always the same female voice. Prefers neural edge-tts; falls back
    to a neural piper voice (never the robotic gTTS voice)."""
    import asyncio
    sys.path.insert(0, str(ROOT / "backend"))
    from app.speech import synthesize
    try:
        data, engine = asyncio.run(synthesize(text))
        if engine == "edge-tts":
            out.write_bytes(data)
            return
    except Exception:
        pass
    _tts_piper(text, out, AGENT_VOICE)


def _tts_piper(text: str, out: Path, model: Path) -> None:
    wav = out.with_suffix(".wav")
    subprocess.run(
        ["piper", "--model", str(model), "--output_file", str(wav), *PIPER_FLAGS],
        input=text.encode(), check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "128k", str(out)],
        check=True, capture_output=True,
    )
    wav.unlink()


def _tts_caller(text: str, out: Path, voice: str) -> None:
    """Caller - gender-matched neural piper voice for English scenarios;
    gTTS Hindi voice for Hinglish scenarios."""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.speech import normalize_for_speech
    text = normalize_for_speech(text)       # phone digits read individually
    if voice == "hi":
        from gtts import gTTS
        gTTS(text=text, lang="hi").save(str(out))
        return
    _tts_piper(text, out, CALLER_VOICES[voice])


def _render_audio(transcript: list[dict], scenario: dict) -> Path:
    studio = OUT_DIR / scenario["slug"]
    clips_dir = studio / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_files: list[str] = []
    durations: list[float] = []
    n = 0
    for turn in transcript:
        n += 1
        clip = clips_dir / f"{n:02d}_{turn['role']}.mp3"
        if turn["role"] == "agent":
            _tts_agent(turn["text"], clip)
        else:
            _tts_caller(turn["text"], clip, scenario["caller_voice"])
        clip_files.append(str(clip))
        durations.append(_probe_duration(clip))
        print(f"  clip {n:02d} [{turn['role']}] {durations[-1]:.1f}s")

    # natural gaps between turns (thinking beats, prompt replies, pitch pause)
    gaps = [_gap_before(transcript, i) for i in range(len(transcript))]
    silence_files: list[Path] = []
    for g in sorted(set(g for g in gaps if g)):
        sf = clips_dir / f"silence_{g}.mp3"
        if not sf.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", str(g), "-q:a", "5", str(sf)],
                check=True, capture_output=True,
            )
        silence_files.append(sf)
    with open(clips_dir / "concat_list.txt", "w") as f:
        for i, c in enumerate(clip_files):
            f.write(f"file '{Path(c).resolve()}'\n")
            if i < len(clip_files) - 1:
                gap = gaps[i + 1]
                if gap:
                    sf = clips_dir / f"silence_{gap}.mp3"
                    f.write(f"file '{sf.resolve()}'\n")
    audio = OUT_DIR / f"{scenario['slug']}.m4a"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips_dir / "concat_list.txt"),
         "-c:a", "aac", "-b:a", "128k", str(audio)],
        check=True, capture_output=True,
    )
    total = _probe_duration(audio)
    print(f"  combined -> {audio} ({total:.1f}s)")
    return audio


def _mux_mp4(video: str, audio: Path, scenario: dict) -> Path:
    out = OUT_DIR / f"{scenario['slug']}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video, "-i", str(audio),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p",
         "-c:a", "copy", "-movflags", "+faststart", str(out)],
        check=True, capture_output=True,
    )
    print(f"  mp4 (h264 + aac) -> {out} ({_probe_duration(out):.1f}s)")
    return out


def _write_transcript(transcript: list[dict], scenario: dict) -> None:
    lines = [
        f"WOW voice agent - persona demo {scenario['id']}/5",
        scenario["title"],
        "Automated browser demo (real UI, Playwright). Agent: Meera (Divyasree).",
        "",
    ]
    for t in transcript:
        who = "MEERA (agent)" if t["role"] == "agent" else scenario["caller"]
        st = f"  [{t['state']}]" if t["state"] else ""
        lines.append(f"{who}{st}\n  {t['text']}\n")
    (OUT_DIR / f"{scenario['slug']}_transcript.txt").write_text("\n".join(lines) + "\n")


def run_scenario(scenario: dict) -> None:
    slug = scenario["slug"]
    print(f"\n===== Demo {scenario['id']}/5: {scenario['title']} =====")
    studio = OUT_DIR / slug
    studio.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(studio / "video", ignore_errors=True)
    shutil.rmtree(studio / "screens", ignore_errors=True)
    shutil.rmtree(studio / "clips", ignore_errors=True)
    (studio / "screens").mkdir(parents=True)
    for f in OUT_DIR.glob(f"{slug}.*"):
        if f.suffix in (".mp4", ".m4a", ".txt"):
            f.unlink()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        print("pass 1: driving the real UI (transcript capture)")
        transcript, summary, _ = _drive_browser(browser, scenario, record_video=False)
        browser.close()

    states = [t["state"] for t in transcript if t["role"] == "agent"]
    assert states == scenario["expected_states"], f"unexpected states: {states}"
    assert summary["final_state"] == scenario["final_state"], summary["final_state"]
    assert summary["qualified"] == scenario["qualified"], summary["qualified"]
    assert not summary["console_errors"], f"console errors: {summary['console_errors']}"
    for needle in scenario["lead_contains"]:
        assert needle in summary["lead_panel"], f"{needle!r} missing from lead panel: {summary['lead_panel']}"
    print(f"  journey verified: {len(states)} agent turns, no console errors")

    print("pass 2: rendering the conversation to audio (agent + persona voice)")
    audio = _render_audio(transcript, scenario)

    print("pass 3: recording the browser video (paced to audio) -> mp4")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        total_audio = _probe_duration(audio)
        n_agent = len([t for t in transcript if t["role"] == "agent"])
        pause = (total_audio / n_agent) * 0.55
        transcript2, summary2, video = _drive_browser(browser, scenario, record_video=True, pause_after_reply=pause)
        browser.close()

    a1 = [t["text"] for t in transcript if t["role"] == "agent"]
    a2 = [t["text"] for t in transcript2 if t["role"] == "agent"]
    assert a1 == a2, "replies differ between runs - audio would not match the video"
    assert not summary2["console_errors"]
    assert video, "no video captured"
    final = _mux_mp4(video, audio, scenario)
    _write_transcript(transcript, scenario)
    print(f"  transcript -> {OUT_DIR / f'{slug}_transcript.txt'}")
    print(f"  DONE demo {scenario['id']}: {final}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=0, help="run only scenario with this id")
    args = ap.parse_args()

    _ensure_server()
    selected = [s for s in SCENARIOS if s["id"] == args.only] if args.only else SCENARIOS
    for scenario in selected:
        run_scenario(scenario)
    print("\nAll requested demos completed.")


if __name__ == "__main__":
    main()