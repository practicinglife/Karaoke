"""Global "singer ready" hotkey.

Any cheap button that types a key works: USB foot pedal, wireless presenter clicker,
Bluetooth camera-shutter remote. The hook is global, so it fires no matter which
window has focus.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)


class ReadyHotkey:
    def __init__(self) -> None:
        self._handle = None

    def register(self, key: str, callback: Callable[[], object]) -> bool:
        self.unregister()
        try:
            import keyboard
        except ImportError:
            logger.warning("Ready hotkey disabled: pip install keyboard")
            return False
        try:
            self._handle = keyboard.add_hotkey(key, callback)
        except Exception:
            logger.exception("Could not register ready hotkey %r", key)
            return False
        logger.info("Ready hotkey registered: %s", key)
        return True

    def unregister(self) -> None:
        if self._handle is None:
            return
        try:
            import keyboard

            keyboard.remove_hotkey(self._handle)
        except Exception:
            pass
        self._handle = None
