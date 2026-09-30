"""Input validation helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from .utils import normalize_text

MAX_NAME_LEN = 80
MAX_TITLE_LEN = 255
MAX_ARTIST_LEN = 255


def validate_display_name(name: str) -> str:
    """Validate guest/user display name."""
    cleaned = " ".join(name.strip().split())
    if not cleaned:
        raise ValueError("Name is required.")
    if len(cleaned) > MAX_NAME_LEN:
        raise ValueError(f"Name must be at most {MAX_NAME_LEN} characters.")
    return cleaned


def validate_song_title(title: str) -> str:
    """Validate song title."""
    cleaned = " ".join(title.strip().split())
    if not cleaned:
        raise ValueError("Song title is required.")
    if len(cleaned) > MAX_TITLE_LEN:
        raise ValueError(f"Song title must be at most {MAX_TITLE_LEN} characters.")
    return cleaned


def validate_artist_name(artist: str) -> str:
    """Validate artist name."""
    cleaned = " ".join(artist.strip().split())
    if not cleaned:
        raise ValueError("Artist is required.")
    if len(cleaned) > MAX_ARTIST_LEN:
        raise ValueError(f"Artist must be at most {MAX_ARTIST_LEN} characters.")
    return cleaned


def _is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_valid_youtube_url(url: str) -> bool:
    """Validate a user-supplied YouTube link."""
    if not _is_valid_http_url(url):
        return False
    netloc = urlparse(url).netloc.lower().split(":")[0]
    allowed = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
    return netloc in allowed


def is_valid_apple_music_url(url: str) -> bool:
    """Validate a user-supplied Apple Music link."""
    if not _is_valid_http_url(url):
        return False
    netloc = urlparse(url).netloc.lower().split(":")[0]
    return netloc in {"music.apple.com", "itunes.apple.com"}


def is_valid_spotify_url(url: str) -> bool:
    """Validate a user-supplied Spotify link."""
    if not _is_valid_http_url(url):
        return False
    netloc = urlparse(url).netloc.lower().split(":")[0]
    return netloc in {
        "open.spotify.com",
        "play.spotify.com",
        "spotify.link",
        "spoti.fi",
    }


def is_valid_traditional_karaoke_server_url(url: str) -> bool:
    """Validate configured remote traditional karaoke server URL."""
    if not _is_valid_http_url(url):
        return False
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if parsed.path not in {"", "/", "/player"}:
        return False
    return True


def normalize_user_name(name: str) -> str:
    """Normalize user name for uniqueness matching."""
    return normalize_text(name)
