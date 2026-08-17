/* WOW AI Voice Agent demo frontend.
   Voice uses the free Web Speech API (browser speech recognition + synthesis);
   text mode works everywhere, including automated E2E tests. */

const $ = (id) => document.getElementById(id);

const state = {
  sessionId: null,
  started: false,
  voiceOn: false,
  listening: false,
  awaitingReply: false,
  recognition: null,
  lastTranscript: "",
  mediaRecorder: null,
  mediaStream: null,
  mediaChunks: [],
  recTimeout: null,
};

const els = {
  avatar: $("avatar"), callState: $("callState"), startBtn: $("startBtn"),
  modeBtn: $("modeBtn"), micBtn: $("micBtn"), transcript: $("transcript"),
  emptyState: $("emptyState"), textInput: $("textInput"), sendBtn: $("sendBtn"),
  micStatus: $("micStatus"), flow: $("flow"), lead: $("lead"),
  providerBadge: $("providerBadge"),
};

const FLOW_STATES = ["greeting", "intent", "geography", "budget", "timeline", "pitch", "cta"];

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return resp.json();
}

async function startCall() {
  try {
    els.startBtn.disabled = true;
    els.sendBtn.disabled = false;
    els.textInput.disabled = false;
    els.micBtn.disabled = false;
    els.emptyState.style.display = "none";
    els.callState.textContent = "Call in progress…";
    const turn = await api("/api/v1/conversation/start", { method: "POST" });
    state.sessionId = turn.session_id;
    state.started = true;
    setProvider(turn.provider);
    appendMsg("agent", turn.reply);
    updatePanel(turn);
    await speak(turn.reply, turn.reply_language);
    if (state.voiceOn) await listenOnce();
  } catch (err) {
    appendMsg("agent", "⚠ Demo error: " + err.message);
    els.callState.textContent = "Failed to start call";
    els.startBtn.disabled = false;
  }
}

