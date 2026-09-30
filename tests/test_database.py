"""Database initialization tests."""

from sqlalchemy import inspect


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

