"""URL validator tests."""

from karaoke.validators import (
    is_valid_apple_music_url,
    is_valid_spotify_url,
    is_valid_youtube_url,
)


def test_youtube_url_validation() -> None:
    assert is_valid_youtube_url("https://www.youtube.com/watch?v=test123")
    assert is_valid_youtube_url("https://youtube.com/watch?v=test123")
    assert is_valid_youtube_url("https://youtu.be/test123")


def test_apple_music_url_validation() -> None:
    assert is_valid_apple_music_url("https://music.apple.com/us/album/test/123")


def test_spotify_url_validation() -> None:
    assert is_valid_spotify_url("https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6")
    assert is_valid_spotify_url("https://spotify.link/example123")


def test_invalid_url_rejection() -> None:
    assert not is_valid_youtube_url("https://example.com/watch?v=test123")
    assert not is_valid_apple_music_url("https://apple.com/not-music")
    assert not is_valid_spotify_url("https://example.com/track/abc")

