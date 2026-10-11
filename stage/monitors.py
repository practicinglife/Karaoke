"""Find monitor rectangles so the stage window opens on the audience screen."""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)


def list_monitors() -> list[tuple[int, int, int, int]]:
    """Return (left, top, width, height) per monitor, primary first. Windows only."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes

    rects: list[tuple[int, int, int, int, bool]] = []

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def callback(hmonitor, _hdc, _rect, _data) -> int:
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            r = info.rcMonitor
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top, bool(info.dwFlags & 1)))
        return 1

    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, callback_type(callback), 0)
    except Exception:
        logger.exception("Could not enumerate monitors")
        return []
    rects.sort(key=lambda r: (not r[4], r[0], r[1]))
    return [r[:4] for r in rects]


def monitor_rect(monitor: int) -> tuple[int, int, int, int] | None:
    """Rectangle of monitor N (1 = primary); falls back to the primary monitor."""
    monitors = list_monitors()
    if not monitors:
        return None
    return monitors[monitor - 1] if 1 <= monitor <= len(monitors) else monitors[0]


def describe_monitors() -> list[dict[str, object]]:
    """Monitor choices for settings/admin dropdowns."""
    return [
        {
            "number": index,
            "label": f"Screen {index}: {width}x{height}" + (" (main)" if index == 1 else ""),
        }
        for index, (_left, _top, width, height) in enumerate(list_monitors(), start=1)
    ]
