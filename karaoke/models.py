"""SQLAlchemy models for Karaoke Ticker."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    """Persistent karaoke user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    songs: Mapped[list["Song"]] = relationship("Song", back_populates="user", cascade="all, delete-orphan")
    queue_items: Mapped[list["QueueItem"]] = relationship("QueueItem", back_populates="user")


class KaraokeLibrary(Base):
    """Indexed karaoke media item."""

    __tablename__ = "karaoke_library"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_file: Mapped[str] = mapped_column(Text, nullable=False)
    audio_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    cdg_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    modified_time: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    search_blob: Mapped[str] = mapped_column(Text, nullable=False)

    songs: Mapped[list["Song"]] = relationship("Song", back_populates="karaoke_library")


class Song(Base):
    """User-saved song entry."""

    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(30), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    karaoke_library_id: Mapped[int | None] = mapped_column(
        ForeignKey("karaoke_library.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="songs")
    karaoke_library: Mapped[KaraokeLibrary | None] = relationship("KaraokeLibrary", back_populates="songs")
    queue_items: Mapped[list["QueueItem"]] = relationship("QueueItem", back_populates="song")


class SessionRecord(Base):
    """Karaoke session house code and status."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    house_code: Mapped[str] = mapped_column(String(6), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    house_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Karaoke Ticker")
    admin_token: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker_token: Mapped[str] = mapped_column(String(64), nullable=False)

    queue_items: Mapped[list["QueueItem"]] = relationship("QueueItem", back_populates="session")


class QueueItem(Base):
    """Queue item for active session playback pipeline."""

    __tablename__ = "queue_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="WAITING")
    queue_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    session: Mapped[SessionRecord] = relationship("SessionRecord", back_populates="queue_items")
    user: Mapped[User] = relationship("User", back_populates="queue_items")
    song: Mapped[Song] = relationship("Song", back_populates="queue_items")


class Setting(Base):
    """Application settings key/value store."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class EventLog(Base):
    """Simple event log."""

    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
