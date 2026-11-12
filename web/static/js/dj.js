// DJ phone page: the host runs the queue and the stage from a phone.
const { token, csrf } = window.KT_DJ;
const NEW_SINGER = "new";

const messageEl = document.getElementById("dj-message");
const stageStateEl = document.getElementById("dj-stage-state");
const nowEl = document.getElementById("dj-now");
const queueEl = document.getElementById("dj-queue");
const singerEl = document.getElementById("dj-singer");
const newSingerEl = document.getElementById("dj-new-singer");
const newNameEl = document.getElementById("dj-new-name");
const songAreaEl = document.getElementById("dj-song-area");
const savedEl = document.getElementById("dj-saved");
const searchEl = document.getElementById("dj-search");
const resultsEl = document.getElementById("dj-results");

const STATE_TEXT = {
  IDLE: "Stage closed",
  INTERMISSION: "Waiting for the next singer",
  STARTING: "Starting the song…",
  PLAYING: "Playing",
  TEACHING: "Teach mode",
};

let messageTimer = null;
function say(text, isError = false) {
  messageEl.textContent = text;
  messageEl.classList.toggle("dj-error", isError);
  messageEl.hidden = !text;
  clearTimeout(messageTimer);
  if (text) messageTimer = setTimeout(() => { messageEl.hidden = true; }, 4000);
}

async function api(path, body) {
  const options = { headers: { "X-Admin-Token": token }, cache: "no-cache" };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["X-CSRF-Token"] = csrf;
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch (_error) { data = null; }
  if (!res.ok || (data && data.ok === false)) {
    throw new Error((data && data.message) || `Something went wrong (${res.status}).`);
  }
  return data;
}

