const serviceSelector = document.getElementById("service-selector");
const titleInput = document.getElementById("song-title");
const artistInput = document.getElementById("song-artist");
const urlRow = document.getElementById("url-row");
const urlLabel = document.getElementById("url-label");
const urlInput = document.getElementById("url-input");
const traditionalRow = document.getElementById("traditional-row");
const searchInput = document.getElementById("traditional-search");
const resultsEl = document.getElementById("search-results");
const karaokeLibraryId = document.getElementById("karaoke-library-id");
const deleteModeToggle = document.getElementById("delete-mode-toggle");
const songTilesEl = document.getElementById("song-tiles");
const deleteSelectedBtn = document.getElementById("delete-selected-btn");
const bulkDeleteForm = document.getElementById("bulk-delete-form");
const userCsrfToken = document.getElementById("user-csrf-token");
const bulkUploadToggle = document.getElementById("bulk-upload-toggle");
const bulkUploadPanel = document.getElementById("bulk-upload-panel");
const savedTools = document.getElementById("saved-tools");
const savedFind = document.getElementById("saved-find");
const savedSort = document.getElementById("saved-sort");
const savedViewList = document.getElementById("saved-view-list");
const savedViewTiles = document.getElementById("saved-view-tiles");
const savedNone = document.getElementById("saved-none");

let searchController = null;
let lastSearchQuery = "";
let userQueueNotificationTimer = null;
let lastUserQueueNotificationKey = "none||";

const QUEUED_SONG_ARIA_SUFFIX = ", queued tonight, click again to remove from queue";
const UP_NEXT_NOTIFICATION_TEXT = "UP NEXT!!";
const UP_NOW_NOTIFICATION_TEXT = "UP NOW!!";
const SAVED_VIEW_KEY = "kt-saved-songs-view";
const SAVED_SORT_KEY = "kt-saved-songs-sort";
const LIST_VIEW_FROM = 11; // more than 10 saved songs start as a list

function getQueuedSongBaseLabel(tile) {
  const existing = tile.dataset.baseAriaLabel;
  if (existing) {
    return existing;
  }
  const current = tile.getAttribute("aria-label") || "";
  const base = current.endsWith(QUEUED_SONG_ARIA_SUFFIX)
    ? current.slice(0, -QUEUED_SONG_ARIA_SUFFIX.length)
    : current;
  tile.dataset.baseAriaLabel = base;
  return base;
}

function setQueuedSongState(tile, queued) {
  if (!(tile instanceof HTMLElement)) return;
  tile.classList.toggle("queued-song", queued);
  const badge = tile.querySelector(".song-tile-badge");
  if (badge instanceof HTMLElement) {
    badge.hidden = !queued;
  }
  const baseLabel = getQueuedSongBaseLabel(tile);
  tile.setAttribute("aria-label", queued ? `${baseLabel}${QUEUED_SONG_ARIA_SUFFIX}` : baseLabel);
}

function setPlayedSongState(tile, played) {
  if (!(tile instanceof HTMLElement)) return;
  tile.classList.toggle("played-song", played);
  const mark = tile.querySelector(".song-tile-played");
  if (mark instanceof HTMLElement) {
    // Queued again after singing it: "Queued tonight" wins.
    mark.hidden = !played || tile.classList.contains("queued-song");
  }
}

function applyQueuedSongState(queuedIds, playedIds = null) {
  if (!songTilesEl) return;
  const queued = new Set(Array.from(queuedIds, (value) => String(value)));
  const played = playedIds ? new Set(Array.from(playedIds, (value) => String(value))) : null;
  songTilesEl.querySelectorAll(".song-tile").forEach((tile) => {
    const songId = tile.getAttribute("data-song-id") || "";
    setQueuedSongState(tile, queued.has(songId));
    setPlayedSongState(tile, played ? played.has(songId) : tile.classList.contains("played-song"));
  });
  arrangeSavedSongs();
}

// ----- saved songs: find, sort, list or tiles -----------------------------------

function readPref(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function writePref(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_error) {
    // private browsing: the choice just isn't remembered
  }
}

