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

const stageStateEl = document.getElementById("stage-state");
const stageNextEl = document.getElementById("stage-next");
const stageMessageEl = document.getElementById("stage-message");
const stageReportEl = document.getElementById("stage-report");
const teachStepsEl = document.getElementById("teach-steps");

function renderStageStatus(stage) {
  if (!stage || !stageStateEl) return;
  stageStateEl.textContent = stage.browser_running ? stage.state : "CLOSED";
  const next = stage.next;
  stageNextEl.textContent = stage.state === "INTERMISSION" && next ? `— waiting for ${next.user} (${next.song})` : "";
  stageMessageEl.textContent = stage.message || "";
  stageMessageEl.hidden = !stage.message;
  if (teachStepsEl) {
    const steps = stage.teach ? stage.teach.steps || [] : [];
    teachStepsEl.hidden = !stage.teach;
    teachStepsEl.innerHTML = "";
    for (const label of steps) {
      const li = document.createElement("li");
      li.textContent = label;
      teachStepsEl.appendChild(li);
    }
    if (stage.teach && !steps.length) {
      const li = document.createElement("li");
      li.textContent = "Recording… click through the song in the stage window.";
      teachStepsEl.appendChild(li);
    }
  }
}

async function refreshStageStatus() {
  if (!stageStateEl) return;
  const res = await fetch("/api/stage", { headers: { "X-Admin-Token": window.KT_ADMIN.token } });
  if (res.ok) renderStageStatus(await res.json());
}

function formatSelectorReport(report) {
  if (!report || report.error) return report?.error || "No report.";
  const lines = [`${report.service || "unknown service"} — ${report.url}`, `media: ${JSON.stringify(report.media)}`, ""];
  for (const row of report.selectors || []) {
    const mark = row.visible ? "VISIBLE" : row.count > 0 ? "hidden " : row.count < 0 ? "ERROR  " : "missing";
    lines.push(`${mark}  [${row.group}]  ${row.selector}`);
  }
  return lines.join("
");
}

async function postStageAction(action) {
  const form = new URLSearchParams();
  form.set("action", action);
  form.set("csrf_token", window.KT_ADMIN.csrfToken);
  const monitorSelect = document.getElementById("stage-monitor-select");
  if (monitorSelect instanceof HTMLSelectElement) {
    form.set("monitor", monitorSelect.value);
  }
  const teachService = document.getElementById("teach-service");
  const teachUrl = document.getElementById("teach-url");
  if (teachService instanceof HTMLSelectElement) form.set("service", teachService.value);
  if (teachUrl instanceof HTMLInputElement) form.set("url", teachUrl.value.trim());
  const res = await fetch("/admin/stage", {
    method: "POST",
    headers: { "X-Admin-Token": window.KT_ADMIN.token },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.message || "Stage action failed.");
    return;
  }
  if (data.report && stageReportEl) {
    stageReportEl.hidden = false;
    stageReportEl.textContent = formatSelectorReport(data.report);
  }
  if (data.stage) renderStageStatus(data.stage);
  if (action === "teach_save") alert(data.saved_steps ? `Saved ${data.saved_steps} steps.` : "Nothing was recorded, so nothing was saved.");
  if (action === "teach_reset") alert("Using the built-in steps for this service again.");
  await refreshQueue();
}

function renderRecent(items) {
  const tbody = document.querySelector("#recent-table tbody");
  const empty = document.getElementById("recent-empty");
  if (!tbody) return;
  tbody.innerHTML = "";
  for (const item of items) {
    const tr = document.createElement("tr");
    for (const value of [item.user, item.song, item.artist, item.service]) {
      const td = document.createElement("td");
      td.textContent = value || "";
      tr.appendChild(td);
    }
    const actionTd = document.createElement("td");
    const btn = document.createElement("button");
    btn.dataset.action = "play";
    btn.dataset.id = String(item.id);
    btn.textContent = "PLAY AGAIN";
    actionTd.appendChild(btn);
    tr.appendChild(actionTd);
    tbody.appendChild(tr);
  }
  if (empty) empty.hidden = items.length > 0;
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

    renderRecent(data.recent || []);

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
  if (target.dataset.stageAction) {
    await postStageAction(target.dataset.stageAction);
    return;
  }
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

if (window.io) {
  // Live updates instead of waiting for the next poll.
  const socket = window.io();
  socket.on("queue_updated", () => refreshQueue());
  socket.on("stage_state", (stage) => renderStageStatus(stage));
}

refreshQueue();
refreshStageStatus();
setInterval(refreshQueue, 12000);
setInterval(refreshStageStatus, 1500);
