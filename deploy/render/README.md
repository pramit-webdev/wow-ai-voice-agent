# Deploying to Render (free tier)

Free plan: 750 compute hours/month, spins down after 15 min idle
(spins back up on the next request, ~1 min), free `*.onrender.com`
subdomain with TLS. No payment card required for free services.

## Prerequisites

1. A GitHub (or GitLab) account — free, the code must live in a repo.
2. A Render account — https://dashboard.render.com/register (Sign up with
   GitHub is the fastest).

## Option A — fully automatic (I do it, needs two tokens)

1. Create a **GitHub token** (repo scope) at https://github.com/settings/tokens
2. Create a **Render API key** at https://dashboard.render.com/api-keys
3. Paste both here. I will:
   - create a public `wow-ai-voice-agent` repo,
   - push this repository (secrets excluded by `.gitignore`),
   - create the Render web service from `deploy/render/render.yaml` via the
     Render API with `plan: free`.

## Option B — manual (about 10 minutes)

1. Push this repo to GitHub (`render.yaml` is already at the repo root).
2. On Render: **New → Blueprint** → connect the repo → Render finds
   `render.yaml` at the root → **Apply**.
3. When prompted, set the secret `GROQ_API_KEY` (your key from
   https://console.groq.com — keep it secret; it is never committed).
   Without it the app runs the deterministic offline fallback engine.
4. After deploy, open `https://wow-ai-voice-agent.onrender.com` (your exact
   subdomain is shown in the dashboard). First load may take ~1 min.

## Notes

- Local filesystem is ephemeral: TTS cache and in-memory sessions reset on
  spin-down — fine for a demo (each call is a fresh session anyway).
- Free services consume included outbound bandwidth (5 GB/month on the free
  Hobby plan) — plenty for this demo; TTS/STT audio is a few KB per reply.
