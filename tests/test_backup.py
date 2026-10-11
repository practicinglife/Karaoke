"""User data backup and import tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import func, select

from karaoke.backup import JSON_NAME, backup_user_data, import_user_data
from karaoke.database import DatabaseManager
from karaoke.library_indexer import build_index, search_library
from karaoke.models import Song, User
from karaoke.services import create_or_get_user, create_song, ensure_default_settings


def _seed(app, folder: Path) -> None:
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(folder))
        dale = create_or_get_user(db, "Dale")
        lib = search_library(db, "friends in low places")[0]
        create_song(db, user_id=dale.id, title="Friends in Low Places", artist="Garth Brooks",
                    service="traditional", karaoke_library_id=lib.id)
        create_song(db, user_id=dale.id, title="Zoo", artist="Jawed", service="youtube",
                    url="https://www.youtube.com/watch?v=jNQXAC9IVRw")
        sam = create_or_get_user(db, "Sam")
        create_song(db, user_id=sam.id, title="Song", artist="Artist", service="spotify",
                    url="https://open.spotify.com/track/abc")


def _fresh_db(tmp_path: Path, name: str) -> DatabaseManager:
    manager = DatabaseManager(f"sqlite:///{(tmp_path / name).as_posix()}")
    manager.create_all()
    with manager.session_scope() as db:
        ensure_default_settings(db)
    return manager


def test_backup_writes_database_copy_and_json(app, test_karaoke_folder, tmp_path) -> None:
    _seed(app, test_karaoke_folder)
    folder = backup_user_data(app.runtime_state.db, f"sqlite:///{(tmp_path / 'karaoke_test.db').as_posix()}", tmp_path / "backups")

    payload = json.loads((folder / JSON_NAME).read_text(encoding="utf-8"))
    by_name = {u["display_name"]: u for u in payload["users"]}
    assert {s["title"] for s in by_name["Dale"]["songs"]} == {"Friends in Low Places", "Zoo"}
    traditional = next(s for s in by_name["Dale"]["songs"] if s["service"] == "traditional")
    assert traditional["karaoke_file"].endswith("Garth Brooks - Friends in Low Places.mp3")

    with sqlite3.connect(folder / "karaoke.db") as conn:
        assert conn.execute("select count(*) from songs").fetchone()[0] == 3


def test_import_adds_missing_data_and_is_safe_to_repeat(app, test_karaoke_folder, tmp_path) -> None:
    _seed(app, test_karaoke_folder)
    folder = backup_user_data(app.runtime_state.db, "", tmp_path / "backups")
    payload = json.loads((folder / JSON_NAME).read_text(encoding="utf-8"))

    target = _fresh_db(tmp_path, "target.db")
    with target.session_scope() as db:
        create_or_get_user(db, "Sam")  # already exists in the target
        first = import_user_data(db, payload)
    # Library not indexed in the target yet: streaming songs come over, traditional waits.
    assert (first.users_added, first.songs_added, first.traditional_not_indexed) == (1, 2, 1)

    with target.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        second = import_user_data(db, payload)
    assert (second.users_added, second.songs_added, second.songs_already_there) == (0, 1, 2)

    with target.session_scope() as db:
        third = import_user_data(db, payload)
        assert (third.songs_added, third.songs_already_there) == (0, 3)
        assert db.scalar(select(func.count()).select_from(User)) == 2
        assert db.scalar(select(func.count()).select_from(Song)) == 3


def test_import_rejects_other_files(tmp_path) -> None:
    target = _fresh_db(tmp_path, "target.db")
    with target.session_scope() as db:
        try:
            import_user_data(db, {"something": "else"})
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def test_library_cleanup_backs_up_database_first(tmp_path) -> None:
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    manager.create_all()
    with manager.engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ux_karaoke_library_primary_file")
        conn.exec_driver_sql(
            "INSERT INTO karaoke_library (title, artist, display_name, primary_file, folder, extension,"
            " modified_time, file_size, active, search_blob) VALUES ('t','a','a - t','x.mp3','f','.mp3','1',1,1,'a t')"
        )
    manager.create_all()
    backups = list((tmp_path / "backups").glob("pre-cleanup-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute("select count(*) from karaoke_library").fetchone()[0] == 1
