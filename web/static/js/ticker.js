const nowSinger = document.getElementById("now-singer");
const nowSong = document.getElementById("now-song");
const nowArtist = document.getElementById("now-artist");
const upNext = document.getElementById("up-next");
const fullScreenBtn = document.getElementById("fullscreen-btn");
const controllerState = document.getElementById("controller-state");
const controllerService = document.getElementById("controller-service");
const controllerSinger = document.getElementById("controller-singer");
const controllerSong = document.getElementById("controller-song");
const controllerError = document.getElementById("controller-error");

function renderTicker(data) {
  const now = data.now_playing;
  if (!now) {
    nowSinger.textContent = "Waiting...";
    nowSong.textContent = "";
    nowArtist.textContent = "";
  } else {
    nowSinger.textContent = now.user;
    nowSong.textContent = now.song;
    nowArtist.textContent = now.artist;
  }

  upNext.innerHTML = "";
  for (const item of data.up_next || []) {
    const li = document.createElement("li");
    li.textContent = `${item.user} — ${item.song} (${item.artist})`;
    upNext.appendChild(li);
  }
}

function renderControllerStatus(payload) {
  const status = payload && payload.status ? payload.status : payload;
  if (!status || typeof status !== "object") {
    controllerState.textContent = "IDLE";
    controllerService.textContent = "-";
    controllerSinger.textContent = "-";
    controllerSong.textContent = "-";
    controllerError.textContent = "-";
    return;
  }

  const activeJob = status.active_job || null;
  controllerState.textContent = status.state || "IDLE";
  controllerService.textContent = activeJob && activeJob.service ? activeJob.service : "-";
  controllerSinger.textContent = activeJob && activeJob.singer ? activeJob.singer : "-";
  controllerSong.textContent = activeJob && activeJob.title ? activeJob.title : "-";
  controllerError.textContent = status.last_error ? status.last_error : "-";
}

let tickerRefreshInFlight = false;
let controllerRefreshInFlight = false;

async function loadInitial() {
  if (tickerRefreshInFlight) {
    return;
  }
  tickerRefreshInFlight = true;
  try {
    const res = await fetch("/api/ticker", {
      headers: { "X-Ticker-Token": window.KT_TICKER.token },
    });
    if (res.ok) {
      const data = await res.json();
      renderTicker(data);
    }
  } finally {
    tickerRefreshInFlight = false;
  }
}

async function loadControllerStatus() {
  if (controllerRefreshInFlight) {
    return;
  }
  controllerRefreshInFlight = true;
  try {
    const res = await fetch("/api/ticker/playback-status", {
      headers: { "X-Ticker-Token": window.KT_TICKER.token },
    });
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    renderControllerStatus(data);
  } finally {
    controllerRefreshInFlight = false;
  }
}

fullScreenBtn.addEventListener("click", () => {
  document.documentElement.requestFullscreen();
});

const socket = io();
socket.on("queue_updated", renderTicker);
socket.on("playback_status", renderControllerStatus);

loadInitial();
loadControllerStatus();
setInterval(loadInitial, 4000);
setInterval(loadControllerStatus, 1200);
