"""Controller event dispatch helpers for Socket.IO and logs."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Dispatch controller events to Socket.IO when available."""

    def __init__(self, socketio: Any | None = None) -> None:
        self._socketio = socketio

    def emit(self, event_name: str, payload: dict[str, Any]) -> None:
        """Emit event safely with logging fallback."""
        if self._socketio is None:
            logger.info("Playback event %s: %s", event_name, payload)
            return
        try:
            self._socketio.emit(event_name, payload)
        except Exception as exc:
            logger.warning("Failed to emit event %s: %s", event_name, exc)
