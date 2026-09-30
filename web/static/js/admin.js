async function postAction(action, queueItemId = "") {
  const form = new URLSearchParams();
  form.set("action", action);
  form.set("queue_item_id", String(queueItemId));
  form.set("csrf_token", window.KT_ADMIN.csrfToken);
  const res = await fetch("/admin/action", {
    method: "POST",
    headers: { "X-Admin-Token": window.KT_ADMIN.token },
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    alert(`Action failed: ${text}`);
  } else {
    await refreshQueue();
  }
}

let refreshInFlight = false;
let controllerRefreshInFlight = false;

const controllerStateEl = document.getElementById("controller-state");
const controllerServiceEl = document.getElementById("controller-service");
const controllerSingerEl = document.getElementById("controller-singer");
const controllerSongEl = document.getElementById("controller-song");
const controllerErrorEl = document.getElementById("controller-error");
const controllerRecentActionsEl = document.getElementById("controller-recent-actions");
const controllerStartBtn = document.getElementById("controller-start-btn");
const controllerStopBtn = document.getElementById("controller-stop-btn");
const controllerStopAllBtn = document.getElementById("controller-stop-all-btn");

function renderControllerStatus(status) {
  if (!status || typeof status !== "object") {
    if (controllerStateEl) controllerStateEl.textContent = "STOPPED";
    if (controllerServiceEl) controllerServiceEl.textContent = "-";
    if (controllerSingerEl) controllerSingerEl.textContent = "-";
    if (controllerSongEl) controllerSongEl.textContent = "-";
    if (controllerErrorEl) controllerErrorEl.textContent = "-";
    if (controllerRecentActionsEl) controllerRecentActionsEl.textContent = "No controller actions yet.";
    return;
  }

  const activeJob = status.active_job || null;
  const rawState = status.state || "IDLE";
  let displayState = rawState;
  if (!status.connected) {
    displayState = "STOPPED";
  } else if (["PREPARING", "STARTING", "VERIFYING_START", "PLAYING", "STOPPING"].includes(rawState)) {
    displayState = `RUNNING (${rawState})`;
  }

  if (controllerStateEl) controllerStateEl.textContent = displayState;
  if (controllerServiceEl) controllerServiceEl.textContent = activeJob && activeJob.service ? activeJob.service : "-";
  if (controllerSingerEl) controllerSingerEl.textContent = activeJob && activeJob.singer ? activeJob.singer : "-";
  if (controllerSongEl) controllerSongEl.textContent = activeJob && activeJob.title ? activeJob.title : "-";
  if (controllerErrorEl) controllerErrorEl.textContent = status.last_error || "-";
  if (controllerRecentActionsEl) {
    const recent = Array.isArray(status.recent_actions) ? status.recent_actions : [];
    controllerRecentActionsEl.textContent = recent.length ? recent.join("\n") : "No controller actions yet.";
  }
}

async function refreshControllerStatus() {
  if (controllerRefreshInFlight) {
    return;
  }
  controllerRefreshInFlight = true;
  try {
    const res = await fetch("/api/playback/status", {
      headers: { "X-Admin-Token": window.KT_ADMIN.token },
    });
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    renderControllerStatus(data.status || null);
  } finally {
    controllerRefreshInFlight = false;
  }
}

async function postControllerAction(path) {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "X-Admin-Token": window.KT_ADMIN.token,
      "X-CSRF-Token": window.KT_ADMIN.csrfToken,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    alert(`Controller action failed: ${text}`);
    return;
  }
  await refreshControllerStatus();
}

async function refreshQueue() {
  if (refreshInFlight) {
    return;
  }
  refreshInFlight = true;
  try {
    const res = await fetch("/api/queue", {
      headers: { "X-Admin-Token": window.KT_ADMIN.token },
    });
    if (!res.ok) {
      return;
    }
    const data = await res.json();

    const nowPlayingText = document.getElementById("now-playing-text");
    const reopenBtn = document.getElementById("reopen-now-playing");
    const nowPlaying = data.now_playing || null;
    if (nowPlayingText) {
      if (nowPlaying) {
        nowPlayingText.textContent = `${nowPlaying.user || ""} — ${nowPlaying.song || ""} / ${nowPlaying.artist || ""}`;
      } else {
        nowPlayingText.textContent = "No song marked as now playing.";
      }
    }
    if (reopenBtn) {
      if (nowPlaying && nowPlaying.id) {
        reopenBtn.style.display = "";
        reopenBtn.dataset.id = String(nowPlaying.id);
      } else {
        reopenBtn.style.display = "none";
        delete reopenBtn.dataset.id;
      }
    }

    const tbody = document.querySelector("#queue-table tbody");
    tbody.innerHTML = "";
    for (const item of data.queue_all || []) {
      const tr = document.createElement("tr");
      const userTd = document.createElement("td");
      userTd.textContent = item.user || "";
      const songTd = document.createElement("td");
      songTd.textContent = item.song || "";
      const artistTd = document.createElement("td");
      artistTd.textContent = item.artist || "";
      const serviceTd = document.createElement("td");
      serviceTd.textContent = item.service || "";
      const actionsTd = document.createElement("td");

      for (const action of ["play", "complete", "skip", "remove", "up", "down"]) {
        const btn = document.createElement("button");
        btn.dataset.action = action;
        btn.textContent = {
          play: "PLAY/OPEN",
          complete: "MARK COMPLETE",
          skip: "SKIP",
          remove: "REMOVE",
          up: "MOVE UP",
          down: "MOVE DOWN",
        }[action];
        actionsTd.appendChild(btn);
      }

      tr.appendChild(userTd);
      tr.appendChild(songTd);
      tr.appendChild(artistTd);
      tr.appendChild(serviceTd);
      tr.appendChild(actionsTd);
      tr.dataset.id = String(item.id);
      tbody.appendChild(tr);
    }
  } finally {
    refreshInFlight = false;
  }
}

document.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) return;
  const action = target.dataset.action;
  if (!action) return;
  const row = target.closest("tr");
  const queueItemId = target.dataset.id || (row ? row.dataset.id : "");
  await postAction(action, queueItemId || "");
});

const adminUserModsToggle = document.getElementById("admin-user-mods-toggle");
const adminUserModsPanel = document.getElementById("admin-user-mods-panel");

function setAdminUserModsVisible(visible) {
  if (!adminUserModsPanel) return;
  if (visible) {
    adminUserModsPanel.removeAttribute("hidden");
  } else {
    adminUserModsPanel.setAttribute("hidden", "hidden");
  }
}

if (adminUserModsToggle instanceof HTMLInputElement) {
  setAdminUserModsVisible(adminUserModsToggle.checked);
  adminUserModsToggle.addEventListener("change", () => {
    setAdminUserModsVisible(adminUserModsToggle.checked);
  });
}

if (controllerStartBtn instanceof HTMLButtonElement) {
  controllerStartBtn.addEventListener("click", async () => {
    await postControllerAction("/api/playback/start-controller");
  });
}

if (controllerStopBtn instanceof HTMLButtonElement) {
  controllerStopBtn.addEventListener("click", async () => {
    await postControllerAction("/api/playback/stop-controller");
  });
}

if (controllerStopAllBtn instanceof HTMLButtonElement) {
  controllerStopAllBtn.addEventListener("click", async () => {
    await postControllerAction("/api/playback/stop-all");
  });
}

refreshQueue();
refreshControllerStatus();
setInterval(refreshQueue, 12000);
setInterval(refreshControllerStatus, 1500);