async function act(path, body, done) {
  try {
    await api(path, body || {});
    if (done) say(done);
    await refresh();
  } catch (error) {
    say(error.message, true);
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, onClick, className) {
  const btn = el("button", className, label);
  btn.type = "button";
  btn.onclick = onClick;
  return btn;
}

function songLine(item) {
  const line = el("span", "dj-song");
  line.append(el("strong", "", item.user ? `${item.user}: ` : ""), document.createTextNode(item.song || item.title || ""));
  if (item.artist) line.append(el("span", "dj-artist", ` — ${item.artist}`));
  return line;
}

// ----- stage + queue ---------------------------------------------------------------

function renderStage(stage) {
  if (!stage) return;
  stageStateEl.textContent = STATE_TEXT[stage.state] || stage.state;
  if (stage.state === "INTERMISSION" && stage.next) {
    stageStateEl.textContent += ` · up: ${stage.next.user || ""}`;
  }
}

function renderQueue(state) {
  nowEl.innerHTML = "";
  if (state.now_playing) {
    nowEl.append(el("span", "dj-label", "NOW "), songLine(state.now_playing));
  }
  queueEl.innerHTML = "";
  if (!state.queue.length) {
    queueEl.append(el("li", "hint", "Nobody is waiting."));
    return;
  }
  state.queue.forEach((item, index) => {
    const li = el("li", "dj-item");
    li.append(songLine(item));
    const tools = el("div", "dj-tools");
    const path = (action) => `/api/dj/item/${item.id}/${action}`;
    if (index > 0) {
      tools.append(button("TOP", () => act(path("top"), {}, `${item.user} is next.`)));
      tools.append(button("▲", () => act(path("up"))));
    }
    if (index < state.queue.length - 1) tools.append(button("▼", () => act(path("down"))));
    tools.append(button("✕", () => {
      if (confirm(`Remove ${item.song} (${item.user}) from the queue?`)) act(path("remove"), {}, "Removed.");
    }, "dj-remove"));
    li.append(tools);
    queueEl.append(li);
  });
}

function renderSingers(singers) {
  const chosen = singerEl.value;
  singerEl.innerHTML = "";
  singerEl.append(new Option("Choose a singer…", ""));
  for (const singer of singers) singerEl.append(new Option(singer.name, String(singer.id)));
  singerEl.append(new Option("+ New singer", NEW_SINGER));
  if ([...singerEl.options].some((o) => o.value === chosen)) singerEl.value = chosen;
}

async function refresh() {
  try {
    const state = await api("/api/dj/state");
    renderStage(state.stage);
    renderQueue(state);
    renderSingers(state.singers);
  } catch (error) {
    say(error.message, true);
  }
}

document.querySelectorAll("[data-stage]").forEach((btn) => {
  btn.onclick = () => {
    const action = btn.dataset.stage;
    if (action !== "start_next" && !confirm(action === "end" ? "End this song?" : "Play this song again from the start?")) return;
    act(`/api/dj/stage/${action}`);
  };
});

// ----- queue a song ----------------------------------------------------------------

function queueButtons(body, label) {
  const tools = el("div", "dj-tools");
  const send = async (next) => {
    await act("/api/dj/queue", { ...body, user_id: Number(singerEl.value), next },
      next ? `${label} is next.` : `${label} added.`);
    if (body.library_id) loadSaved(); // it's on their list now
  };
  tools.append(button("NEXT", () => send(true), "dj-go"), button("END", () => send(false)));
  return tools;
}

async function loadSaved() {
  savedEl.innerHTML = "";
  const userId = singerEl.value;
  if (!userId || userId === NEW_SINGER) return;
  try {
    const songs = await api(`/api/dj/singer/${userId}/songs`);
    if (!songs.length) savedEl.append(el("li", "hint", "No saved songs yet. Find one below."));
    for (const song of songs) {
      const li = el("li", "dj-item");
      li.append(songLine({ song: song.title, artist: song.artist }), queueButtons({ song_id: song.id }, song.title));
      savedEl.append(li);
    }
  } catch (error) {
    say(error.message, true);
  }
}

singerEl.onchange = () => {
  const value = singerEl.value;
  newSingerEl.hidden = value !== NEW_SINGER;
  songAreaEl.hidden = !value || value === NEW_SINGER;
  if (value === NEW_SINGER) newNameEl.focus();
  loadSaved();
};

document.getElementById("dj-new-add").onclick = async () => {
  try {
    const singer = await api("/api/dj/singer", { name: newNameEl.value });
    newNameEl.value = "";
    await refresh();
    singerEl.value = String(singer.id);
    singerEl.onchange();
    say(`${singer.name} is ready to queue.`);
  } catch (error) {
    say(error.message, true);
  }
};

function libraryRow(song) {
  const best = song.versions.find((v) => v.id === song.best_id) || song.versions[0];
  const li = el("li", "dj-item");
  li.append(songLine({ song: song.title, artist: song.artist }));
  if (best && best.label) li.append(el("span", "dj-artist", ` [${best.label}]`));
  li.append(queueButtons({ library_id: best.id, title: best.save_title || song.title, artist: song.artist }, song.title));
  return li;
}

function artistRow(artist, query) {
  const li = el("li", "dj-artist-row");
  const list = el("ul", "dj-list");
  list.hidden = true;
  let loaded = false;
  li.append(button(`${artist.name} (${artist.songs})`, async () => {
    list.hidden = !list.hidden;
    if (loaded || list.hidden) return;
    loaded = true;
    try {
      const songs = await api(`/api/dj/search/artist?key=${encodeURIComponent(artist.key)}&q=${encodeURIComponent(query)}`);
      for (const song of songs) list.append(libraryRow(song));
    } catch (error) {
      loaded = false;
      say(error.message, true);
    }
  }, "dj-artist-btn"), list);
  return li;
}

let searchTimer = null;
let searchSeq = 0;
searchEl.oninput = () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = searchEl.value.trim();
    const seq = ++searchSeq;
    resultsEl.innerHTML = "";
    if (q.length < 2) return;
    try {
      const data = await api(`/api/dj/search?q=${encodeURIComponent(q)}`);
      if (seq !== searchSeq) return;
      for (const artist of data.artists || []) resultsEl.append(artistRow(artist, q));
      for (const song of data.songs || []) resultsEl.append(libraryRow(song));
      if (!resultsEl.children.length) resultsEl.append(el("li", "hint", "No matching song found."));
    } catch (error) {
      say(error.message, true);
    }
  }, 300);
};

// ----- live updates ----------------------------------------------------------------

const socket = io();
socket.on("queue_updated", refresh);
socket.on("stage_state", renderStage);
socket.on("connect", refresh);
refresh();
