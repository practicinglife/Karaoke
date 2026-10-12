"""Map queued songs to stage-browser services and URLs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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


def normalize_stage_url(stage_service: str, url: str) -> str:
    """Links are opened exactly as saved.

    (Apple Music album links with ``?i=<track>`` already open that track's song page,
    so rewriting them is unnecessary.)
    """
    return url
