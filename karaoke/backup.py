"""Back up and import user data (singers and their saved songs).

A backup folder holds:
- ``karaoke.db``: a consistent copy of the whole database (SQLite online backup,
  safe while the app is running), for a full restore.
- ``users_and_songs.json``: singers and saved songs in a portable form, which
  ``import_user_data`` can load into another copy of the app (for example a test
  copy run from source, or a fresh install).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KaraokeLibrary, Song, User
from .services import create_or_get_user, create_song
from .utils import utcnow

FORMAT_VERSION = 1
JSON_NAME = "users_and_songs.json"


def sqlite_file(database_url: str) -> Path | None:
    """Path of a sqlite:/// database, or None for other databases."""
    prefix = "sqlite:///"
    return Path(database_url[len(prefix):]) if database_url.startswith(prefix) else None


def copy_database(source: Path, target: Path) -> None:
    """Consistent copy of a SQLite database, even while it is in use."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def export_user_data(session: Session) -> dict[str, Any]:
    users = []
    for user in session.scalars(select(User).order_by(User.id)):
        songs = []
        for song in session.scalars(select(Song).where(Song.user_id == user.id).order_by(Song.id)):
            entry = session.get(KaraokeLibrary, song.karaoke_library_id) if song.karaoke_library_id else None
            songs.append(
                {
                    "title": song.title,
                    "artist": song.artist,
                    "service": song.service,
                    "url": song.url,
                    # Traditional songs are matched to the library by file on import.
                    "karaoke_file": entry.primary_file if entry else None,
                    "created_at": song.created_at.isoformat() if song.created_at else None,
                }
            )
        users.append({"display_name": user.display_name, "songs": songs})
    return {"format": FORMAT_VERSION, "exported_at": utcnow().isoformat(), "users": users}


def backup_user_data(db_manager, database_url: str, backups_dir: Path) -> Path:
    """Create a timestamped backup folder and return its path."""
    folder = Path(backups_dir) / f"backup-{utcnow().strftime('%Y-%m-%d_%H%M%S')}"
    folder.mkdir(parents=True, exist_ok=False)
    db_file = sqlite_file(database_url)
    if db_file and db_file.exists():
        copy_database(db_file, folder / "karaoke.db")
    with db_manager.session_scope() as session:
        payload = export_user_data(session)
    (folder / JSON_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return folder


@dataclass
class ImportResult:
    users_added: int = 0
    songs_added: int = 0
    songs_already_there: int = 0
    traditional_not_indexed: int = 0
    invalid: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Singers added: {self.users_added}",
            f"Songs added: {self.songs_added}",
            f"Songs already there: {self.songs_already_there}",
        ]
        if self.traditional_not_indexed:
            lines.append(
                f"Traditional songs skipped (not in this copy's library yet): {self.traditional_not_indexed}. "
                "Refresh the karaoke library, then import again."
            )
        if self.invalid:
            lines.append(f"Skipped as invalid: {len(self.invalid)}")
        return "\n".join(lines)


def import_user_data(session: Session, payload: dict[str, Any]) -> ImportResult:
    """Add singers and songs from a backup. Never deletes or changes existing data."""
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_VERSION:
        raise ValueError("Not a Karaoke Ticker user backup.")
    result = ImportResult()
    for user_data in payload.get("users", []):
        name = str(user_data.get("display_name") or "").strip()
        if not name:
            continue
        existing_ids = set(session.scalars(select(User.id)))
        try:
            user = create_or_get_user(session, name)
        except ValueError as exc:
            result.invalid.append(f"{name}: {exc}")
            continue
        if user.id not in existing_ids:
            result.users_added += 1
        current = {
            (s.service, s.title.casefold(), s.artist.casefold(), s.url or "", s.karaoke_library_id)
            for s in session.scalars(select(Song).where(Song.user_id == user.id))
        }
        for song in user_data.get("songs", []):
            service = song.get("service")
            library_id = None
            if service == "traditional":
                library_id = session.scalar(
                    select(KaraokeLibrary.id).where(
                        KaraokeLibrary.primary_file == (song.get("karaoke_file") or ""),
                        KaraokeLibrary.active == True,  # noqa: E712
                    )
                )
                if library_id is None:
                    result.traditional_not_indexed += 1
                    continue
            key = (
                service,
                str(song.get("title") or "").casefold(),
                str(song.get("artist") or "").casefold(),
                "" if service == "traditional" else (song.get("url") or ""),
                library_id,
            )
            if key in current:
                result.songs_already_there += 1
                continue
            try:
                with session.begin_nested():
                    create_song(
                        session,
                        user_id=user.id,
                        title=song.get("title") or "",
                        artist=song.get("artist") or "",
                        service=service,
                        url=song.get("url"),
                        karaoke_library_id=library_id,
                    )
            except ValueError as exc:
                result.invalid.append(f"{name} / {song.get('title')}: {exc}")
                continue
            current.add(key)
            result.songs_added += 1
    return result
