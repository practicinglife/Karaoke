"""Player manager behavior tests."""

from __future__ import annotations

from playback.playback_job import PlaybackJob
from playback.player_manager import PlayerManager
from playback.players.kanto_player import KantoPlayer


class DummyWindowManager:
    def __init__(self) -> None:
        self.media_play_pause_calls = 0
        self.space_calls = 0
        self.enter_calls = 0
        self.global_media_play_pause_calls = 0
        self.global_space_calls = 0
        self.global_enter_calls = 0

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

    def click_screen_point(self, _x: int, _y: int) -> bool:
        return False


class DummyPlayer:
    def __init__(self) -> None:
        self.ensure_running_calls = 0
        self.discover_calls = 0
        self.activate_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0
        self.prepare_calls = 0
        self.load_calls = 0
        self.select_calls = 0
        self.start_calls = 0

    def ensure_running(self) -> None:
        self.ensure_running_calls += 1

    def discover(self) -> None:
        self.discover_calls += 1

    def activate(self) -> None:
        self.activate_calls += 1

    def prepare(self, _job: PlaybackJob) -> None:
        self.prepare_calls += 1

    def load(self, _job: PlaybackJob) -> None:
        self.load_calls += 1

    def select(self, _job: PlaybackJob) -> None:
        self.select_calls += 1

    def start(self) -> None:
        self.start_calls += 1

    def verify_started(self, _job: PlaybackJob) -> bool:
        return True

    def pause(self) -> None:
        self.pause_calls += 1

    def stop(self) -> None:
        self.stop_calls += 1

    def is_playing(self) -> bool:
        return False

    def has_finished(self) -> bool:
        return False

    def place_windows(self) -> None:
        return None

    def capture_diagnostics(self) -> dict[str, object]:
        return {}

    def recover(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def test_player_manager_switch_stops_other_players() -> None:
    manager = PlayerManager()
    kanto = DummyPlayer()
    apple = DummyPlayer()
    youtube = DummyPlayer()
    manager._players = {  # type: ignore[attr-defined]
        "kanto": kanto,
        "apple_music": apple,
        "youtube_music": youtube,
    }

    manager.switch_to_player("apple_music")

    assert kanto.pause_calls == 1
    assert youtube.pause_calls == 1
    assert apple.activate_calls == 1


def test_player_manager_prepare_and_start_job() -> None:
    manager = PlayerManager()
    kanto = DummyPlayer()
    manager._players = {  # type: ignore[attr-defined]
        "kanto": kanto,
        "apple_music": DummyPlayer(),
        "youtube_music": DummyPlayer(),
    }

    job = PlaybackJob(
        queue_item_id=21,
        singer="Levi",
        title="Song",
        artist="Artist",
        service="kanto",
        path_or_url=r"D:\\song.cdg",
        expected_player="kanto",
    )

    manager.prepare_job(job)
    started = manager.start_job(job)

    assert started is True
    assert kanto.prepare_calls == 1
    assert kanto.load_calls == 1
    assert kanto.select_calls == 1
    assert kanto.start_calls == 1


def test_kanto_start_inputs_use_media_play_pause_first() -> None:
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
