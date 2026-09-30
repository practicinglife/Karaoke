"""Core business services."""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import KaraokeLibrary, SessionRecord, Setting, Song, User
from .utils import generate_house_code
from .validators import (
    is_valid_apple_music_url,
    is_valid_spotify_url,
    is_valid_youtube_url,
    normalize_user_name,
    validate_artist_name,
    validate_display_name,
    validate_song_title,
)

SETTING_KEYS = {
    "karaoke_folder",
    "karaoke_manifest_path",
    "kanto_executable_path",
    "external_application_path",
    "playback_mode",
    "traditional_karaoke_server_url",
    "use_kanto",
    "use_web_player",
    "web_server_port",
    "ticker_upcoming_count",
    "singer_rotation_on",
    "house_name",
    "first_run_completed",
}


DEFAULT_SETTINGS = {
    "karaoke_folder": "",
    "karaoke_manifest_path": "",
    "kanto_executable_path": "",
    "external_application_path": "",
    "playback_mode": "built_in",
    "traditional_karaoke_server_url": "",
    "use_kanto": "0",
    "use_web_player": "1",
    "web_server_port": "8080",
    "ticker_upcoming_count": "5",
    "singer_rotation_on": "1",
    "house_name": "Karaoke Ticker",
    "first_run_completed": "0",
}


def ensure_default_settings(session: Session) -> None:
    """Ensure settings rows exist."""
    for key, value in DEFAULT_SETTINGS.items():
        if not session.get(Setting, key):
            session.add(Setting(key=key, value=value))
    session.flush()


def get_setting(session: Session, key: str) -> str:
    """Get setting value."""
    setting = session.get(Setting, key)
    if not setting:
        if key in DEFAULT_SETTINGS:
            setting = Setting(key=key, value=DEFAULT_SETTINGS[key])
            session.add(setting)
            session.flush()
        else:
            return ""

    value = setting.value
    if key == "external_application_path" and not value:
        legacy = session.get(Setting, "kanto_executable_path")
        if legacy and legacy.value:
            return legacy.value
    if key == "playback_mode" and not value:
        return infer_playback_mode_from_legacy(session)
    return value


def set_setting(session: Session, key: str, value: str) -> None:
    """Set setting value."""
    if key not in SETTING_KEYS:
        raise ValueError("Unknown setting key.")
    setting = session.get(Setting, key)
    if not setting:
        setting = Setting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    session.flush()


def infer_playback_mode_from_legacy(session: Session) -> str:
    """Infer playback mode from legacy compatibility settings."""
    use_web_player = get_setting(session, "use_web_player") == "1"
    use_kanto = get_setting(session, "use_kanto") == "1"
    legacy_path = get_setting(session, "kanto_executable_path").strip()
    if use_web_player:
        return "built_in"
    if use_kanto or legacy_path:
        return "external_application"
    return "system_default"


def get_playback_mode(session: Session) -> str:
    """Return normalized playback mode with legacy fallback."""
    mode = get_setting(session, "playback_mode").strip().lower()
    if mode in {"built_in", "system_default", "external_application"}:
        return mode
    return infer_playback_mode_from_legacy(session)


def set_playback_mode(session: Session, mode: str) -> str:
    """Persist playback mode and synchronize legacy flags for compatibility."""
    normalized = (mode or "").strip().lower()
    if normalized not in {"built_in", "system_default", "external_application"}:
        normalized = "built_in"

    set_setting(session, "playback_mode", normalized)
    set_setting(session, "use_web_player", "1" if normalized == "built_in" else "0")
    set_setting(session, "use_kanto", "1" if normalized == "external_application" else "0")
    return normalized


def get_external_application_path(session: Session) -> str:
    """Return configured external application path with legacy fallback."""
    return get_setting(session, "external_application_path").strip()


def set_external_application_path(session: Session, path: str) -> str:
    """Persist external app path and mirror into legacy key for compatibility."""
    normalized_path = (path or "").strip()
    set_setting(session, "external_application_path", normalized_path)
    set_setting(session, "kanto_executable_path", normalized_path)
    return normalized_path


def create_or_get_user(session: Session, display_name: str) -> User:
    """Create or return existing user by normalized name."""
    clean_name = validate_display_name(display_name)
    normalized = normalize_user_name(clean_name)
    existing = session.scalar(select(User).where(User.normalized_name == normalized))
    if existing:
        return existing
    try:
        with session.begin_nested():
            user = User(display_name=clean_name, normalized_name=normalized)
            session.add(user)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(User).where(User.normalized_name == normalized))
        if existing:
            return existing
        raise
    return user


