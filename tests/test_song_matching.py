"""Song matching normalization tests."""

from playback.playback_job import SERVICE_MAP


def test_service_map_contains_expected_values() -> None:
    assert SERVICE_MAP["traditional"] == "kanto"
    assert SERVICE_MAP["apple_music"] == "apple_music"
    assert SERVICE_MAP["youtube"] == "youtube_music"
