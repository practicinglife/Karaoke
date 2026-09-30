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
const paginationEl = document.getElementById("search-pagination");
const prevBtn = document.getElementById("search-prev");
const nextBtn = document.getElementById("search-next");
const pageLabel = document.getElementById("search-page-label");
const deleteModeToggle = document.getElementById("delete-mode-toggle");
const songTilesEl = document.getElementById("song-tiles");
const deleteSelectedBtn = document.getElementById("delete-selected-btn");
const bulkDeleteForm = document.getElementById("bulk-delete-form");
const userCsrfToken = document.getElementById("user-csrf-token");
const bulkUploadToggle = document.getElementById("bulk-upload-toggle");
const bulkUploadPanel = document.getElementById("bulk-upload-panel");

const PAGE_SIZE = 60;
const SEARCH_LIMIT = 120;
let currentResults = [];
let currentPage = 1;
let searchController = null;
let lastSearchQuery = "";
let userQueueNotificationTimer = null;
let lastUserQueueNotificationKey = "none||";

const QUEUED_SONG_ARIA_SUFFIX = ", queued tonight, click again to remove from queue";
const UP_NEXT_NOTIFICATION_TEXT = "UP NEXT!!";
const UP_NOW_NOTIFICATION_TEXT = "UP NOW!!";
const VIDEO_EXTENSIONS = new Set([".mp4", ".mkv", ".avi", ".wmv"]);

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

function applyQueuedSongState(queuedIds) {
  if (!songTilesEl) return;
  const normalized = new Set(Array.from(queuedIds, (value) => String(value)));
  songTilesEl.querySelectorAll(".song-tile").forEach((tile) => {
    const songId = tile.getAttribute("data-song-id") || "";
    setQueuedSongState(tile, normalized.has(songId));
  });
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
  currentResults = [];
  currentPage = 1;
  resultsEl.innerHTML = "";
  if (paginationEl) {
    paginationEl.style.display = "none";
  }
  if (pageLabel) {
    pageLabel.textContent = "";
  }
}

function formatTraditionalResultLabel(row) {
  const extension = String(row?.extension || "").toLowerCase();
  const suffix = VIDEO_EXTENSIONS.has(extension) ? " [VIDEO]" : "";
  return `${row.display_name}${suffix}`;
}

function renderCurrentSearchPage() {
  const totalMatches = currentResults.length;
  const totalPages = Math.max(1, Math.ceil(totalMatches / PAGE_SIZE));

  if (currentPage < 1) currentPage = 1;
  if (currentPage > totalPages) currentPage = totalPages;

  resultsEl.innerHTML = "";

  if (!totalMatches) {
    const li = document.createElement("li");
    li.textContent = "No matching song was found in the indexed karaoke library.";
    resultsEl.appendChild(li);
    if (paginationEl) paginationEl.style.display = "none";
    return;
  }

  const start = (currentPage - 1) * PAGE_SIZE;
  const end = Math.min(start + PAGE_SIZE, totalMatches);
  const pageRows = currentResults.slice(start, end);

  const info = document.createElement("li");
  info.textContent = `Showing ${start + 1}-${end} of ${totalMatches} tracks`;
  resultsEl.appendChild(info);

  for (const row of pageRows) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `SELECT: ${formatTraditionalResultLabel(row)}`;
    btn.onclick = () => {
      karaokeLibraryId.value = String(row.id || "");
      btn.textContent = `SELECTED: ${formatTraditionalResultLabel(row)}`;
      if (titleInput) {
        titleInput.value = row.title || "";
      }
      if (artistInput) {
        artistInput.value = row.artist || "";
      }
    };
    li.appendChild(btn);
    resultsEl.appendChild(li);
  }

  if (paginationEl) {
    paginationEl.style.display = totalPages > 1 ? "block" : "none";
  }
  if (pageLabel) {
    pageLabel.textContent = `Page ${currentPage} of ${totalPages}`;
  }
  if (prevBtn) {
    prevBtn.disabled = currentPage <= 1;
  }
  if (nextBtn) {
    nextBtn.disabled = currentPage >= totalPages;
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
    const response = await fetch(
      `/song/search?service=traditional&q=${encodeURIComponent(q)}&limit=${SEARCH_LIMIT}`,
      { cache: "no-cache", signal: searchController.signal }
    );
    if (!response.ok) {
      clearSearchResults();
      const li = document.createElement("li");
      li.textContent = "Search unavailable. Try again.";
      resultsEl.appendChild(li);
      return;
    }

    const items = await response.json();
    currentResults = Array.isArray(items) ? items : [];
    currentPage = 1;
    renderCurrentSearchPage();
  } catch (_error) {
    if (_error && _error.name === "AbortError") {
      return;
    }
    clearSearchResults();
    const li = document.createElement("li");
    li.textContent = "Search unavailable. Try again.";
    resultsEl.appendChild(li);
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
if (prevBtn) {
  prevBtn.addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage -= 1;
      renderCurrentSearchPage();
    }
  });
}
if (nextBtn) {
  nextBtn.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(currentResults.length / PAGE_SIZE));
    if (currentPage < totalPages) {
      currentPage += 1;
      renderCurrentSearchPage();
    }
  });
}

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
    if (payload && Array.isArray(payload.queue_all)) {
      for (const item of payload.queue_all) {
        if (item && item.song_id !== undefined && item.song_id !== null) {
          queuedIds.add(String(item.song_id));
        }
      }
    }
    applyQueuedSongState(queuedIds);
    window.dispatchEvent(new CustomEvent("karaoke:queue-updated", { detail: payload }));
  });
}

setDeleteMode(false);
updateServiceUi();

