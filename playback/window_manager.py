"""Windows handle discovery and positioning helpers."""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from time import sleep
from typing import Any

from .monitor_manager import MonitorInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowInfo:
    """Top-level window metadata snapshot."""

    hwnd: int
    process_id: int
    title: str
    class_name: str
    visible: bool
    enabled: bool
    left: int
    top: int
    right: int
    bottom: int


class WindowManager:
    """Wrap pywin32 window operations with safe fallbacks."""

    def _import_win32(self):
        try:
            import win32con  # type: ignore
            import win32gui  # type: ignore
            import win32process  # type: ignore

            return win32con, win32gui, win32process
        except Exception:
            return None, None, None

    def enumerate_top_level_windows(self) -> list[WindowInfo]:
        """Enumerate top-level windows."""
        win32con, win32gui, win32process = self._import_win32()
        if not win32gui or not win32process:
            return []

        windows: list[WindowInfo] = []

        def callback(hwnd: int, _lparam: int) -> None:
            try:
                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                windows.append(
                    WindowInfo(
                        hwnd=int(hwnd),
                        process_id=int(process_id),
                        title=str(title),
                        class_name=str(class_name),
                        visible=bool(win32gui.IsWindowVisible(hwnd)),
                        enabled=bool(win32gui.IsWindowEnabled(hwnd)),
                        left=int(left),
                        top=int(top),
                        right=int(right),
                        bottom=int(bottom),
                    )
                )
            except Exception:
                return

        win32gui.EnumWindows(callback, 0)
        return windows

    def find_windows_by_process(self, process_id: int) -> list[WindowInfo]:
        """Find windows for specific process id."""
        return [w for w in self.enumerate_top_level_windows() if w.process_id == process_id]

    def find_window(
        self,
        *,
        process_id: int | None = None,
        title_contains: list[str] | None = None,
        class_contains: list[str] | None = None,
    ) -> WindowInfo | None:
        """Find first matching window with optional process/title/class filters."""
        titles = [item.lower() for item in (title_contains or []) if item]
        classes = [item.lower() for item in (class_contains or []) if item]

        for window in self.enumerate_top_level_windows():
            if process_id is not None and window.process_id != process_id:
                continue
            if titles and not any(token in window.title.lower() for token in titles):
                continue
            if classes and not any(token in window.class_name.lower() for token in classes):
                continue
            return window
        return None

    def validate_window_handle(self, hwnd: int) -> bool:
        """Validate if window handle exists and is usable."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return False
        try:
            return bool(win32gui.IsWindow(hwnd))
        except Exception:
            return False

    def get_window_process_id(self, hwnd: int) -> int | None:
        """Return process id for a window handle."""
        _, _, win32process = self._import_win32()
        if not win32process:
            return None
        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            return int(process_id)
        except Exception:
            return None

    def get_window_title(self, hwnd: int) -> str:
        """Return title for a window handle."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return ""
        try:
            return str(win32gui.GetWindowText(hwnd) or "")
        except Exception:
            return ""

    def get_window_class(self, hwnd: int) -> str:
        """Return class name for a window handle."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return ""
        try:
            return str(win32gui.GetClassName(hwnd) or "")
        except Exception:
            return ""

    def get_window_bounds(self, hwnd: int) -> tuple[int, int, int, int]:
        """Return window bounds."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return 0, 0, 0, 0
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            return int(left), int(top), int(right), int(bottom)
        except Exception:
            return 0, 0, 0, 0

    def restore_window(self, hwnd: int) -> bool:
        """Restore a minimized window."""
        win32con, win32gui, _ = self._import_win32()
        if not win32con or not win32gui:
            return False
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True
        except Exception:
            return False

    def focus_window(self, hwnd: int) -> bool:
        """Bring a window to foreground."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return False
        try:
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False

    def move_window(self, hwnd: int, left: int, top: int) -> bool:
        """Move a window while preserving size."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return False
        try:
            cur_left, cur_top, cur_right, cur_bottom = win32gui.GetWindowRect(hwnd)
            width = cur_right - cur_left
            height = cur_bottom - cur_top
            win32gui.MoveWindow(hwnd, left, top, width, height, True)
            return True
        except Exception:
            return False

    def resize_window(self, hwnd: int, left: int, top: int, width: int, height: int) -> bool:
        """Move and resize a window."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return False
        try:
            win32gui.MoveWindow(hwnd, left, top, width, height, True)
            return True
        except Exception:
            return False

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize a window."""
        win32con, win32gui, _ = self._import_win32()
        if not win32con or not win32gui:
            return False
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return True
        except Exception:
            return False

    def move_to_monitor(self, hwnd: int, monitor: MonitorInfo) -> bool:
        """Move a window to monitor origin."""
        return self.move_window(hwnd, monitor.left, monitor.top)

    def fill_monitor(self, hwnd: int, monitor: MonitorInfo) -> bool:
        """Resize a window to fill monitor bounds."""
        return self.resize_window(hwnd, monitor.left, monitor.top, monitor.width, monitor.height)

    def verify_foreground_window(self, hwnd: int) -> bool:
        """Verify target window owns foreground."""
        _, win32gui, _ = self._import_win32()
        if not win32gui:
            return False
        try:
            return int(win32gui.GetForegroundWindow()) == int(hwnd)
        except Exception:
            return False

    def attach_input_and_focus(self, hwnd: int) -> bool:
        """Attempt foreground focus for restricted windows."""
        return self.focus_window(hwnd)

    def send_virtual_key(self, hwnd: int, virtual_key: int) -> bool:
        """Send key down/up messages directly to target window."""
        win32con, win32gui, _ = self._import_win32()
        if not win32con or not win32gui:
            return False
        try:
            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, virtual_key, 0)
            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, virtual_key, 0)
            return True
        except Exception:
            return False

    def send_space_key(self, hwnd: int) -> bool:
        """Send SPACE key to target window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        return self.send_virtual_key(hwnd, int(win32con.VK_SPACE))

    def send_enter_key(self, hwnd: int) -> bool:
        """Send ENTER key to target window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        return self.send_virtual_key(hwnd, int(win32con.VK_RETURN))

    def send_media_play_pause_key(self, hwnd: int) -> bool:
        """Send MEDIA_PLAY_PAUSE key to target window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        virtual_key = int(getattr(win32con, "VK_MEDIA_PLAY_PAUSE", 0xB3))
        return self.send_virtual_key(hwnd, virtual_key)

    def send_global_virtual_key(self, virtual_key: int) -> bool:
        """Send global key down/up via user32 for focused-window fallback."""
        try:
            user32 = ctypes.windll.user32
            key_up_flag = 0x0002
            user32.keybd_event(int(virtual_key), 0, 0, 0)
            user32.keybd_event(int(virtual_key), 0, key_up_flag, 0)
            return True
        except Exception:
            return False

    def send_global_media_play_pause_key(self) -> bool:
        """Send MEDIA_PLAY_PAUSE globally to the current foreground window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        virtual_key = int(getattr(win32con, "VK_MEDIA_PLAY_PAUSE", 0xB3))
        return self.send_global_virtual_key(virtual_key)

    def send_global_space_key(self) -> bool:
        """Send SPACE globally to the current foreground window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        return self.send_global_virtual_key(int(win32con.VK_SPACE))

    def send_global_enter_key(self) -> bool:
        """Send ENTER globally to the current foreground window."""
        win32con, _, _ = self._import_win32()
        if not win32con:
            return False
        return self.send_global_virtual_key(int(win32con.VK_RETURN))

    def click_screen_point(self, x: int, y: int) -> bool:
        """Perform a left mouse click at absolute screen coordinates."""
        try:
            user32 = ctypes.windll.user32
            user32.SetCursorPos(int(x), int(y))
            left_down = 0x0002
            left_up = 0x0004
            user32.mouse_event(left_down, 0, 0, 0, 0)
            sleep(0.03)
            user32.mouse_event(left_up, 0, 0, 0, 0)
            return True
        except Exception:
            return False

    def click_window_relative_point(self, hwnd: int, offset_x: int, offset_y: int) -> bool:
        """Click a point relative to the target window top-left corner."""
        if not self.validate_window_handle(hwnd):
            return False
        left, top, _, _ = self.get_window_bounds(hwnd)
        return self.click_screen_point(int(left + offset_x), int(top + offset_y))

    def get_foreground_window_info(self) -> dict[str, Any]:
        """Return metadata for current foreground window."""
        _, win32gui, win32process = self._import_win32()
        if not win32gui or not win32process:
            return {}
        try:
            hwnd = int(win32gui.GetForegroundWindow())
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
            return {
                "hwnd": hwnd,
                "process_id": int(process_id),
                "title": str(win32gui.GetWindowText(hwnd) or ""),
                "class_name": str(win32gui.GetClassName(hwnd) or ""),
            }
        except Exception:
            return {}

    def get_window_monitor(
        self,
        hwnd: int,
        monitors: list[MonitorInfo],
    ) -> MonitorInfo | None:
        """Locate the monitor containing the window's top-left point."""
        left, top, _, _ = self.get_window_bounds(hwnd)
        for monitor in monitors:
            if monitor.left <= left < monitor.right and monitor.top <= top < monitor.bottom:
                return monitor
        return None

    def log_process_windows(self, process_id: int, logger_obj: logging.Logger | None = None) -> list[dict[str, Any]]:
        """Log all top-level windows for a process and return serialized data."""
        log = logger_obj or logger
        entries: list[dict[str, Any]] = []
        for window in self.find_windows_by_process(process_id):
            entry = {
                "hwnd": window.hwnd,
                "title": window.title,
                "class_name": window.class_name,
                "visible": window.visible,
                "enabled": window.enabled,
                "bounds": [window.left, window.top, window.right, window.bottom],
                "process_id": window.process_id,
            }
            entries.append(entry)
            log.info("Window pid=%s hwnd=%s title=%s class=%s", process_id, window.hwnd, window.title, window.class_name)
        return entries
