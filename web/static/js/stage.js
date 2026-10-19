const stageToken = window.KT_STAGE?.token || "";
const upEl = document.getElementById("stage-up");
const emptyEl = document.getElementById("stage-empty");
const startingEl = document.getElementById("stage-starting");
const startingDetailEl = document.getElementById("stage-starting-detail");
const singerEl = document.getElementById("stage-singer");
const songEl = document.getElementById("stage-song");
const countdownEl = document.getElementById("stage-countdown");
const afterEl = document.getElementById("stage-after");
const afterListEl = document.getElementById("stage-after-list");
const fillerEl = document.getElementById("stage-filler");
const nowPlayingEl = document.getElementById("stage-now-playing");
const nowPlayingTitleEl = document.getElementById("stage-now-playing-title");

const FILLER_VOLUME = 0.6;
let stageState = window.KT_STAGE?.state || null;
let fillerOrder = [];
let fillerTitles = [];
let fillerPosition = 0;
let fadeTimer = null;

function songLine(item) {
  return [item?.song, item?.artist].filter(Boolean).join(" — ");
}

function renderStage(state) {
  stageState = state;
  const phase = state?.state || "IDLE";
  const next = state?.next || null;
  upEl.hidden = !(phase === "INTERMISSION" && next);
  emptyEl.hidden = !(phase === "INTERMISSION" && !next);
  startingEl.hidden = phase !== "STARTING";
  if (next) {
    singerEl.textContent = next.user || "";
    songEl.textContent = songLine(next);
  }
  if (phase === "STARTING") {
    startingDetailEl.textContent = state?.message || "";
  }
  renderCountdown();
  if (phase === "INTERMISSION") {
    startFiller();
  } else {
    fadeOutFiller();
  }
}

function renderCountdown() {
  const endsAt = stageState?.countdown_ends_at;
  if (!endsAt || stageState?.state !== "INTERMISSION" || !stageState?.next) {
    countdownEl.hidden = true;
    return;
  }
  countdownEl.hidden = false;
  const remaining = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
  if (remaining > 0) {
    countdownEl.classList.remove("expired");
    const minutes = Math.floor(remaining / 60);
    const seconds = String(remaining % 60).padStart(2, "0");
    countdownEl.textContent = minutes ? `${minutes}:${seconds}` : String(remaining);
  } else {
    countdownEl.classList.add("expired");
    countdownEl.textContent = `Waiting for ${stageState.next.user || "the next singer"}…`;
  }
}

function renderQueue(payload) {
  const after = Array.isArray(payload?.up_next) ? payload.up_next.slice(1, 4) : [];
  afterListEl.innerHTML = "";
  for (const item of after) {
    const li = document.createElement("li");
    li.textContent = item.user || "";
    afterListEl.appendChild(li);
  }
  afterEl.hidden = after.length === 0;
}

// ----- intermission music -------------------------------------------------------

function shuffle(values) {
  for (let i = values.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [values[i], values[j]] = [values[j], values[i]];
  }
  return values;
}

async function loadFiller() {
  try {
    const res = await fetch(`/stage/filler?token=${encodeURIComponent(stageToken)}`);
    const data = res.ok ? await res.json() : { count: 0 };
    fillerOrder = shuffle(Array.from({ length: data.count || 0 }, (_v, i) => i));
    fillerTitles = Array.isArray(data.titles) ? data.titles : [];
  } catch (_error) {
    fillerOrder = [];
    fillerTitles = [];
  }
}

function playNextFiller() {
  if (!fillerOrder.length) {
    return;
  }
  const index = fillerOrder[fillerPosition % fillerOrder.length];
  fillerPosition += 1;
  nowPlayingTitleEl.textContent = fillerTitles[index] || "";
  fillerEl.src = `/stage/filler/${index}?token=${encodeURIComponent(stageToken)}`;
  fillerEl.play().catch(() => {});
}

function startFiller() {
  if (!fillerOrder.length) {
    return;
  }
  window.clearInterval(fadeTimer);
  fillerEl.volume = FILLER_VOLUME;
  if (!fillerEl.src) {
    playNextFiller();
  } else if (fillerEl.paused) {
    fillerEl.play().catch(() => {});
  }
}

function fadeOutFiller() {
  if (fillerEl.paused) {
    return;
  }
  window.clearInterval(fadeTimer);
  fadeTimer = window.setInterval(() => {
    fillerEl.volume = Math.max(0, fillerEl.volume - 0.05);
    if (fillerEl.volume <= 0) {
      window.clearInterval(fadeTimer);
      fillerEl.pause();
    }
  }, 60);
}

fillerEl.addEventListener("ended", playNextFiller);
// Show the break song's name while it plays; hide it when the music stops for a singer.
fillerEl.addEventListener("playing", () => {
  nowPlayingEl.hidden = !nowPlayingTitleEl.textContent;
});
fillerEl.addEventListener("pause", () => {
  nowPlayingEl.hidden = true;
});
fillerEl.addEventListener("error", () => window.setTimeout(playNextFiller, 1000));

// ----- wiring -------------------------------------------------------------------

async function loadQueue() {
  try {
    const res = await fetch("/api/queue", { headers: { "X-Admin-Token": stageToken } });
    if (res.ok) {
      renderQueue(await res.json());
    }
  } catch (_error) {
  }
}

const socket = io();
socket.on("stage_state", renderStage);
socket.on("queue_updated", renderQueue);

window.setInterval(renderCountdown, 250);
loadQueue();
loadFiller().then(() => renderStage(stageState));
