"""Audio session inspection helpers for playback verification."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioSessionInfo:
    """Audio session snapshot."""

    process_id: int
    process_name: str
    state: str
    peak_level: float


class AudioMonitor:
    """Provide pycaw-backed audio session checks with safe fallback."""

    def _import_pycaw(self):
        try:
            from pycaw.pycaw import AudioUtilities  # type: ignore

            return AudioUtilities
        except Exception:
            return None

    def enumerate_audio_sessions(self) -> list[AudioSessionInfo]:
        """Enumerate current audio sessions."""
        audio_utilities = self._import_pycaw()
        if not audio_utilities:
            return []

        sessions: list[AudioSessionInfo] = []
        try:
            for session in audio_utilities.GetAllSessions():
                process = session.Process
                process_id = int(process.pid) if process else 0
                process_name = str(process.name()) if process else ""
                state = str(getattr(session, "State", "Unknown"))
                peak = 0.0
                meter = getattr(session, "SimpleAudioVolume", None)
                if meter is not None:
                    try:
                        peak = float(meter.GetMasterVolume())
                    except Exception:
                        peak = 0.0
                sessions.append(
                    AudioSessionInfo(
                        process_id=process_id,
                        process_name=process_name,
                        state=state,
                        peak_level=peak,
                    )
                )
        except Exception:
            return []
        return sessions

    def get_session_for_process(self, process_name: str) -> AudioSessionInfo | None:
        """Get first audio session by process name."""
        wanted = process_name.lower().strip()
        for session in self.enumerate_audio_sessions():
            if session.process_name.lower() == wanted:
                return session
        return None

    def is_audio_active(self, process_name: str, threshold: float = 0.001) -> bool:
        """Check whether process has active audio session volume."""
        session = self.get_session_for_process(process_name)
        if not session:
            return False
        return session.peak_level > threshold

    def is_any_audio_active(self, process_names: list[str], threshold: float = 0.001) -> bool:
        """Check whether any process in list has active audio output."""
        wanted = {name.lower().strip() for name in process_names if name}
        if not wanted:
            return False
        for session in self.enumerate_audio_sessions():
            if session.process_name.lower() in wanted and session.peak_level > threshold:
                return True
        return False

    def get_peak_level(self, process_name: str) -> float:
        """Get process peak level."""
        session = self.get_session_for_process(process_name)
        return session.peak_level if session else 0.0

    def wait_for_audio_start(self, process_name: str, timeout_seconds: float = 5.0) -> bool:
        """Wait for audio activation within timeout."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.is_audio_active(process_name):
                return True
            time.sleep(0.1)
        return False

    def wait_for_audio_stop(self, process_name: str, timeout_seconds: float = 5.0) -> bool:
        """Wait for audio inactivity within timeout."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.is_audio_active(process_name):
                return True
            time.sleep(0.1)
        return False
