"""Monitor discovery and placement helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class MonitorInfo:
    """Connected monitor metadata."""

    device_name: str
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    is_primary: bool = False


class MonitorManager:
    """Provide monitor enumeration and lookup helpers."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def _get_default_monitor(self) -> MonitorInfo:
        return MonitorInfo(
            device_name="UNKNOWN",
            left=0,
            top=0,
            right=1920,
            bottom=1080,
            width=1920,
            height=1080,
            is_primary=True,
        )

    def get_monitors(self) -> list[MonitorInfo]:
        """Enumerate connected monitors using available backends."""
        monitors: list[MonitorInfo] = []
        try:
            from screeninfo import get_monitors  # type: ignore

            for monitor in get_monitors():
                name = str(getattr(monitor, "name", "") or "")
                if not name:
                    name = f"DISPLAY:{monitor.x}:{monitor.y}:{monitor.width}x{monitor.height}"
                monitors.append(
                    MonitorInfo(
                        device_name=name,
                        left=int(monitor.x),
                        top=int(monitor.y),
                        right=int(monitor.x + monitor.width),
                        bottom=int(monitor.y + monitor.height),
                        width=int(monitor.width),
                        height=int(monitor.height),
                        is_primary=bool(getattr(monitor, "is_primary", False)),
                    )
                )
        except Exception:
            pass

        if monitors:
            return monitors

        return [
            MonitorInfo(
                device_name="UNKNOWN",
                left=0,
                top=0,
                right=1920,
                bottom=1080,
                width=1920,
                height=1080,
                is_primary=True,
            )
        ]

    def get_monitor_by_device_name(self, device_name: str) -> MonitorInfo | None:
        """Find monitor by configured device name."""
        for monitor in self.get_monitors():
            if monitor.device_name.lower() == device_name.lower():
                return monitor
        return None

    def get_operator_monitor(self) -> MonitorInfo | None:
        """Return configured operator monitor."""
        key = str(self._config.get("monitors", {}).get("operator", "")).strip()
        if key:
            found = self.get_monitor_by_device_name(key)
            if found:
                return found
        return self.get_monitors()[0] if self.get_monitors() else None

    def get_audience_monitor(self) -> MonitorInfo | None:
        """Return configured audience monitor."""
        key = str(self._config.get("monitors", {}).get("audience", "")).strip()
        if key:
            return self.get_monitor_by_device_name(key)
        monitors = self.get_monitors()
        if len(monitors) >= 2:
            return monitors[1]
        return monitors[0] if monitors else None

    @staticmethod
    def get_monitor_bounds(monitor: MonitorInfo) -> tuple[int, int, int, int]:
        """Return monitor bounds tuple."""
        return monitor.left, monitor.top, monitor.right, monitor.bottom

    @staticmethod
    def is_window_on_monitor(
        window_bounds: tuple[int, int, int, int],
        monitor: MonitorInfo,
    ) -> bool:
        """Check if window's top-left lies within monitor."""
        left, top, _, _ = window_bounds
        return monitor.left <= left < monitor.right and monitor.top <= top < monitor.bottom

    def to_dict(self) -> list[dict[str, Any]]:
        """Export monitor data for diagnostics."""
        return [asdict(monitor) for monitor in self.get_monitors()]
