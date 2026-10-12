"""Map queued songs to stage-browser services and URLs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SELECTORS_PATH = Path(__file__).resolve().parent / "selectors.json"
STREAMING_SERVICES = {"youtube", "spotify", "apple_music"}


def overrides_path() -> Path:
    """Per-machine steps recorded in Teach mode (kept outside the app folder)."""
    from config import DATA_DIR

    return Path(DATA_DIR) / "stage_selectors.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_selectors(path: Path | None = None, overrides: Path | None = None) -> dict[str, Any]:
    """Built-in per-service definitions, with Teach-mode overrides merged per service."""
    data = _read_json(path or SELECTORS_PATH)
    for service, values in _read_json(overrides or overrides_path()).items():
        if isinstance(values, dict) and isinstance(data.get(service), dict):
            data[service] = {**data[service], **values}
    return {key: value for key, value in data.items() if not key.startswith("_")}


def save_taught_steps(service: str, steps: list[dict[str, Any]], overrides: Path | None = None) -> Path:
    """Store steps recorded in Teach mode for one service."""
    target = overrides or overrides_path()
    data = _read_json(target)
    data[service] = {"steps": steps}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return target


SERVICE_NAMES = {
    "apple_music": "Apple Music",
    "spotify": "Spotify",
    "youtube": "YouTube",
    "youtube_music": "YouTube Music",
    "traditional": "Traditional karaoke",
}


def taught_services(overrides: Path | None = None) -> list[dict[str, Any]]:
    """Services with Teach-mode steps on this computer (these replay automatically)."""
    data = _read_json(overrides or overrides_path())
    return [
        {"service": key, "name": SERVICE_NAMES.get(key, key), "steps": len(value.get("steps", []))}
        for key, value in sorted(data.items())
        if isinstance(value, dict) and value.get("steps")
    ]


def forget_taught_steps(service: str, overrides: Path | None = None) -> None:
    """Go back to the built-in steps for a service."""
    target = overrides or overrides_path()
    data = _read_json(target)
    if data.pop(service, None) is not None:
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")


def stage_service_for(service: str, url: str | None) -> str | None:
    """Return the selectors.json key for a saved song, or None if the stage can't play it."""
    if service == "traditional":
        return "traditional"
    if service not in STREAMING_SERVICES or not url:
        return None
    if service == "youtube" and (urlparse(url).hostname or "").lower() == "music.youtube.com":
        return "youtube_music"
    return service


_APPLE_SONG_PATH = re.compile(r"^/([a-z]{2})/song/(?:[^/]+/)?(\d+)/?$")
_apple_album_cache: dict[str, str] = {}


def apple_album_link(url: str, fetch=None) -> str:
    """Turn an Apple Music song-page link into its album link with the track highlighted.

    Song pages (``/us/song/<name>/<id>``) have no track row to click, only a header button
    whose label varies, while album links (``/album/<name>/<album>?i=<id>``) highlight the
    track and give it its own Play button. The song page names its album link; if it can't
    be fetched, the original link is used.
    """
    parsed = urlparse(url)
    match = _APPLE_SONG_PATH.match(parsed.path)
    if not match:
        return url
    if url in _apple_album_cache:
        return _apple_album_cache[url]
    country, song_id = match.groups()
    try:
        html = (fetch or _fetch_text)(url)
    except Exception:
        return url
    found = re.search(rf"https://music\.apple\.com/{country}/album/[a-z0-9-]+/\d+\?i={song_id}", html)
    resolved = found.group(0) if found else url
    _apple_album_cache[url] = resolved
    return resolved


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edg/141.0"})
    with urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", "ignore")


def normalize_stage_url(stage_service: str, url: str) -> str:
    """Links are opened as saved, except Apple Music song-page links (see apple_album_link)."""
    if stage_service == "apple_music":
        return apple_album_link(url)
    return url
