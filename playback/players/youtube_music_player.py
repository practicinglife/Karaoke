"""YouTube Music player automation (Phase 1 foundation)."""

from __future__ import annotations

import logging
import webbrowser
from time import monotonic, sleep
from typing import Any

from ..audio_monitor import AudioMonitor
from ..monitor_manager import MonitorManager
from ..playback_job import PlaybackJob
from ..window_manager import WindowManager
from .base_player import BasePlayer

logger = logging.getLogger(__name__)


class YouTubeMusicPlayer(BasePlayer):
    """Persistent browser-backed YouTube Music player wrapper."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._window_manager = WindowManager()
        self._monitor_manager = MonitorManager(config)
        self._audio_monitor = AudioMonitor()
        self._playing = False
        self._started_at = 0.0
        self._min_play_seconds = float(self.config.get("playback_controller", {}).get("min_play_seconds", 20))
        self._manual_open_mode = bool(self.config.get("playback_controller", {}).get("manual_player_launch", True))

    def _find_process_id(self) -> int | None:
        try:
            import psutil  # type: ignore

            candidates = {"msedge.exe", "chrome.exe"}
            for proc in psutil.process_iter(["name", "pid", "cmdline"]):
                name = str((proc.info.get("name") or "")).lower()
                cmd = " ".join(proc.info.get("cmdline") or []).lower()
                if name in candidates and "music.youtube.com" in cmd:
                    return int(proc.info["pid"])
            for proc in psutil.process_iter(["name", "pid"]):
                name = str((proc.info.get("name") or "")).lower()
                if name in candidates:
                    return int(proc.info["pid"])
        except Exception:
            return None
        return None

    def ensure_running(self) -> None:
        self.process_id = self._find_process_id()
        if self.process_id:
            return
        if self._manual_open_mode:
            logger.info("YouTube Music not detected and manual_player_launch is enabled; skipping auto-launch.")
            return
        logger.info("Launching YouTube Music browser shell")
        webbrowser.open("https://music.youtube.com")

    def discover(self) -> None:
        if not self.process_id:
            self.process_id = self._find_process_id()

        win = None
        if self.process_id:
            win = self._window_manager.find_window(
                process_id=self.process_id,
                title_contains=["youtube", "music"],
            )
        if not win:
            win = self._window_manager.find_window(title_contains=["youtube music", "youtube", "music"])
        if not win:
            return

        self.process_id = int(win.process_id)
        self.main_window_handle = win.hwnd
        self.playback_window_handle = win.hwnd

    def activate(self) -> None:
        if not self.main_window_handle:
            return
        self._window_manager.restore_window(self.main_window_handle)
        self._window_manager.attach_input_and_focus(self.main_window_handle)

    def prepare(self, job: PlaybackJob) -> None:
        logger.info("Preparing YouTube Music job queue_item_id=%s", job.queue_item_id)
        self.activate()

    def load(self, job: PlaybackJob) -> None:
        if not job.path_or_url:
            raise ValueError("YouTube Music playback job has no URL.")
        logger.info("Navigating YouTube Music URL=%s", job.path_or_url)
        webbrowser.open(job.path_or_url)
        sleep(0.8)
        self.discover()
        self.activate()

    def select(self, job: PlaybackJob) -> None:
        logger.info("Selecting YouTube Music title=%s artist=%s", job.title, job.artist)

    def start(self) -> None:
        logger.info("Starting YouTube Music playback")
        self.activate()
        self._playing = True
        self._started_at = monotonic()

    def verify_started(self, job: PlaybackJob) -> bool:
        _ = job
        timeout = float(self.config.get("playback_controller", {}).get("playback_start_timeout_seconds", 12))
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if self._audio_monitor.is_any_audio_active(["msedge.exe", "chrome.exe"]):
                return True
            sleep(0.25)
        self._playing = False
        logger.warning("YouTube Music start verification failed: no active audio detected")
        return False

    def pause(self) -> None:
        logger.info("Pausing YouTube Music playback")
        self._playing = False

    def stop(self) -> None:
        logger.info("Stopping YouTube Music playback")
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    def get_now_playing(self) -> tuple[str, str]:
        return "", ""

    def get_position(self) -> float:
        if not self._playing or self._started_at <= 0:
            return 0.0
        return max(0.0, monotonic() - self._started_at)

    def get_duration(self) -> float:
        return 0.0

    def has_finished(self) -> bool:
        if not self._playing:
            return True

        if self.get_position() < self._min_play_seconds:
            return False

        if self._audio_monitor.is_any_audio_active(["msedge.exe", "chrome.exe"]):
            return False

        self._playing = False
        return True

    def place_windows(self) -> None:
        audience = self._monitor_manager.get_audience_monitor()
        if audience and self.playback_window_handle:
            self._window_manager.fill_monitor(self.playback_window_handle, audience)

    def capture_diagnostics(self) -> dict[str, Any]:
        return {
            "service": "youtube_music",
            "process_id": self.process_id,
            "window_handle": self.playback_window_handle,
        }

    def recover(self) -> None:
        self.ensure_running()
        self.discover()

    def shutdown(self) -> None:
        logger.info("YouTube Music shutdown requested (no-op in persistent mode)")
