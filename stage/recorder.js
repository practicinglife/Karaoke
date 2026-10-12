// Teach mode: report the host's clicks and keys to the app (window.__ktRecord is a
// Playwright binding; the app ignores events unless a teach session is running).
// Each click is described by several selectors, most stable first, so replay still
// finds the button if one attribute changes.
(() => {
  if (window.__ktRecorderInstalled) {
    return;
  }
  window.__ktRecorderInstalled = true;

  const CLICKABLE = "button, a, [role='button'], [role='tab'], [role='menuitem'], [role='switch'], input, [tabindex]";
  const quote = (value) => JSON.stringify(String(value));
  // Build-generated names (hashes) change on every site update, so they make poor selectors.
  const looksGenerated = (value) =>
    /\d{3,}|[a-f0-9]{8,}|^:/.test(value) || (/^[A-Za-z0-9_]{12,}$/.test(value) && /[a-z]/.test(value) && /[A-Z]/.test(value));

  function shortText(el) {
    const text = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
    return text.length > 0 && text.length <= 40 ? text : "";
  }

  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "button") return "button";
    if (tag === "a" && el.hasAttribute("href")) return "link";
    return "";
  }

  function selectorsFor(el) {
    const tag = el.tagName.toLowerCase();
    const found = [];
    const add = (selector) => {
      if (selector && !found.includes(selector)) found.push(selector);
    };
    const testId = el.getAttribute("data-testid") || el.getAttribute("data-test-id");
    if (testId) add(`${tag}[data-testid=${quote(testId)}]`);
    const label = el.getAttribute("aria-label");
    if (label) add(`${tag}[aria-label=${quote(label)}]`);
    if (el.id && !looksGenerated(el.id)) add(`#${CSS.escape(el.id)}`);
    const role = roleOf(el);
    const name = label || shortText(el);
    if (role && name) add(`role=${role}[name=${quote(name)}]`);
    const classes = Array.from(el.classList).filter((c) => !looksGenerated(c)).slice(0, 2);
    if (classes.length) add(`${tag}.${classes.map((c) => CSS.escape(c)).join(".")}`);
    const text = shortText(el);
    if (text && !label) add(`${tag}:has-text(${quote(text)})`);
    return found;
  }

  function describe(el) {
    const label = el.getAttribute("aria-label") || el.getAttribute("title") || shortText(el);
    return label || el.tagName.toLowerCase();
  }

  function mediaPlaying() {
    try {
      return Boolean(window.__ktState && window.__ktState().playing);
    } catch (_error) {
      return false;
    }
  }

  function send(payload) {
    if (typeof window.__ktRecord === "function") {
      window.__ktRecord(payload).catch(() => {});
    }
  }

  document.addEventListener(
    "click",
    (event) => {
      if (!event.isTrusted) return;
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      const el = target.closest(CLICKABLE) || target;
      send({
        type: "click",
        selectors: selectorsFor(el),
        label: describe(el),
        wasPlaying: mediaPlaying(),
        wasFullscreen: Boolean(document.fullscreenElement),
      });
    },
    true
  );

  document.addEventListener(
    "keydown",
    (event) => {
      if (!event.isTrusted || event.repeat) return;
      if (["Shift", "Control", "Alt", "Meta"].includes(event.key)) return;
      // The app manages the window's fullscreen itself, so Teach mode never replays these;
      // they still tell the app the host has taken over the song.
      const hostOnly = ["F11", "Escape"].includes(event.key);
      const active = document.activeElement;
      if (active && (active.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName))) return;
      send({
        type: "press",
        key: event.key.length === 1 ? event.key.toLowerCase() : event.key,
        focus: active && active !== document.body ? selectorsFor(active) : [],
        wasPlaying: mediaPlaying(),
        wasFullscreen: Boolean(document.fullscreenElement),
        hostOnly,
      });
    },
    true
  );
})();