function plainText(value) {
  return String(value || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

// Queued tonight first, then the rest, then songs already played tonight at the bottom.
function songBand(tile) {
  if (tile.classList.contains("queued-song")) return 0;
  if (tile.classList.contains("played-song")) return 2;
  return 1;
}

function compareSongs(a, b, sort) {
  const byTitle = plainText(a.dataset.title).localeCompare(plainText(b.dataset.title));
  const byArtist = plainText(a.dataset.artist).localeCompare(plainText(b.dataset.artist));
  if (sort === "title") return byTitle || byArtist;
  if (sort === "artist") return byArtist || byTitle;
  return Number(a.dataset.order || 0) - Number(b.dataset.order || 0);
}

function arrangeSavedSongs() {
  if (!songTilesEl) return;
  const sort = savedSort instanceof HTMLSelectElement ? savedSort.value : "newest";
  const query = savedFind instanceof HTMLInputElement ? plainText(savedFind.value.trim()) : "";
  const tiles = Array.from(songTilesEl.querySelectorAll(".song-tile"));
  tiles.sort((a, b) => songBand(a) - songBand(b) || compareSongs(a, b, sort));
  let shown = 0;
  for (const tile of tiles) {
    const matches = !query || plainText(`${tile.dataset.title} ${tile.dataset.artist}`).includes(query);
    tile.hidden = !matches;
    if (matches) shown += 1;
    songTilesEl.appendChild(tile);
  }
  if (savedNone) savedNone.hidden = !query || shown > 0;
}

function setSavedView(view) {
  if (!songTilesEl) return;
  const list = view === "list";
  songTilesEl.classList.toggle("song-list-view", list);
  if (savedViewList) savedViewList.setAttribute("aria-pressed", list ? "true" : "false");
  if (savedViewTiles) savedViewTiles.setAttribute("aria-pressed", list ? "false" : "true");
}

function setupSavedSongs() {
  if (!songTilesEl || !savedTools) return;
  const count = Number(savedTools.dataset.songCount || 0);
  const view = readPref(SAVED_VIEW_KEY) || (count >= LIST_VIEW_FROM ? "list" : "tiles");
  setSavedView(view);
  const sort = readPref(SAVED_SORT_KEY);
  if (savedSort instanceof HTMLSelectElement && sort && savedSort.querySelector(`option[value="${sort}"]`)) {
    savedSort.value = sort;
  }
  savedViewList?.addEventListener("click", () => {
    setSavedView("list");
    writePref(SAVED_VIEW_KEY, "list");
  });
  savedViewTiles?.addEventListener("click", () => {
    setSavedView("tiles");
    writePref(SAVED_VIEW_KEY, "tiles");
  });
  savedSort?.addEventListener("change", () => {
    writePref(SAVED_SORT_KEY, savedSort.value);
    arrangeSavedSongs();
  });
  savedFind?.addEventListener("input", arrangeSavedSongs);
  arrangeSavedSongs();
}

function updateServiceUi() {
  const service = serviceSelector.value;
  if (service === "traditional") {
    traditionalRow.style.display = "block";
    urlRow.style.display = "none";
    urlInput.value = "";
  } else {
    traditionalRow.style.display = "none";
    urlRow.style.display = "block";
    karaokeLibraryId.value = "";
    clearSearchResults();
    if (service === "youtube") {
      urlLabel.textContent = "YouTube Link";
    } else if (service === "apple_music") {
      urlLabel.textContent = "Apple Music Link";
    } else {
      urlLabel.textContent = "Spotify Link";
    }
  }
}

function debounce(fn, wait) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}


function clearSearchResults() {
  resultsEl.innerHTML = "";
}

function searchNote(text) {
  const li = document.createElement("li");
  li.className = "search-note";
  li.textContent = text;
  return li;
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// Save one version of a song to the singer's list in one tap.
function addVersion(song, version) {
  karaokeLibraryId.value = String(version.id || "");
  if (titleInput) titleInput.value = version.save_title || song.title || "";
  if (artistInput) artistInput.value = song.artist || "";
  const form = document.getElementById("add-song-form");
  if (form && typeof form.requestSubmit === "function") {
    form.requestSubmit();
  } else if (form) {
    form.submit();
  }
}

function addButton(song, version, label) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "search-add";
  btn.textContent = label;
  btn.setAttribute("aria-label", `Add ${song.title} by ${song.artist}${version.label ? `, ${version.label}` : ""}`);
  btn.onclick = (event) => {
    event.stopPropagation();
    btn.disabled = true;
    btn.textContent = "ADDING…";
    addVersion(song, version);
  };
  return btn;
}

function tagBadges(tags) {
  return (tags || []).map((tag) => {
    const span = document.createElement("span");
    span.className = "search-tag";
    span.textContent = tag.toUpperCase();
    return span;
  });
}

function toggleRow(row, nested, open) {
  nested.hidden = !open;
  row.setAttribute("aria-expanded", open ? "true" : "false");
  row.querySelector(".search-chevron").textContent = open ? "▾" : "▸";
}

function renderSong(song, showArtist) {
  const li = document.createElement("li");
  li.className = "search-song";
  const row = document.createElement("div");
  row.className = "search-row";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "search-toggle";
  toggle.setAttribute("aria-expanded", "false");
  const chevron = document.createElement("span");
  chevron.className = "search-chevron";
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "search-name";
  name.textContent = showArtist ? `${song.title} — ${song.artist}` : song.title;
  const count = document.createElement("span");
  count.className = "search-count";
  count.textContent = plural(song.versions.length, "version");
  toggle.append(chevron, name, ...tagBadges(song.tags), count);

  const best = song.versions.find((v) => v.id === song.best_id) || song.versions[0];
  row.append(toggle, addButton(song, best, "ADD"));

  const nested = document.createElement("ul");
  nested.className = "search-versions";
  nested.hidden = true;
  for (const version of song.versions) {
    const vli = document.createElement("li");
    vli.className = "search-row search-version";
    const label = document.createElement("span");
    label.className = "search-name";
    label.textContent = version.id === song.best_id ? `${version.label} (best)` : version.label;
    vli.append(label, addButton(song, version, "ADD"));
    nested.appendChild(vli);
  }
  toggle.onclick = () => toggleRow(toggle, nested, nested.hidden);

  li.append(row, nested);
  return li;
}

function renderArtist(artist, query) {
  const li = document.createElement("li");
  li.className = "search-artist";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "search-toggle search-row";
  toggle.setAttribute("aria-expanded", "false");
  const chevron = document.createElement("span");
  chevron.className = "search-chevron";
  chevron.textContent = "▸";
  const name = document.createElement("span");
  name.className = "search-name";
  name.textContent = artist.name;
  const count = document.createElement("span");
  count.className = "search-count";
  count.textContent = plural(artist.songs, "song");
  toggle.append(chevron, name, count);

  const nested = document.createElement("ul");
  nested.className = "search-songs";
  nested.hidden = true;
  let loaded = false;
  toggle.onclick = async () => {
    const open = nested.hidden;
    toggleRow(toggle, nested, open);
    if (!open || loaded) return;
    loaded = true;
    nested.appendChild(searchNote("Loading songs…"));
    try {
      const res = await fetch(
        `/song/search/artist?key=${encodeURIComponent(artist.key)}&q=${encodeURIComponent(query)}`,
        { cache: "no-cache" }
      );
      const songs = res.ok ? await res.json() : [];
      nested.innerHTML = "";
      for (const song of songs) {
        // Duets and featured spots show the full credit.
        nested.appendChild(renderSong(song, song.artist.toLowerCase() !== artist.name.toLowerCase()));
      }
      if (!songs.length) nested.appendChild(searchNote("No songs found."));
    } catch (_error) {
      loaded = false;
      nested.innerHTML = "";
      nested.appendChild(searchNote("Couldn't load the songs. Tap again."));
    }
  };
  li.append(toggle, nested);
  return li;
}

function renderGroupedResults(data, query) {
  resultsEl.innerHTML = "";
  const artists = Array.isArray(data?.artists) ? data.artists : [];
  const songs = Array.isArray(data?.songs) ? data.songs : [];
  if (!artists.length && !songs.length) {
    resultsEl.appendChild(searchNote("No matching song was found in the indexed karaoke library."));
    return;
  }
  if (artists.length) {
    const head = searchNote("ARTISTS");
    head.className = "search-heading";
    resultsEl.appendChild(head);
    for (const artist of artists) resultsEl.appendChild(renderArtist(artist, query));
    if (data.more_artists) resultsEl.appendChild(searchNote(`${data.more_artists} more artists — keep typing to narrow it down`));
  }
  if (songs.length) {
    const head = searchNote("SONGS");
    head.className = "search-heading";
    resultsEl.appendChild(head);
    for (const song of songs) resultsEl.appendChild(renderSong(song, true));
    if (data.more_songs) resultsEl.appendChild(searchNote(`${data.more_songs} more songs — keep typing to narrow it down`));
  }
}

async function runSearch() {
  if (serviceSelector.value !== "traditional") return;

  const q = searchInput.value.trim();
  karaokeLibraryId.value = "";

  if (!q) {
    lastSearchQuery = "";
    if (searchController) {
      searchController.abort();
      searchController = null;
    }
    clearSearchResults();
    return;
  }

  if (q === lastSearchQuery) {
    return;
  }
  lastSearchQuery = q;

  if (searchController) {
    searchController.abort();
  }
  searchController = new AbortController();

  try {
    const response = await fetch(`/song/search/grouped?q=${encodeURIComponent(q)}`, {
      cache: "no-cache",
      signal: searchController.signal,
    });
    if (!response.ok) {
      clearSearchResults();
      resultsEl.appendChild(searchNote("Search unavailable. Try again."));
      return;
    }
    renderGroupedResults(await response.json(), q);
  } catch (_error) {
    if (_error && _error.name === "AbortError") {
      return;
    }
    clearSearchResults();
    resultsEl.appendChild(searchNote("Search unavailable. Try again."));
  }
}

async function resolveLinkMetadata() {
  const service = serviceSelector.value;
  if (service !== "youtube" && service !== "apple_music" && service !== "spotify") {
    return;
  }
  const url = urlInput.value.trim();
  if (!url) {
    return;
  }

  try {
    const res = await fetch(
      `/song/link-metadata?service=${encodeURIComponent(service)}&url=${encodeURIComponent(url)}`
    );
    if (!res.ok) {
      return;
    }
    const data = await res.json();
    if (!data || !data.ok) {
      return;
    }
    if (titleInput && data.title) {
      titleInput.value = data.title;
    }
    if (artistInput && data.artist) {
      artistInput.value = data.artist;
    }
  } catch (_error) {
    // ignore metadata failures; manual input remains available
  }
}

const debouncedSearch = debounce(runSearch, 200);
const debouncedMetadata = debounce(resolveLinkMetadata, 450);

serviceSelector.addEventListener("change", () => {
  updateServiceUi();
  resolveLinkMetadata();
});
searchInput.addEventListener("input", debouncedSearch);
urlInput.addEventListener("input", debouncedMetadata);
urlInput.addEventListener("blur", resolveLinkMetadata);

function updateDeleteSelectedState() {
  if (!songTilesEl || !deleteSelectedBtn) return;
  let selected = 0;
  songTilesEl.querySelectorAll(".song-tile").forEach((tile) => {
    const checkbox = tile.querySelector(".song-delete-checkbox");
    if (checkbox instanceof HTMLInputElement && checkbox.checked) {
      selected += 1;
      tile.classList.add("selected-delete");
    } else {
      tile.classList.remove("selected-delete");
    }
  });
  deleteSelectedBtn.disabled = selected === 0;
}

function setDeleteMode(enabled) {
  if (!songTilesEl) return;
  songTilesEl.classList.toggle("delete-mode", enabled);
  if (!enabled) {
    songTilesEl.querySelectorAll(".song-delete-checkbox").forEach((input) => {
      if (input instanceof HTMLInputElement) {
        input.checked = false;
      }
    });
    songTilesEl.querySelectorAll(".song-tile").forEach((tile) => tile.classList.remove("selected-delete"));
  }
  updateDeleteSelectedState();
}

function queueSongFromTile(tile) {
  if (!(tile instanceof HTMLElement)) return;
  const queueUrl = tile.getAttribute("data-queue-url");
  if (!queueUrl || !(userCsrfToken instanceof HTMLInputElement)) return;

  const form = document.createElement("form");
  form.method = "post";
  form.action = queueUrl;
  form.style.display = "none";

  const csrf = document.createElement("input");
  csrf.type = "hidden";
  csrf.name = "csrf_token";
  csrf.value = userCsrfToken.value;
  form.appendChild(csrf);

  document.body.appendChild(form);
  form.submit();
}

if (songTilesEl) {
  songTilesEl.querySelectorAll(".song-tile").forEach((tile) => {
    setQueuedSongState(tile, tile.classList.contains("queued-song"));
    tile.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;

      const checkbox = tile.querySelector(".song-delete-checkbox");
      const inDeleteMode = songTilesEl.classList.contains("delete-mode");
      if (inDeleteMode) {
        if (target instanceof HTMLInputElement && target.classList.contains("song-delete-checkbox")) {
          updateDeleteSelectedState();
          return;
        }
        if (checkbox instanceof HTMLInputElement) {
          checkbox.checked = !checkbox.checked;
          updateDeleteSelectedState();
        }
        return;
      }

      if (target.closest("input,button,a,textarea,select,label")) return;
      queueSongFromTile(tile);
    });

    tile.addEventListener("keydown", (event) => {
      if (!(event instanceof KeyboardEvent)) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();

      const checkbox = tile.querySelector(".song-delete-checkbox");
      const inDeleteMode = songTilesEl.classList.contains("delete-mode");
      if (inDeleteMode) {
        if (checkbox instanceof HTMLInputElement) {
          checkbox.checked = !checkbox.checked;
          updateDeleteSelectedState();
        }
      } else {
        queueSongFromTile(tile);
      }
    });
  });
}