async function sendMessage(text) {
  if (!state.sessionId || state.awaitingReply) return;
  state.awaitingReply = true;
  appendMsg("user", text);
  const typing = appendTyping();
  try {
    const turn = await api(`/api/v1/conversation/${state.sessionId}/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    setProvider(turn.provider);
    typing.remove();
    appendMsg("agent", turn.reply);
    updatePanel(turn);
    if (turn.closed) {
      els.callState.textContent = "Call ended — " + (turn.closed_reason || "closed");
      els.startBtn.disabled = false;
      els.micBtn.disabled = true;
      state.awaitingReply = false;
      return;
    }
    els.callState.textContent = turn.state === "done"
      ? "Call completed — follow-up scheduled"
      : "Call in progress…";
    await speak(turn.reply, turn.reply_language);
    if (state.voiceOn) await listenOnce();
  } catch (err) {
    typing.remove();
    appendMsg("agent", "⚠ Demo error: " + err.message);
  } finally {
    state.awaitingReply = false;
  }
}

function appendMsg(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = role === "agent" ? "Meera · Divyasree" : "You";
  div.appendChild(meta);
  div.appendChild(document.createTextNode(text));
  els.transcript.appendChild(div);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return div;
}

function appendTyping() {
  const div = document.createElement("div");
  div.className = "typing";
  div.textContent = "Meera is typing…";
  els.transcript.appendChild(div);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return div;
}

function updatePanel(turn) {
  const finished = turn.closed || turn.state === "done";
  const idx = finished ? FLOW_STATES.length : FLOW_STATES.indexOf(turn.state);
  [...els.flow.children].forEach((li) => {
    const st = li.dataset.state;
    const i = FLOW_STATES.indexOf(st);
    li.classList.toggle("active", i === idx && !turn.closed);
    li.classList.toggle("done", finished || i < idx);
  });
  els.avatar.textContent = turn.state === "done" || turn.closed ? "✓" : "M";
  renderLead(turn);
}

function renderLead(turn) {
  const l = turn.lead;
  if (!l) return;
  const rows = [
    ["Intent", l.intent ? l.intent.replace("_", " ") : "—"],
    ["Geography", yesNo(l.geography_comfortable)],
    ["Budget", yesNo(l.budget_fit)],
    ["Timeline", yesNo(l.timeline_ok)],
    ["Language", l.language],
  ];
  if (l.name) rows.push(["Name", l.name]);
  if (l.phone) rows.push(["Phone", l.phone]);
  if (l.preferred_time) rows.push(["Preferred time", l.preferred_time]);
  const qualified = l.qualified;
  els.lead.innerHTML =
    rows.map(([k, v]) => `<div class="row"><span>${k}</span><b>${v}</b></div>`).join("") +
    `<div class="row"><span>Qualified</span><b class="qualified">${qualified ? "YES ✓" : "no"}</b></div>`;
}

function yesNo(v) {
  if (v === true) return "yes";
  if (v === false) return "no";
  return "—";
}

function setProvider(p) {
  els.providerBadge.textContent = "engine: " + p;
  els.providerBadge.classList.toggle("groq", p === "groq");
  els.providerBadge.classList.toggle("fallback", p !== "groq");
}

/* ---------------------- voice (server speech AI + browser fallback) ------- */

// capabilities from /health: stt = "whisper" | null, tts = "edge-tts" | null
let caps = { stt: null, tts: null };

function speechAvailable() {
  return !!(caps.stt || window.SpeechRecognition || window.webkitSpeechRecognition);
}

const FEMALE_VOICE_HINTS = [
  "female", "swara", "neerja", "heera", "veena", "zira", "samantha",
  "karen", "moira", "tessa", "kalpana", "lekha", "meera", "nita", "ria",
];

function isFemaleVoice(v) {
  const n = v.name.toLowerCase();
  return FEMALE_VOICE_HINTS.some((h) => n.includes(h));
}

function pickVoice(lang) {
  const voices = window.speechSynthesis.getVoices();
  const pref = lang === "hi" ? "hi-IN" : "en-IN";
  return (
    voices.find((v) => v.lang === pref && isFemaleVoice(v)) ||
    voices.find((v) => v.lang === pref) ||
    voices.find((v) => v.lang.startsWith("en") && isFemaleVoice(v)) ||
    voices.find((v) => isFemaleVoice(v)) ||
    voices.find((v) => v.lang === "en-IN") ||
    voices.find((v) => v.lang.startsWith("en")) ||
    voices[0]
  );
}

function browserSpeak(text, language) {
  return new Promise((resolve) => {
    if (!("speechSynthesis" in window)) return resolve();
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    const voice = pickVoice(language === "hi" ? "hi-IN" : "en-IN");
    if (voice) utter.voice = voice;
    utter.rate = 1.02;
    utter.onend = resolve;
    utter.onerror = resolve;
    window.speechSynthesis.speak(utter);
  });
}

function speak(text, language) {
  return new Promise((resolve) => {
    if (!state.voiceOn) return resolve();
    if (caps.tts) {
      const url = "/api/v1/speak?lang=" + (language === "hi" ? "hi" : "en") +
                  "&text=" + encodeURIComponent(text);
      fetch(url)
        .then((r) => { if (!r.ok) throw new Error(); return r.blob(); })
        .then((blob) => {
          const audio = new Audio(URL.createObjectURL(blob));
          audio.onended = () => resolve();
          audio.onerror = () => resolve();
          audio.play().catch(() => resolve());
        })
        .catch(() => browserSpeak(text, language).then(resolve));
      return;
    }
    browserSpeak(text, language).then(resolve);
  });
}

function makeRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SR();
  rec.continuous = false;
  rec.interimResults = false;
  rec.lang = "en-IN";
  rec.onresult = (event) => {
    const text = event.results[0][0].transcript;
    state.lastTranscript = text;
    els.micStatus.textContent = "";
    stopListening();
    sendMessage(text);
  };
  rec.onerror = (event) => {
    els.micStatus.textContent = "Mic error: " + event.error;
    state.listening = false;
    els.micBtn.classList.remove("live");
    els.micBtn.textContent = "🎙";
  };
  rec.onend = () => {
    state.listening = false;
    els.micBtn.classList.remove("live");
    els.micBtn.textContent = "🎙";
    if (state.voiceOn && state.awaitingReply && !state.lastTranscript) {
      setTimeout(() => listenOnce(), 600);
    }
  };
  return rec;
}

function serverSTT() {
  return new Promise((resolve) => {
    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        state.mediaStream = stream;
        const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
        state.mediaRecorder = mr;
        state.mediaChunks = [];
        mr.ondataavailable = (e) => { if (e.data.size) state.mediaChunks.push(e.data); };
        mr.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          state.mediaStream = null;
          state.mediaRecorder = null;
          const blob = new Blob(state.mediaChunks, { type: "audio/webm" });
          state.listening = false;
          els.micBtn.classList.remove("live");
          els.micBtn.textContent = "🎙";
          els.micStatus.classList.remove("live");
          if (blob.size > 1000) {
            const fd = new FormData();
            fd.append("file", blob, "caller.webm");
            try {
              const resp = await fetch("/api/v1/transcribe", { method: "POST", body: fd });
              const data = await resp.json();
              if (data.text && data.text.trim()) {
                els.micStatus.textContent = "";
                sendMessage(data.text.trim());
              } else {
                els.micStatus.textContent = "Nothing heard — please try again.";
              }
            } catch (_) {
              els.micStatus.textContent = "Speech service unavailable — use text mode.";
            }
          } else {
            els.micStatus.textContent = "Nothing heard — please try again.";
          }
          resolve();
        };
        mr.start();
        state.listening = true;
        els.micBtn.classList.add("live");
        els.micBtn.textContent = "🔴";
        els.micStatus.classList.add("live");
        els.micStatus.textContent = "Listening… (click 🎙 to stop)";
        state.recTimeout = setTimeout(() => {
          if (state.mediaRecorder && state.mediaRecorder.state === "recording") {
            state.mediaRecorder.stop();
          }
        }, 8000);
      })
      .catch(() => {
        els.micStatus.textContent = "Microphone unavailable — use text mode.";
        resolve();
      });
  });
}

function startListening() {
  if (!state.voiceOn || state.awaitingReply) return;
  els.micStatus.classList.add("live");
  if (caps.stt) {
    serverSTT();
  } else {
    els.micBtn.classList.add("live");
    els.micBtn.textContent = "🔴";
    els.micStatus.textContent = "Listening…";
    state.lastTranscript = "";
    if (state.recognition) {
      try { state.recognition.stop(); } catch (_) {}
    }
    state.recognition = makeRecognition();
    state.recognition.start();
    state.listening = true;
  }
}

function stopListening() {
  state.lastTranscript = "";
  els.micStatus.classList.remove("live");
  if (state.mediaRecorder) {
    if (state.mediaRecorder.state === "recording") state.mediaRecorder.stop();
    return; // onstop handles the rest
  }
  els.micStatus.textContent = "";
  if (state.recognition) {
    try { state.recognition.stop(); } catch (_) {}
  }
  state.listening = false;
}

async function listenOnce() {
  if (state.awaitingReply) return;
  startListening();
}

function toggleVoice() {
  state.voiceOn = !state.voiceOn;
  els.modeBtn.textContent = "Voice: " + (state.voiceOn ? "on" : "off");
  if (!state.voiceOn) {
    stopListening();
    window.speechSynthesis && window.speechSynthesis.cancel();
  } else if (!speechAvailable()) {
    state.voiceOn = false;
    els.modeBtn.textContent = "Voice: unsupported";
    els.micStatus.textContent = "Speech recognition not supported in this browser — use text mode.";
  }
}

/* --------------------------------- events --------------------------------- */

els.startBtn.addEventListener("click", startCall);
els.sendBtn.addEventListener("click", () => {
  const text = els.textInput.value.trim();
  if (text) { els.textInput.value = ""; sendMessage(text); }
});
els.textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const text = els.textInput.value.trim();
    if (text) { els.textInput.value = ""; sendMessage(text); }
  }
});
els.micBtn.addEventListener("click", () => {
  if (state.listening) stopListening();
  else startListening();
});
els.modeBtn.addEventListener("click", toggleVoice);

window.speechSynthesis && window.speechSynthesis.getVoices(); // warm up
setProvider("loading…");
fetch("/health")
  .then((r) => r.json())
  .then((h) => {
    setProvider(h.provider);
    caps = h.capabilities || caps;
    if (caps.tts && !state.voiceOn) {
      els.micStatus.textContent = "Voice ready: " +
        (caps.stt ? "Whisper STT + neural TTS" : "neural TTS") + " — press Voice: on to speak.";
    }
  })
  .catch(() => setProvider("offline"));