def list_users(session: Session) -> list[User]:
    """List users by name."""
    return list(session.scalars(select(User).order_by(User.display_name.asc())))


def get_user_by_name(session: Session, display_name: str) -> User | None:
    """Lookup user by normalized display name."""
    normalized = normalize_user_name(display_name)
    return session.scalar(select(User).where(User.normalized_name == normalized))


def create_song(
    session: Session,
    *,
    user_id: int,
    title: str,
    artist: str,
    service: str,
    url: str | None = None,
    karaoke_library_id: int | None = None,
) -> Song:
    """Create song under user."""
    title_clean = validate_song_title(title)
    artist_clean = validate_artist_name(artist)
    if service not in {"traditional", "youtube", "apple_music", "spotify"}:
        raise ValueError("Invalid song service.")

    if service == "traditional":
        if not karaoke_library_id:
            raise ValueError("Traditional songs must reference indexed karaoke item.")
        entry = session.get(KaraokeLibrary, karaoke_library_id)
        if not entry or not entry.active:
            raise ValueError("Selected karaoke library entry is not available.")
        url = None
    elif service == "youtube":
        if not url or not is_valid_youtube_url(url):
            raise ValueError("Invalid YouTube URL.")
    elif service == "apple_music":
        if not url or not is_valid_apple_music_url(url):
            raise ValueError("Invalid Apple Music URL.")
    elif service == "spotify":
        if not url or not is_valid_spotify_url(url):
            raise ValueError("Invalid Spotify URL.")

    song = Song(
        user_id=user_id,
        title=title_clean,
        artist=artist_clean,
        service=service,
        url=url,
        karaoke_library_id=karaoke_library_id,
    )
    session.add(song)
    session.flush()
    return song


def list_user_songs(session: Session, user_id: int) -> list[Song]:
    """List songs for user."""
    return list(
        session.scalars(
            select(Song).where(Song.user_id == user_id).order_by(Song.created_at.desc())
        )
    )


def update_song(
    session: Session,
    song_id: int,
    *,
    title: str,
    artist: str,
) -> Song:
    """Update editable song fields."""
    song = session.get(Song, song_id)
    if not song:
        raise ValueError("Song not found.")
    song.title = validate_song_title(title)
    song.artist = validate_artist_name(artist)
    session.flush()
    return song


def delete_song(session: Session, song_id: int) -> None:
    """Delete song."""
    song = session.get(Song, song_id)
    if not song:
        raise ValueError("Song not found.")
    session.delete(song)
    session.flush()


def create_session(session: Session, house_name: str | None = None) -> SessionRecord:
    """Create running karaoke session and stop previous running one."""
    running = session.scalar(
        select(SessionRecord).where(SessionRecord.status == "RUNNING")
    )
    if running:
        running.status = "STOPPED"
        running.ended_at = datetime.utcnow()

    house_code = generate_house_code()
    while session.scalar(select(SessionRecord).where(SessionRecord.house_code == house_code)):
        house_code = generate_house_code()

    record = SessionRecord(
        house_code=house_code,
        status="RUNNING",
        house_name=house_name or DEFAULT_SETTINGS["house_name"],
        admin_token=secrets.token_hex(16),
        ticker_token=secrets.token_hex(16),
    )
    session.add(record)
    session.flush()
    return record


def stop_session(session: Session, session_id: int) -> SessionRecord:
    """Stop active session."""
    record = session.get(SessionRecord, session_id)
    if not record:
        raise ValueError("Session not found.")
    record.status = "STOPPED"
    record.ended_at = datetime.utcnow()
    session.flush()
    return record


def active_session(session: Session) -> SessionRecord | None:
    """Get active session."""
    return session.scalar(
        select(SessionRecord)
        .where(SessionRecord.status == "RUNNING")
        .order_by(SessionRecord.started_at.desc())
    )


def validate_house_code(session: Session, house_code: str) -> SessionRecord | None:
    """Validate that a house code belongs to active session."""
    return session.scalar(
        select(SessionRecord).where(
            SessionRecord.status == "RUNNING",
            SessionRecord.house_code == house_code,
        )
    )
