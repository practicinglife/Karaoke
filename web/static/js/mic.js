// Mic-stand page: START plays whoever is up next on the stage screen.
const micKey = window.KT_MIC?.key || "";
const labelEl = document.getElementById("mic-label");
const singerEl = document.getElementById("mic-singer");
const songEl = document.getElementById("mic-song");
const countdownEl = document.getElementById("mic-countdown");
const startBtn = document.getElementById("mic-start");
const messageEl = document.getElementById("mic-message");

let micState = window.KT_MIC?.state || null;
let busy = false;

function songLine(item) {
  return [item?.song, item?.artist].filter(Boolean).join(" — ");
}

function render(state) {
  micState = state;
  const phase = state?.state || "IDLE";
  const next = state?.next || null;
  const now = state?.now || null;
  labelEl.classList.toggle("singing", phase === "PLAYING");

  if (phase === "PLAYING" || phase === "STARTING") {
    labelEl.textContent = phase === "PLAYING" ? "NOW SINGING" : "STARTING…";
    singerEl.textContent = now?.user || "";
    songEl.textContent = songLine(now);
    startBtn.disabled = true;
  } else if (phase === "TEACHING") {
    labelEl.textContent = "HOST IS SETTING UP";
    singerEl.textContent = "";
    songEl.textContent = "";
    startBtn.disabled = true;
  } else if (next) {
    labelEl.textContent = "UP NEXT";
    singerEl.textContent = next.user || "";
    songEl.textContent = songLine(next);
    startBtn.disabled = busy;
  } else {
    labelEl.textContent = phase === "IDLE" ? "STAGE SCREEN IS CLOSED" : "QUEUE IS EMPTY";
    singerEl.textContent = "";
    songEl.textContent = phase === "IDLE" ? "Press START when a singer is up" : "Add songs from your phone";
    // When the stage is closed, START opens it and plays whoever is first in the queue.
    startBtn.disabled = busy || phase !== "IDLE";
  }
  renderCountdown();
}

function renderCountdown() {
  const endsAt = micState?.countdown_ends_at;
  if (!endsAt || micState?.state !== "INTERMISSION" || !micState?.next) {
    countdownEl.hidden = true;
    return;
  }
  const remaining = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
  countdownEl.hidden = false;
  countdownEl.textContent = remaining > 0 ? String(remaining) : "Your turn!";
}

startBtn.addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  startBtn.disabled = true;
  messageEl.textContent = "Starting…";
  try {
    const res = await fetch(`/api/stage/ready?key=${encodeURIComponent(micKey)}`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    messageEl.textContent = res.ok && data.ok ? "" : data.message || "Couldn't start. Ask the host.";
  } catch (_error) {
    messageEl.textContent = "Can't reach the karaoke computer. Check Wi-Fi.";
  } finally {
    busy = false;
    render(micState);
  }
});

// Keep the iPad/iPhone screen awake while this page is open.
async function keepAwake() {
  try {
    if ("wakeLock" in navigator && document.visibilityState === "visible") {
      await navigator.wakeLock.request("screen");
    }
  } catch (_error) {
  }
}
document.addEventListener("visibilitychange", keepAwake);
keepAwake();

const socket = io();
socket.on("stage_state", render);
socket.on("connect", () => {
  messageEl.textContent = "";
});
socket.on("disconnect", () => {
  messageEl.textContent = "Reconnecting…";
});

window.setInterval(renderCountdown, 250);
render(micState);
