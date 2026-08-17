# Whispers of the Wind (WOW) — AI Voice Agent

Outbound AI voice agent that qualifies leads for **Divyasree Developers'**
premium villa-plot project **"Whispers of the Wind"** (Nandi Valley, near
Nandi Hills, North Bengaluru).

Built for the assignment: a full-stack demo with a FastAPI backend, an AI
speech stack (Whisper speech recognition + neural TTS — all free), a Groq
free-tier LLM (with a built-in offline fallback engine that needs **no API
key**), a System Prompt PDF deliverable, and recorded demo calls.

## Conversation flow (as required by the assignment)

1. **Introduction** — professional greeting as a Divyasree consultant; project
   + location; always asks permission to speak.
2. **Qualification — the 4 checkpoints**
   - Intent (self-use vs investment)
   - Geography (comfort with the Nandi Hills / Devanahalli corridor)
   - Budget (fitment for ₹92.4 lakh+ starting price)
   - Timeline (comfort with phased delivery / Dec 2029 possession)
3. **The Pitch** — aspirational "Private Valley" lifestyle (74% open space,
   20,000 sq.ft. clubhouse, eco-parks, community).
4. **CTA** — follow-up call with a Property Expert; captures name, phone,
   preferred time.

Edge cases handled: permission refusal, budget-fit-but-not-location (and vice
versa), irritated caller, hang-up, early answers (never re-asks), and
**English + Hindi** conversation. Project facts are real (RERA
`PRM/KA/RERA/1250/301/PR/070525/007718`, 207 plots, ₹7,700/sq.ft base).

## Quick start

```bash
python3 -m virtualenv .venv            # or: python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # optional: add GROQ_API_KEY
.venv/bin/uvicorn app.main:app --port 8001 --app-dir backend
```

Open http://localhost:8001 — press **Start call**, talk or type.

**Voice mode is AI end-to-end:**
- **STT** — your speech is recorded in the browser and transcribed by
  **Groq Whisper** (free tier) when `GROQ_API_KEY` is set; otherwise the
  browser's Web Speech API is used.
- **TTS** — replies are spoken by a **female neural voice**
  (`en-IN-SwaraNeural` / `hi-IN-SwaraNeural` via edge-tts, free; falls back
  to gTTS if Microsoft's endpoint is unreachable). The short, punchy
  greeting is under 15 seconds of speech, and every reply is kept brief so
  callers don't hang up mid-sentence.

> No API key? The app automatically runs on the offline fallback engine —
> everything works, the demo is fully deterministic.

## Free-tier LLM (Groq)

1. Create a free key at https://console.groq.com
2. Put it in `backend/.env`: `GROQ_API_KEY=...`
3. Restart — the UI badge shows `engine: groq`.

Without a key, or if Groq is unreachable, the engine degrades gracefully to
the offline fallback (log shows it per turn).

## Deliverables

| Deliverable | Where |
|---|---|
| Demo link (running bot) | run locally, or deploy to Render free tier (below) |
| Recorded demo calls (5 flows) | `demo_audio/flow_1.mp3` … `flow_5.mp3` (+ per-turn clips in `demo_audio/flow_N/`) |
| Case study call (single MP3) | `demo_audio/case_study_sanjay_nri_investor.mp3` — automated browser demo (NRI investor, full journey incl. a pitch-stage question) |
| Case study browser video | `demo_audio/case_study_sanjay_nri_investor.webm` — real UI session with the conversation audio muxed in |
| System Prompt (PDF) | `docs/WOW_AI_Voice_Agent_System_Prompt.pdf` (also downloadable from the UI) |
| System Prompt (text/JSON) | `GET /api/v1/system-prompt` |

Demo flows: (1) qualified weekend-home buyer, (2) NRI investor, (3) budget
mismatch close, (4) location mismatch close, (5) irritated caller (bilingual).
The case study call is reproduced end-to-end by
`scripts/run_case_study_demo.py` (drives the real UI with Playwright, verifies
every state, renders the captured conversation to one MP3, and records the
browser session with audio).

## API

- `POST /api/v1/conversation/start` — start a call (returns greeting turn)
- `POST /api/v1/conversation/{session_id}/respond` — `{"message": "..."}`
- `GET /api/v1/conversation/{session_id}` — transcript + lead snapshot
- `GET /api/v1/system-prompt` / `GET /api/v1/system-prompt.pdf`
- `GET /api/v1/project` — project knowledge base
- `GET /api/v1/speak?text=...&lang=en|hi` — neural TTS (mp3, cached)
- `POST /api/v1/transcribe` — Whisper STT (multipart audio file)
- `GET /health` — health + active provider + speech capabilities

Interactive docs at http://localhost:8001/docs.

## Tests

```bash
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest                          # unit + API tests
.venv/bin/python -m pytest backend/tests/e2e -q     # browser E2E (server must run)
```

## Deploy free (Render)

1. Push this repo to GitHub.
2. Render → New Web Service (Free). Root dir: `backend`; start command:
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Add `GROQ_API_KEY` as an env var. Deploy → share the `onrender.com` URL.

## Project layout

```
backend/
  app/
    main.py                FastAPI app (serves API + static demo UI)
    config.py              env settings
    conversation/
      state.py             state machine (4 checkpoints, pitch, CTA, closes)
      prompt.py            system prompt + pronunciation dictionary
      project.py           verified project knowledge base + FAQ
      engine.py            provider + state machine orchestration
    llm/
      groq.py              Groq free-tier provider (OpenAI-compatible)
      fallback.py          offline deterministic NLU + reply templates (EN/HI)
    api/                   REST endpoints, system-prompt PDF generator
    static/                demo UI (vanilla JS, Web Speech API voice)
  tests/                   unit, API, Playwright E2E tests
scripts/                   system-prompt PDF + demo audio + case study demo generators
docs/                      System Prompt PDF deliverable
demo_audio/                recorded demo calls (5 flows) + case study MP3/video/transcript
```