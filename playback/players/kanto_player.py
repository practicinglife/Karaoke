"""Kanto karaoke player automation (Phase 1 foundation)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from time import monotonic, sleep
from typing import Any

from karaoke.launcher import launch_traditional_song

from ..audio_monitor import AudioMonitor
from ..monitor_manager import MonitorManager
from ..playback_job import PlaybackJob
from ..window_manager import WindowManager
from .base_player import BasePlayer

logger = logging.getLogger(__name__)


class KantoPlayer(BasePlayer):
    """Persistent Kanto player wrapper."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._window_manager = WindowManager()
        self._monitor_manager = MonitorManager(config)
        self._audio_monitor = AudioMonitor()
        self._last_position = 0.0
        self._playing = False
        self._started_at = 0.0
        self._min_play_seconds = float(self.config.get("playback_controller", {}).get("min_play_seconds", 20))
        self._start_focus_grace_seconds = float(
            self.config.get("playback_controller", {}).get("kanto_focus_start_grace_seconds", 2.5)
        )
        self._manual_open_mode = bool(self.config.get("playback_controller", {}).get("manual_player_launch", True))
        self._last_audio_seen_at = 0.0
        self._recorded_step_delay_seconds = float(
            self.config.get("playback_controller", {}).get("kanto_recorded_step_delay_seconds", 0.12)
        )
        self._play_step_sequence: list[dict[str, Any]] = list(
            self.config.get("playback_controller", {}).get("kanto_play_step_sequence")
            or [
                {"type": "screen", "x": 1211, "y": 1051, "delay": 0.05},
                {"type": "screen", "x": 970, "y": 737, "delay": 0.15},
            ]
        )
        self._stop_step_sequence: list[dict[str, Any]] = list(
            self.config.get("playback_controller", {}).get("kanto_stop_step_sequence")
            or [
                {"type": "screen", "x": 1211, "y": 1051, "delay": 0.05},
                {"type": "screen", "x": 905, "y": 736, "delay": 0.15},
            ]
        )

    def _find_process_id(self) -> int | None:
        try:
            import psutil  # type: ignore

            configured_exe = str(self._get_configured_executable() or "").strip().lower()
            configured_name = Path(configured_exe).name if configured_exe else ""
            preferred_names = {
                "kanto.exe",
                "kantokaraoke.exe",
                "kantoplayer.exe",
                "karaoke player.exe",
                "karaoke.exe",
            }
            if configured_name:
                preferred_names.add(configured_name)

            for proc in psutil.process_iter(["name", "pid", "exe"]):
                name = str((proc.info.get("name") or "")).lower()
                exe = str((proc.info.get("exe") or "")).lower()
                exe_name = Path(exe).name if exe else ""
                if name in preferred_names or exe_name in preferred_names:
                    return int(proc.info["pid"])
                if configured_exe and (exe == configured_exe or exe_name == configured_name):
                    return int(proc.info["pid"])
                if "kanto" in name or "kanto" in exe_name or "kanto" in exe:
                    return int(proc.info["pid"])

            for window in self._window_manager.enumerate_top_level_windows():
                title = (window.title or "").lower()
                if "karaoke ticker" in title or "admin" in title:
                    continue
                if "kanto" in title or "karaoke player" in title:
                    return int(window.process_id)
        except Exception:
            return None
        return None

    def _get_configured_executable(self) -> str:
        kanto_config = self.config.get("kanto", {})
        playback_config = self.config.get("playback_controller", {})
        return str(
            kanto_config.get("executable")
            or playback_config.get("kanto_executable_path")
            or ""
        ).strip()

    def ensure_running(self) -> None:
        self.process_id = self._find_process_id()
        if self.process_id:
            return

        if self._manual_open_mode:
            logger.warning("Kanto not detected and manual_player_launch is enabled; waiting for manual app start.")
            return

        executable = self._get_configured_executable()
        if executable:
            exe = Path(executable)
            if not exe.exists():
                logger.warning("Kanto executable path not found: %s", executable)
                return

            subprocess.Popen([str(exe)], shell=False)  # noqa: S603
            deadline = monotonic() + 10.0
            while monotonic() < deadline:
                self.process_id = self._find_process_id()
                if self.process_id:
                    return
                sleep(0.2)

            logger.warning("Kanto executable launched but process was not detected: %s", executable)
            return

        logger.info("Kanto executable not configured; skipping auto-launch.")

    def discover(self) -> None:
        if not self.process_id:
            self.process_id = self._find_process_id()
        if not self.process_id:
            logger.warning("Kanto discover: process not found")
            return

        main = self._window_manager.find_window(process_id=self.process_id, title_contains=["kanto", "player"])
        if not main:
            main = self._window_manager.find_window(process_id=self.process_id)
        if main:
            self.main_window_handle = main.hwnd

        playback = self._window_manager.find_window(
            process_id=self.process_id,
            title_contains=["lyrics", "kanto", "player"],
        )
        self.playback_window_handle = playback.hwnd if playback else self.main_window_handle
        logger.info(
            "Kanto discover: pid=%s main_hwnd=%s playback_hwnd=%s",
            self.process_id,
            self.main_window_handle,
            self.playback_window_handle,
        )

    def activate(self) -> None:
        hwnd = self.main_window_handle or self.playback_window_handle
        if not hwnd:
            logger.warning("Kanto activate skipped: no discovered window handle")
            return
        self._window_manager.restore_window(hwnd)
        focused = self._window_manager.attach_input_and_focus(hwnd)
        logger.info("Kanto activate: hwnd=%s focused=%s", hwnd, focused)

    def prepare(self, job: PlaybackJob) -> None:
        logger.info("Preparing Kanto job queue_item_id=%s", job.queue_item_id)
        self.activate()

    def load(self, job: PlaybackJob) -> None:
        logger.info("Loading Kanto media path=%s", job.path_or_url)
        if not job.path_or_url:
            raise ValueError("Kanto playback job has no local file path.")
        launch_traditional_song(job.path_or_url, self._get_configured_executable())
        self.discover()
        self.activate()

    def select(self, job: PlaybackJob) -> None:
        logger.info("Selecting Kanto media title=%s artist=%s", job.title, job.artist)

    def _execute_step_sequence(self, sequence_name: str, steps: list[dict[str, Any]]) -> bool:
        """Replay configured click steps for Kanto controls."""
        if not steps:
            return False

        any_success = False
        for index, step in enumerate(steps, start=1):
            step_type = str(step.get("type") or "screen").strip().lower()
            delay_seconds = float(step.get("delay", self._recorded_step_delay_seconds))
            if delay_seconds > 0:
                sleep(delay_seconds)

            if step_type == "screen":
                x = int(step.get("x", 0))
                y = int(step.get("y", 0))
                ok = self._window_manager.click_screen_point(x, y)
                logger.info(
                    "Kanto step sequence=%s index=%s type=screen x=%s y=%s ok=%s",
                    sequence_name,
                    index,
                    x,
                    y,
                    ok,
                )
                any_success = any_success or ok
                continue

            if step_type == "window_relative":
                target = str(step.get("target") or "playback").strip().lower()
                hwnd = self.playback_window_handle if target == "playback" else self.main_window_handle
                x = int(step.get("x", 0))
                y = int(step.get("y", 0))
                ok = bool(hwnd) and self._window_manager.click_window_relative_point(int(hwnd), x, y)
                logger.info(
                    "Kanto step sequence=%s index=%s type=window_relative target=%s hwnd=%s x=%s y=%s ok=%s",
                    sequence_name,
                    index,
                    target,
                    hwnd,
                    x,
                    y,
                    ok,
                )
                any_success = any_success or ok
                continue

            logger.warning("Kanto step sequence=%s index=%s unsupported step type=%s", sequence_name, index, step_type)

        return any_success

    def _send_start_inputs(self, reason: str) -> bool:
        """Send start inputs using media-play, direct keys, global fallback, and recorded clicks."""
        handles: list[int] = []
        if self.playback_window_handle:
            handles.append(int(self.playback_window_handle))
        if self.main_window_handle and self.main_window_handle not in handles:
            handles.append(int(self.main_window_handle))

        foreground = self._window_manager.get_foreground_window_info()
        logger.info("Kanto start input reason=%s foreground=%s", reason, foreground)

        sent_any = False
        for hwnd in handles:
            sent_play = self._window_manager.send_media_play_pause_key(hwnd)
            sent_space = self._window_manager.send_space_key(hwnd)
            sent_enter = self._window_manager.send_enter_key(hwnd)
            logger.info(
                "Kanto start key send reason=%s hwnd=%s sent_play=%s sent_space=%s sent_enter=%s",
                reason,
                hwnd,
                sent_play,
                sent_space,
                sent_enter,
            )
            sent_any = sent_any or sent_play or sent_space or sent_enter

        global_play = self._window_manager.send_global_media_play_pause_key()
        global_space = self._window_manager.send_global_space_key()
        global_enter = self._window_manager.send_global_enter_key()
        logger.info(
            "Kanto start global key send reason=%s sent_play=%s sent_space=%s sent_enter=%s",
            reason,
            global_play,
            global_space,
            global_enter,
        )
        sent_any = sent_any or global_play or global_space or global_enter

        clicked = self._execute_step_sequence(f"{reason}-play", self._play_step_sequence)
        return sent_any or clicked

    def start(self) -> None:
        logger.info("Starting Kanto playback")
        self.activate()
        sent = self._send_start_inputs("initial")
        if not sent:
            logger.warning("Kanto start: no key/click input path succeeded")

        self._playing = True
        self._started_at = monotonic()

    def verify_started(self, job: PlaybackJob) -> bool:
        _ = job
        timeout = float(self.config.get("playback_controller", {}).get("playback_start_timeout_seconds", 12))
        deadline = monotonic() + timeout
        retry_triggered = False
        while monotonic() < deadline:
            self.discover()
            hwnd = self.main_window_handle or self.playback_window_handle
            elapsed = max(0.0, monotonic() - self._started_at)

            audio_active = self._audio_monitor.is_any_audio_active(
                [
                    "kanto.exe",
                    "kantokaraoke.exe",
                    "kanto karaoke player.exe",
                    "karaoke player.exe",
                    "karaoke.exe",
                ]
            )
            if audio_active:
                self._last_audio_seen_at = monotonic()
                logger.info("Kanto verify_started success via audio activity")
                return True

            if not retry_triggered and elapsed >= 1.8:
                retry_triggered = True
                logger.warning("Kanto verify_started retrying start inputs")
                self.activate()
                self._send_start_inputs("verify-retry")

            if self._manual_open_mode and hwnd:
                focused = self._window_manager.verify_foreground_window(hwnd)
                valid_window = self._window_manager.validate_window_handle(hwnd)
                if (focused or valid_window) and elapsed >= self._start_focus_grace_seconds:
                    logger.warning(
                        "Kanto verify_started fallback success via window detection (focused=%s valid=%s no-audio). elapsed=%.2fs hwnd=%s",
                        focused,
                        valid_window,
                        elapsed,
                        hwnd,
                    )
                    return True

            sleep(0.25)

        if self._manual_open_mode:
            self.discover()
            hwnd = self.main_window_handle or self.playback_window_handle
            if hwnd and self._window_manager.validate_window_handle(hwnd):
                logger.warning(
                    "Kanto verify_started fallback accepted in manual mode: valid window detected after timeout. hwnd=%s",
                    hwnd,
                )
                return True

        self._playing = False
        logger.warning(
            "Kanto start verification failed: no audio/window confirmation (manual_mode=%s)",
            self._manual_open_mode,
        )
        return False

    def pause(self) -> None:
        logger.info("Pausing Kanto playback")
        self._playing = False

    def stop(self) -> None:
        logger.info("Stopping Kanto playback")
        self.activate()
        self._execute_step_sequence("stop", self._stop_step_sequence)
        self._playing = False

    def is_playing(self) -> bool:
        if not self._playing:
            return False
        return True

    def get_now_playing(self) -> tuple[str, str]:
        return "", ""

    def get_position(self) -> float:
        if not self._playing or self._started_at <= 0:
            return self._last_position
        self._last_position = max(0.0, monotonic() - self._started_at)
        return self._last_position

    def get_duration(self) -> float:
        return 0.0

    def has_finished(self) -> bool:
        if not self._playing:
            return True

        elapsed = self.get_position()
        if elapsed < self._min_play_seconds:
            return False

        audio_active = self._audio_monitor.is_any_audio_active(
            ["kanto.exe", "kantokaraoke.exe", "kanto karaoke player.exe", "karaoke player.exe", "karaoke.exe"]
        )
        if audio_active:
            self._last_audio_seen_at = monotonic()
            return False

        if self._manual_open_mode:
            self.discover()
            hwnd = self.main_window_handle or self.playback_window_handle
            if hwnd and self._window_manager.validate_window_handle(hwnd):
                return False

        self._playing = False
        return True

    def place_windows(self) -> None:
        operator = self._monitor_manager.get_operator_monitor()
        audience = self._monitor_manager.get_audience_monitor()
        if operator and self.main_window_handle:
            self._window_manager.move_to_monitor(self.main_window_handle, operator)
        if audience and self.playback_window_handle:
            self._window_manager.fill_monitor(self.playback_window_handle, audience)

    def capture_diagnostics(self) -> dict[str, Any]:
        return {
            "service": "kanto",
            "process_id": self.process_id,
            "main_window_handle": self.main_window_handle,
            "playback_window_handle": self.playback_window_handle,
        }

    def recover(self) -> None:
        self.ensure_running()
        self.discover()

    def shutdown(self) -> None:
        logger.info("Kanto shutdown requested (no-op in persistent mode)")
