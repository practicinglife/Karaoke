"""Controller recovery tests."""

from playback.playback_state import PlaybackState


def test_recovering_state_exists_for_failure_handling() -> None:
    assert PlaybackState.RECOVERING.value == "RECOVERING"
