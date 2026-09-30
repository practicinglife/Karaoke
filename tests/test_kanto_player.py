"""Kanto player behavior tests."""

from __future__ import annotations

from playback.players.kanto_player import KantoPlayer



def test_kanto_manual_mode_does_not_launch_when_process_missing(monkeypatch) -> None:
    player = KantoPlayer(
        {
            "playback_controller": {
                "manual_player_launch": True,
                "kanto_executable_path": r"C:\\Program Files\\Kanto Player\\KantoPlayer.exe",
            }
        }
    )
    monkeypatch.setattr(player, "_find_process_id", lambda: None)
    monkeypatch.setattr("playback.players.kanto_player.subprocess.Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("launch should not be called in manual mode")))

    player.ensure_running()

    assert player.process_id is None



class DummyWindowManager:
    def __init__(self) -> None:
        self.media_play_pause_calls = 0
        self.space_calls = 0
        self.enter_calls = 0
        self.global_media_play_pause_calls = 0
        self.global_space_calls = 0
        self.global_enter_calls = 0
        self.click_calls = 0
        self.clicked_points: list[tuple[int, int]] = []

    def get_foreground_window_info(self) -> dict[str, object]:
        return {}

    def send_media_play_pause_key(self, _hwnd: int) -> bool:
        self.media_play_pause_calls += 1
        return True

    def send_space_key(self, _hwnd: int) -> bool:
        self.space_calls += 1
        return True

    def send_enter_key(self, _hwnd: int) -> bool:
        self.enter_calls += 1
        return True

    def send_global_media_play_pause_key(self) -> bool:
        self.global_media_play_pause_calls += 1
        return True

    def send_global_space_key(self) -> bool:
        self.global_space_calls += 1
        return True

    def send_global_enter_key(self) -> bool:
        self.global_enter_calls += 1
        return True

    def click_screen_point(self, x: int, y: int) -> bool:
        self.click_calls += 1
        self.clicked_points.append((x, y))
        return True


def test_kanto_start_inputs_prioritize_media_play_pause_key() -> None:
    player = KantoPlayer({"playback_controller": {"manual_player_launch": True}})
    window_manager = DummyWindowManager()
    player._window_manager = window_manager  # type: ignore[assignment]
    player.playback_window_handle = 101
    player.main_window_handle = 102

    sent = player._send_start_inputs("initial")

    assert sent is True
    assert window_manager.media_play_pause_calls == 2
    assert window_manager.space_calls == 2
    assert window_manager.enter_calls == 2
    assert window_manager.global_media_play_pause_calls == 1
    assert window_manager.global_space_calls == 1
    assert window_manager.global_enter_calls == 1
    assert window_manager.click_calls == 2
    assert window_manager.clicked_points == [(1211, 1051), (970, 737)]
