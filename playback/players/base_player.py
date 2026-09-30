"""Base player interface for all playback providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..playback_job import PlaybackJob


class BasePlayer(ABC):
    """Abstract playback player contract."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.process_id: int | None = None
        self.main_window_handle: int | None = None
        self.playback_window_handle: int | None = None

    @abstractmethod
    def ensure_running(self) -> None:
        """Ensure player process exists, launching if needed."""

    @abstractmethod
    def discover(self) -> None:
        """Discover process and primary windows."""

    @abstractmethod
    def activate(self) -> None:
        """Bring main player window into focus."""

    @abstractmethod
    def prepare(self, job: PlaybackJob) -> None:
        """Prepare player context for a job before loading."""

    @abstractmethod
    def load(self, job: PlaybackJob) -> None:
        """Load the target media represented by the job."""

    @abstractmethod
    def select(self, job: PlaybackJob) -> None:
        """Select exact song/media entry for the job."""

    @abstractmethod
    def start(self) -> None:
        """Start playback."""

    @abstractmethod
    def verify_started(self, job: PlaybackJob) -> bool:
        """Verify playback started for expected media."""

    @abstractmethod
    def pause(self) -> None:
        """Pause playback."""

    @abstractmethod
    def stop(self) -> None:
        """Stop playback."""

    @abstractmethod
    def is_playing(self) -> bool:
        """Return true when player is actively playing media."""

    @abstractmethod
    def get_now_playing(self) -> tuple[str, str]:
        """Return now playing title and artist if available."""

    @abstractmethod
    def get_position(self) -> float:
        """Return playback position in seconds."""

    @abstractmethod
    def get_duration(self) -> float:
        """Return track duration in seconds."""

    @abstractmethod
    def has_finished(self) -> bool:
        """Return true if current media has ended."""

    @abstractmethod
    def place_windows(self) -> None:
        """Place and size windows on configured monitors."""

    @abstractmethod
    def capture_diagnostics(self) -> dict[str, Any]:
        """Capture player process/window diagnostics."""

    @abstractmethod
    def recover(self) -> None:
        """Recover from transient automation failure."""

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown player only on full app exit."""