if (deleteModeToggle) {
  deleteModeToggle.addEventListener("change", () => {
    setDeleteMode(Boolean(deleteModeToggle.checked));
  });
}

if (bulkDeleteForm) {
  bulkDeleteForm.addEventListener("submit", (event) => {
    if (!(songTilesEl && deleteSelectedBtn)) return;
    const selected = songTilesEl.querySelectorAll(".song-delete-checkbox:checked").length;
    if (selected === 0) {
      event.preventDefault();
    }
  });
}

if (songTilesEl) {
  songTilesEl.querySelectorAll(".song-delete-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("change", updateDeleteSelectedState);
  });
}

if (bulkUploadToggle && bulkUploadPanel) {
  bulkUploadToggle.addEventListener("click", () => {
    const isHidden = bulkUploadPanel.hasAttribute("hidden");
    if (isHidden) {
      bulkUploadPanel.removeAttribute("hidden");
      bulkUploadToggle.setAttribute("aria-expanded", "true");
      bulkUploadToggle.textContent = "HIDE BULK UPLOAD";
    } else {
      bulkUploadPanel.setAttribute("hidden", "hidden");
      bulkUploadToggle.setAttribute("aria-expanded", "false");
      bulkUploadToggle.textContent = "SHOW BULK UPLOAD";
    }
  });
}

if (songTilesEl && window.io) {
  const socket = window.io();
  socket.on("queue_updated", (payload) => {
    const queuedIds = new Set();
    const items = [...(Array.isArray(payload?.queue_all) ? payload.queue_all : []), payload?.now_playing];
    for (const item of items) {
      if (item && item.song_id !== undefined && item.song_id !== null) {
        queuedIds.add(String(item.song_id));
      }
    }
    const playedIds = Array.isArray(payload?.played_song_ids) ? payload.played_song_ids : null;
    applyQueuedSongState(queuedIds, playedIds);
    window.dispatchEvent(new CustomEvent("karaoke:queue-updated", { detail: payload }));
  });
  socket.on("stage_state", (payload) => {
    window.dispatchEvent(new CustomEvent("karaoke:stage-state", { detail: payload }));
  });
}

setDeleteMode(false);
setupSavedSongs();
updateServiceUi();

