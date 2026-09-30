const userQueueNotificationEl = document.getElementById("user-queue-notification");

if (userQueueNotificationEl instanceof HTMLElement) {
  const userQueueNotificationTitleEl = userQueueNotificationEl.querySelector(
    ".user-queue-notification-title"
  );
  const userQueueNotificationDetailEl = userQueueNotificationEl.querySelector(
    ".user-queue-notification-detail"
  );
  const currentUserName = String(userQueueNotificationEl.dataset.userName || "").trim();
  let userQueueNotificationTimer = null;
  let lastUserQueueNotificationKey = "none||";

  function normalizeName(value) {
    return String(value || "").trim().toLowerCase();
  }

  function normalizeNotificationState(state) {
    return {
      phase: String(state && state.phase ? state.phase : "none"),
      song: String(state && state.song ? state.song : ""),
      artist: String(state && state.artist ? state.artist : ""),
    };
  }

  function notificationStateKey(state) {
    return `${state.phase}|${state.song}|${state.artist}`;
  }

  function hideUserQueueNotification() {
    if (userQueueNotificationTimer) {
      window.clearTimeout(userQueueNotificationTimer);
      userQueueNotificationTimer = null;
    }
    userQueueNotificationEl.hidden = true;
    userQueueNotificationEl.classList.remove("up-next", "up-now");
    if (userQueueNotificationTitleEl instanceof HTMLElement) {
      userQueueNotificationTitleEl.textContent = "";
    }
    if (userQueueNotificationDetailEl instanceof HTMLElement) {
      userQueueNotificationDetailEl.textContent = "";
    }
  }

  function vibrateForNotification(phase) {
    if (!(navigator && typeof navigator.vibrate === "function")) {
      return;
    }
    const pattern = phase === "up-now" ? [300, 120, 300, 120, 300] : [180, 90, 180];
    try {
      navigator.vibrate(pattern);
    } catch (_error) {
    }
  }

  function showUserQueueNotification(state, shouldVibrate) {
    if (!(userQueueNotificationTitleEl instanceof HTMLElement)) {
      return;
    }

    const title = state.phase === "up-now" ? "UP NOW!!" : "UP NEXT!!";
    const detailParts = [];
    if (state.song) {
      detailParts.push(state.song);
    }
    if (state.artist) {
      detailParts.push(state.artist);
    }

    if (userQueueNotificationTimer) {
      window.clearTimeout(userQueueNotificationTimer);
      userQueueNotificationTimer = null;
    }

    userQueueNotificationEl.hidden = false;
    userQueueNotificationEl.classList.remove("up-next", "up-now");
    userQueueNotificationEl.classList.add(state.phase);
    userQueueNotificationTitleEl.textContent = title;
    if (userQueueNotificationDetailEl instanceof HTMLElement) {
      userQueueNotificationDetailEl.textContent = detailParts.join(" — ");
    }

    if (shouldVibrate) {
      vibrateForNotification(state.phase);
    }

    const displayMs = state.phase === "up-now" ? 9000 : 7000;
    userQueueNotificationTimer = window.setTimeout(() => {
      userQueueNotificationEl.hidden = true;
    }, displayMs);
  }

  function stateFromQueuePayload(payload) {
    const normalizedUser = normalizeName(currentUserName);
    if (!normalizedUser || !payload || typeof payload !== "object") {
      return { phase: "none", song: "", artist: "" };
    }

    const nowPlaying = payload.now_playing;
    if (nowPlaying && normalizeName(nowPlaying.user) === normalizedUser) {
      return {
        phase: "up-now",
        song: String(nowPlaying.song || ""),
        artist: String(nowPlaying.artist || ""),
      };
    }

    const firstUpNext = Array.isArray(payload.up_next) ? payload.up_next[0] : null;
    if (firstUpNext && normalizeName(firstUpNext.user) === normalizedUser) {
      return {
        phase: "up-next",
        song: String(firstUpNext.song || ""),
        artist: String(firstUpNext.artist || ""),
      };
    }

    return { phase: "none", song: "", artist: "" };
  }

  function syncUserQueueNotification(state, options) {
    const normalizedState = normalizeNotificationState(state);
    const nextKey = notificationStateKey(normalizedState);
    const changed = nextKey !== lastUserQueueNotificationKey;
    lastUserQueueNotificationKey = nextKey;

    if (normalizedState.phase === "none") {
      hideUserQueueNotification();
      return;
    }

    const forceDisplay = Boolean(options && options.forceDisplay);
    const shouldVibrate = Boolean(options && options.vibrate);
    if (!forceDisplay && !changed) {
      return;
    }

    showUserQueueNotification(normalizedState, shouldVibrate);
  }

  const initialNotificationState = normalizeNotificationState({
    phase: userQueueNotificationEl.dataset.phase,
    song: userQueueNotificationEl.dataset.song,
    artist: userQueueNotificationEl.dataset.artist,
  });

  syncUserQueueNotification(initialNotificationState, {
    forceDisplay: initialNotificationState.phase !== "none",
    vibrate: initialNotificationState.phase !== "none",
  });

  window.addEventListener("karaoke:queue-updated", (event) => {
    const state = stateFromQueuePayload(event.detail);
    syncUserQueueNotification(state, { vibrate: true });
  });
}
