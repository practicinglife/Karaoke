"""Diagnostics helpers for controller environment discovery."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config import LOG_DIR
from .audio_monitor import AudioMonitor
from .monitor_manager import MonitorManager
from .window_manager import WindowManager


def build_diagnostics_payload(
    monitor_manager: MonitorManager,
    window_manager: WindowManager,
    audio_monitor: AudioMonitor,
) -> dict[str, Any]:
    """Build monitor/window/audio diagnostics payload."""
    monitors = [asdict(monitor) for monitor in monitor_manager.get_monitors()]
    windows = [asdict(window) for window in window_manager.enumerate_top_level_windows()]
    sessions = [asdict(session) for session in audio_monitor.enumerate_audio_sessions()]
    return {
        "monitors": monitors,
        "windows": windows,
        "audio_sessions": sessions,
    }


def save_diagnostics(payload: dict[str, Any], target: Path | None = None) -> Path:
    """Persist diagnostics payload to JSON file."""
    path = target or (LOG_DIR / "window_diagnostics.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
