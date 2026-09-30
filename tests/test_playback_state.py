"""Playback state enum tests."""

from playback.playback_state import PlaybackState


def test_playback_state_contains_expected_values() -> None:
    values = {state.value for state in PlaybackState}
    assert "IDLE" in values
    assert "PLAYING" in values
    assert "FAILED" in values
    assert "RECOVERING" in values
