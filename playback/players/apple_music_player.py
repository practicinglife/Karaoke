"""Apple Music player automation (Phase 1 foundation)."""

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


class AppleMusicPlayer(BasePlayer):
    """Persistent Apple Music player wrapper with MiniPlayer awareness."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._window_manager = WindowManager()
        self._monitor_manager = MonitorManager(config)
        self._audio_monitor = AudioMonitor()
        self.mini_player_handle: int | None = None
        self._playing = False
        self._started_at = 0.0
        self._min_play_seconds = float(self.config.get("playback_controller", {}).get("min_play_seconds", 20))
        self._start_focus_grace_seconds = float(
            self.config.get("playback_controller", {}).get("apple_focus_start_grace_seconds", 2.5)
        )
        self._manual_open_mode = bool(self.config.get("playback_controller", {}).get("manual_player_launch", True))

    def _find_process_id(self) -> int | None:
        try:
            import psutil  # type: ignore

            for proc in psutil.process_iter(["name", "pid"]):
                name = str((proc.info.get("name") or "")).lower()
                if "applemusic" in name or "music" == name.replace(".exe", ""):
                    return int(proc.info["pid"])
        except Exception:
            return None
        return None

    def ensure_running(self) -> None:
        self.process_id = self._find_process_id()
        if self.process_id:
            return
        logger.info("Apple Music not detected. Launch remains external for Phase 1.")

    def discover(self) -> None:
        if not self.process_id:
            self.process_id = self._find_process_id()

        main = None
        if self.process_id:
            main = self._window_manager.find_window(process_id=self.process_id, title_contains=["apple music", "music"])
            if not main:
                main = self._window_manager.find_window(process_id=self.process_id)
        if not main:
            main = self._window_manager.find_window(title_contains=["apple music", "music"])

        if not main:
            logger.warning("Apple Music discover: window not found")
            return

        self.process_id = int(main.process_id)
        self.main_window_handle = main.hwnd

        mini = None
        if self.process_id:
            mini = self._window_manager.find_window(process_id=self.process_id, title_contains=["mini", "player"])
        if not mini:
            mini = self._window_manager.find_window(title_contains=["mini", "player", "apple music"])
        if mini:
            self.mini_player_handle = mini.hwnd
            self.playback_window_handle = mini.hwnd
        else:
            self.playback_window_handle = self.main_window_handle

        logger.info(
            "Apple discover: pid=%s main_hwnd=%s playback_hwnd=%s mini_hwnd=%s",
            self.process_id,
            self.main_window_handle,
            self.playback_window_handle,
            self.mini_player_handle,
        )

    def activate(self) -> None:
        hwnd = self.main_window_handle or self.playback_window_handle
        if not hwnd:
            return
        self._window_manager.restore_window(hwnd)
        self._window_manager.attach_input_and_focus(hwnd)

    def prepare(self, job: PlaybackJob) -> None:
        logger.info("Preparing Apple Music job queue_item_id=%s", job.queue_item_id)
        self.ensure_running()
        self.discover()
        self.activate()

    def load(self, job: PlaybackJob) -> None:
        if not job.path_or_url:
            raise ValueError("Apple Music playback job has no URL.")
        url_lower = job.path_or_url.lower()
        if "music.apple.com" not in url_lower and "itunes.apple.com" not in url_lower:
            raise ValueError("Apple Music URL must point to Apple Music or iTunes.")
        logger.info("Opening Apple Music web URL=%s", job.path_or_url)
        webbrowser.open(job.path_or_url)
        sleep(0.8)
        self.discover()
        self.activate()

    def select(self, job: PlaybackJob) -> None:
        logger.info("Selecting Apple Music title=%s artist=%s", job.title, job.artist)

    def start(self) -> None:
        logger.info("Starting Apple Music playback")
        self.activate()
        self._playing = True
        self._started_at = monotonic()

    def verify_started(self, job: PlaybackJob) -> bool:
        _ = job
        timeout = float(self.config.get("playback_controller", {}).get("playback_start_timeout_seconds", 12))
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            self.discover()
            hwnd = self.main_window_handle or self.playback_window_handle

            audio_active = self._audio_monitor.is_any_audio_active(["msedge.exe", "chrome.exe", "applemusic.exe", "music.exe"])
            if audio_active:
                logger.info("Apple Music verify_started success via audio activity")
                return True

            if self._manual_open_mode and hwnd:
                focused = self._window_manager.verify_foreground_window(hwnd)
                elapsed = max(0.0, monotonic() - self._started_at)
                if focused and elapsed >= self._start_focus_grace_seconds:
                    logger.warning(
                        "Apple Music verify_started fallback success via focused window (no audio detected). elapsed=%.2fs hwnd=%s",
                        elapsed,
                        hwnd,
                    )
                    return True

            sleep(0.25)

        self._playing = False
        logger.warning(
            "Apple Music start verification failed: no audio and no focused-window fallback (manual_mode=%s)",
            self._manual_open_mode,
        )
        return False

    def pause(self) -> None:
        logger.info("Pausing Apple Music playback")
        self._playing = False

    def stop(self) -> None:
        logger.info("Stopping Apple Music playback")
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

        if self._audio_monitor.is_any_audio_active(["msedge.exe", "chrome.exe", "applemusic.exe", "music.exe"]):
            return False

        self._playing = False
        return True

    def place_windows(self) -> None:
        operator = self._monitor_manager.get_operator_monitor()
        audience = self._monitor_manager.get_audience_monitor()

        if operator and self.main_window_handle:
            self._window_manager.move_to_monitor(self.main_window_handle, operator)

        mini_target = self.mini_player_handle or self.playback_window_handle
        if audience and mini_target:
            self._window_manager.fill_monitor(mini_target, audience)

    def capture_diagnostics(self) -> dict[str, Any]:
        return {
            "service": "apple_music",
            "process_id": self.process_id,
            "main_window_handle": self.main_window_handle,
            "mini_player_handle": self.mini_player_handle,
            "playback_window_handle": self.playback_window_handle,
        }

    def recover(self) -> None:
        self.ensure_running()
        self.discover()

    def shutdown(self) -> None:
        logger.info("Apple Music shutdown requested (no-op in persistent mode)")
