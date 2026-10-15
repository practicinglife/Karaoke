"""Database initialization tests."""

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, inspect

from karaoke import database
from karaoke.database import DatabaseManager


def test_database_tables_created(app) -> None:
    inspector = inspect(app.runtime_state.db.engine)
    tables = set(inspector.get_table_names())
    expected = {
        "users",
        "songs",
        "karaoke_library",
        "sessions",
        "queue_items",
        "settings",
        "event_log",
    }
    assert expected.issubset(tables)



def _wal_size(db_file: Path) -> int:
    wal = Path(f"{db_file}-wal")
    return wal.stat().st_size if wal.exists() else 0


def _write_rows(db: DatabaseManager, count: int) -> None:
    with db.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS filler (id INTEGER PRIMARY KEY, body TEXT)")
        for start in range(0, count, 500):
            conn.exec_driver_sql(
                "INSERT INTO filler (body) VALUES " + ",".join(["(?)"] * 500),
                tuple("x" * 2000 for _ in range(500)),
            )


def test_checkpoint_truncates_wal(tmp_path) -> None:
    db_file = tmp_path / "karaoke.db"
    db = DatabaseManager(f"sqlite:///{db_file}")
    db.create_all()
    _write_rows(db, 5000)
    assert _wal_size(db_file) > 5_000_000

    assert db.checkpoint() is True
    assert _wal_size(db_file) == 0
    with db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM filler").scalar_one() == 5000
    db.engine.dispose()


def test_checkpoint_waits_out_open_reader_then_reports_busy(tmp_path) -> None:
    db_file = tmp_path / "karaoke.db"
    db = DatabaseManager(f"sqlite:///{db_file}")
    db.create_all()
    _write_rows(db, 500)
    reader = sqlite3.connect(db_file)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM filler").fetchone()
    _write_rows(db, 500)  # newer than the reader's snapshot, so it cannot be folded in yet
    db.engine.dispose()

    impatient = DatabaseManager(f"sqlite:///{db_file}")
    impatient.engine.dispose()
    impatient.engine = create_engine(f"sqlite:///{db_file}", connect_args={"timeout": 0.1})
    assert impatient.checkpoint() is False
    assert _wal_size(db_file) > 0

    reader.rollback()
    reader.close()
    assert impatient.checkpoint() is True
    assert _wal_size(db_file) == 0
    impatient.engine.dispose()


def test_wal_shrinks_to_size_limit_after_a_huge_write(tmp_path, monkeypatch) -> None:
    """Without journal_size_limit SQLite keeps the WAL at its largest size forever."""
    monkeypatch.setattr(database, "WAL_SIZE_LIMIT_BYTES", 1_000_000)
    db_file = tmp_path / "karaoke.db"
    db = DatabaseManager(f"sqlite:///{db_file}")
    db.create_all()
    _write_rows(db, 5000)  # ~10 MB in one transaction, like the library cleanup
    assert _wal_size(db_file) > 5_000_000

    with db.engine.connect() as conn:  # the passive auto-checkpoint SQLite runs by itself
        conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
    with db.engine.begin() as conn:  # the next write restarts the log and trims it
        conn.exec_driver_sql("UPDATE filler SET body = 'y' WHERE id = 1")
    assert _wal_size(db_file) <= 1_000_000
    db.engine.dispose()


def test_startup_shrinks_a_wal_left_by_a_previous_run(tmp_path) -> None:
    db_file = tmp_path / "karaoke.db"
    first = DatabaseManager(f"sqlite:///{db_file}")
    first.create_all()
    _write_rows(first, 2000)
    # An idle second connection stops SQLite from tidying the log when the first closes,
    # which is what happens when the app is killed or another reader is still attached.
    bystander = sqlite3.connect(db_file)
    bystander.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
    first.engine.dispose()
    assert _wal_size(db_file) > 1_000_000

    second = DatabaseManager(f"sqlite:///{db_file}")
    second.create_all()
    assert _wal_size(db_file) == 0
    bystander.close()
    second.engine.dispose()
