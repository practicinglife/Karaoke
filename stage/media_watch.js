// Injected into every page the stage browser loads (Playwright add_init_script).
// Tracks every <audio>/<video> element - including detached ones created by
// streaming players - so the app can tell when a song has started and ended.
(() => {
  if (window.__ktState) {
    return;
  }
  const tracked = new Set();
  const flags = { started: false, ended: false };

  function track(el) {
    if (!(el instanceof HTMLMediaElement) || tracked.has(el)) {
      return;
    }
    tracked.add(el);
    el.addEventListener("playing", () => {
      flags.started = true;
    });
    // Sticky: sites often auto-play the next track right after the song ends.
    // An 'ended' while a busy marker (e.g. YouTube ad) is showing doesn't count.
    el.addEventListener("ended", () => {
      const busy = (window.__ktBusySelectors || []).some((selector) => {
        try {
          return Boolean(document.querySelector(selector));
        } catch (_error) {
          return false;
        }
      });
      if (!busy) {
        flags.ended = true;
      }
    });
  }

  const originalPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...args) {
    track(this);
    return originalPlay.apply(this, args);
  };
  document.addEventListener("play", (event) => track(event.target), true);
  document.addEventListener("playing", (event) => track(event.target), true);

  window.__ktState = () => {
    for (const el of document.querySelectorAll("audio, video")) {
      track(el);
    }
    // Report the element that is (or was most recently) carrying the song.
    let best = null;
    for (const el of tracked) {
      if (!best || (!el.paused && best.paused) || (el.duration || 0) > (best.duration || 0)) {
        best = el;
      }
    }
    return {
      started: flags.started,
      ended: flags.ended,
      playing: Boolean(best && !best.paused && !best.ended),
      position: best ? best.currentTime || 0 : 0,
      duration: best && Number.isFinite(best.duration) ? best.duration : 0,
      // Window fullscreen (set by the app) doesn't set fullscreenElement; only the page's own player does.
      fullscreen: Boolean(document.fullscreenElement),
      // Track title the site reports to the OS media controls. Players that roll straight
      // into the next track (Apple Music albums) never fire 'ended'; the title changes instead.
      title: (navigator.mediaSession && navigator.mediaSession.metadata && navigator.mediaSession.metadata.title) || "",
    };
  };
})();
