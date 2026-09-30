"""Window matching helper tests."""

from __future__ import annotations

from time import monotonic

from playback.players.apple_music_player import AppleMusicPlayer
from playback.players.youtube_music_player import YouTubeMusicPlayer
from playback.window_manager import WindowInfo, WindowManager


def test_find_window_matches_title_and_process() -> None:
    manager = WindowManager()

    def fake_enum() -> list[WindowInfo]:
        return [
            WindowInfo(
                hwnd=101,
                process_id=11,
                title="Apple Music",
                class_name="ApplicationFrameWindow",
                visible=True,
                enabled=True,
                left=0,
                top=0,
                right=1200,
                bottom=800,
            ),
            WindowInfo(
                hwnd=102,
                process_id=22,
                title="Kanto Player",
                class_name="KantoMain",
                visible=True,
                enabled=True,
                left=1200,
                top=0,
                right=1920,
                bottom=1080,
            ),
        ]

    manager.enumerate_top_level_windows = fake_enum  # type: ignore[assignment]
    found = manager.find_window(process_id=11, title_contains=["music"])

    assert found is not None
    assert found.hwnd == 101


def test_find_window_returns_none_when_no_match() -> None:
    manager = WindowManager()
    manager.enumerate_top_level_windows = lambda: []  # type: ignore[assignment]

    found = manager.find_window(process_id=999, title_contains=["nothing"])
    assert found is None


def test_apple_music_discover_falls_back_to_title_matching_when_process_missing() -> None:
    player = AppleMusicPlayer({"playback_controller": {"manual_player_launch": True}})
    player._find_process_id = lambda: None  # type: ignore[assignment]

    class FakeWindowManager:
        def find_window(self, **kwargs):
            title_contains = [str(item).lower() for item in kwargs.get("title_contains", []) or []]
            if "apple music" in title_contains or "music" in title_contains:
                return WindowInfo(
                    hwnd=201,
                    process_id=33,
                    title="Apple Music",
                    class_name="ApplicationFrameWindow",
                    visible=True,
                    enabled=True,
                    left=0,
                    top=0,
                    right=1200,
                    bottom=800,
                )
            return None

        def restore_window(self, _hwnd: int) -> bool:
            return True

        def attach_input_and_focus(self, _hwnd: int) -> bool:
            return True

        def verify_foreground_window(self, _hwnd: int) -> bool:
            return True

    player._window_manager = FakeWindowManager()  # type: ignore[assignment]

    player.discover()

    assert player.process_id == 33
    assert player.main_window_handle == 201
    assert player.playback_window_handle == 201


def test_youtube_music_discover_falls_back_to_title_matching_when_process_missing() -> None:
    player = YouTubeMusicPlayer({"playback_controller": {"manual_player_launch": True}})
    player._find_process_id = lambda: None  # type: ignore[assignment]

    class FakeWindowManager:
        def find_window(self, **kwargs):
            title_contains = [str(item).lower() for item in kwargs.get("title_contains", []) or []]
            if "youtube music" in title_contains or "youtube" in title_contains or "music" in title_contains:
                return WindowInfo(
                    hwnd=301,
                    process_id=44,
                    title="YouTube Music",
                    class_name="Chrome_WidgetWin_1",
                    visible=True,
                    enabled=True,
                    left=0,
                    top=0,
                    right=1200,
                    bottom=800,
                )
            return None

        def restore_window(self, _hwnd: int) -> bool:
            return True

        def attach_input_and_focus(self, _hwnd: int) -> bool:
            return True

    player._window_manager = FakeWindowManager()  # type: ignore[assignment]

    player.discover()

    assert player.process_id == 44
    assert player.main_window_handle == 301
    assert player.playback_window_handle == 301


def test_apple_music_load_accepts_album_page_and_opens_browser(monkeypatch) -> None:
    player = AppleMusicPlayer({"playback_controller": {"manual_player_launch": True}})
    opened_urls: list[str] = []
    monkeypatch.setattr("playback.players.apple_music_player.webbrowser.open", lambda url: opened_urls.append(url) or True)
    monkeypatch.setattr("playback.players.apple_music_player.sleep", lambda _seconds: None)
    monkeypatch.setattr(player, "discover", lambda: None)
    monkeypatch.setattr(player, "activate", lambda: None)

    class FakeJob:
        path_or_url = "https://music.apple.com/us/album/test/123"

    player.load(FakeJob())

    assert opened_urls == ["https://music.apple.com/us/album/test/123"]


def test_apple_music_verify_started_uses_browser_audio_processes(monkeypatch) -> None:
    player = AppleMusicPlayer({"playback_controller": {"manual_player_launch": True, "playback_start_timeout_seconds": 0.5}})
    player._started_at = monotonic()
    player.discover = lambda: None  # type: ignore[assignment]

    class FakeAudioMonitor:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def is_any_audio_active(self, process_names):
            self.calls.append(list(process_names))
            return True

    fake_audio = FakeAudioMonitor()
    player._audio_monitor = fake_audio  # type: ignore[assignment]

    assert player.verify_started(object()) is True
    assert fake_audio.calls
    assert "msedge.exe" in fake_audio.calls[0]
    assert "chrome.exe" in fake_audio.calls[0]
