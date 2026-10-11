"""Database setup and session helpers."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker


Base = declarative_base()

LIBRARY_PRIMARY_FILE_INDEX = "ux_karaoke_library_primary_file"

# Older indexer builds inserted a new karaoke_library row for every MP3+CDG pair on
# every scan. Collapse those to one row per primary_file (preferring the newest active
# row), repoint saved songs at the survivor, drop unreferenced inactive rows, and add a
# unique index so duplicates cannot return.
_DEDUPE_LIBRARY_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_karaoke_library_primary_file_tmp ON karaoke_library (primary_file)",
    """
    CREATE TEMP TABLE karaoke_library_keep AS
    SELECT primary_file,
           COALESCE(MAX(CASE WHEN active = 1 THEN id END), MAX(id)) AS keep_id
    FROM karaoke_library
    GROUP BY primary_file
    HAVING COUNT(*) > 1
    """,
    "CREATE INDEX ix_karaoke_library_keep ON karaoke_library_keep (primary_file)",
    """
    UPDATE songs SET karaoke_library_id = (
        SELECT k.keep_id FROM karaoke_library l
        JOIN karaoke_library_keep k ON k.primary_file = l.primary_file
        WHERE l.id = songs.karaoke_library_id
    )
    WHERE karaoke_library_id IN (
        SELECT l.id FROM karaoke_library l
        JOIN karaoke_library_keep k ON k.primary_file = l.primary_file
    )
    """,
    """
    DELETE FROM karaoke_library WHERE id IN (
        SELECT l.id FROM karaoke_library l
        JOIN karaoke_library_keep k ON k.primary_file = l.primary_file
        WHERE l.id <> k.keep_id
    )
    """,
    """
    DELETE FROM karaoke_library
    WHERE active = 0
      AND id NOT IN (SELECT karaoke_library_id FROM songs WHERE karaoke_library_id IS NOT NULL)
    """,
    "DROP TABLE karaoke_library_keep",
    "DROP INDEX ix_karaoke_library_primary_file_tmp",
    f"CREATE UNIQUE INDEX {LIBRARY_PRIMARY_FILE_INDEX} ON karaoke_library (primary_file)",
]


class DatabaseManager:
    """Database manager wrapping SQLAlchemy engine/session lifecycle."""

    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False}
            if database_url.startswith("sqlite")
            else {},
            future=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )

    def create_all(self) -> None:
        """Create all known schema objects."""
        Base.metadata.create_all(self.engine)
        self._dedupe_karaoke_library()

    def _dedupe_karaoke_library(self) -> None:
        """One-time migration for databases created before the unique primary_file index."""
        indexes = inspect(self.engine).get_indexes("karaoke_library")
        if any(index["name"] == LIBRARY_PRIMARY_FILE_INDEX for index in indexes):
            return

        with self.engine.connect() as conn:
            before = conn.exec_driver_sql("SELECT COUNT(*) FROM karaoke_library").scalar_one()
        if before:
            self._backup_before_migration()

        with self.engine.begin() as conn:
            logging.info("Deduplicating karaoke library (%s rows)...", before)
            for statement in _DEDUPE_LIBRARY_SQL:
                conn.exec_driver_sql(statement)
            after = conn.exec_driver_sql("SELECT COUNT(*) FROM karaoke_library").scalar_one()
        logging.info("Karaoke library deduplicated: %s -> %s rows", before, after)

        if before - after > 10_000 and self.engine.dialect.name == "sqlite":
            with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("VACUUM")

    def _backup_before_migration(self) -> None:
        """Copy the database aside before the one-time cleanup touches it."""
        from .backup import copy_database, sqlite_file
        from .utils import utcnow

        db_file = sqlite_file(str(self.engine.url))
        if not db_file or not db_file.exists():
            return
        target = db_file.parent / "backups" / f"pre-cleanup-{utcnow().strftime('%Y-%m-%d_%H%M%S')}.db"
        copy_database(db_file, target)
        logging.info("Backed up database before library cleanup: %s", target)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Provide transactional session scope."""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
