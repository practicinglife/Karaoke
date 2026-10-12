"""Karaoke library indexing and search tests."""

from pathlib import Path

from sqlalchemy import func, select

from karaoke.database import LIBRARY_PRIMARY_FILE_INDEX, DatabaseManager
from karaoke.library_indexer import build_index, list_active_library, search_library, search_library_traditional
from karaoke.models import KaraokeLibrary, Song, User
from karaoke.services import create_or_get_user, create_song


def _library_rows(db) -> int:
    return db.scalar(select(func.count()).select_from(KaraokeLibrary))


def test_rescan_reuses_rows_and_keeps_saved_songs(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        assert build_index(db, str(test_karaoke_folder)) == 4
        pair = db.scalar(select(KaraokeLibrary).where(KaraokeLibrary.extension == ".mp3+.cdg"))
        user = create_or_get_user(db, "Dale")
        song = create_song(
            db, user_id=user.id, title=pair.title, artist=pair.artist,
            service="traditional", karaoke_library_id=pair.id,
        )
        pair_id, song_id = pair.id, song.id

    for _ in range(2):
        with app.runtime_state.db.session_scope() as db:
            assert build_index(db, str(test_karaoke_folder)) == 0
            assert _library_rows(db) == 4

    with app.runtime_state.db.session_scope() as db:
        assert db.get(Song, song_id).karaoke_library_id == pair_id
        assert db.get(KaraokeLibrary, pair_id).active


def test_rescan_purges_removed_files(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
    (test_karaoke_folder / "Pop" / "ABBA - Dancing Queen.mp4").unlink()
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        assert _library_rows(db) == 3


def test_build_index_reports_progress(app, test_karaoke_folder) -> None:
    calls: list[tuple[int, int]] = []
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder), progress=lambda done, total: calls.append((done, total)))
    assert calls and calls[-1] == (5, 5)


def test_dedupe_migration_collapses_duplicates_and_remaps_songs(tmp_path: Path) -> None:
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    manager.create_all()
    with manager.engine.begin() as conn:
        conn.exec_driver_sql(f"DROP INDEX {LIBRARY_PRIMARY_FILE_INDEX}")

    def row(primary: str, active: bool) -> KaraokeLibrary:
        return KaraokeLibrary(
            title="T", artist="A", display_name="A - T", primary_file=primary, folder="f",
            extension=".mp3+.cdg", modified_time="1", file_size=1, active=active, search_blob="a t",
        )

    with manager.session_scope() as db:
        stale, older, current = row("x.mp3", False), row("x.mp3", False), row("x.mp3", True)
        orphan = row("gone.mp3", False)
        db.add_all([stale, older, current, orphan])
        db.flush()
        user = User(display_name="Dale", normalized_name="dale")
        db.add(user)
        db.flush()
        db.add(Song(user_id=user.id, title="T", artist="A", service="traditional", karaoke_library_id=stale.id))
        current_id = current.id

    manager.create_all()

    with manager.session_scope() as db:
        assert [r.id for r in db.scalars(select(KaraokeLibrary))] == [current_id]
        assert db.scalar(select(Song.karaoke_library_id)) == current_id
    # Second run is a no-op once the unique index exists.
    manager.create_all()


def test_library_indexing_with_fixture_folder(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        count = build_index(db, str(test_karaoke_folder))
        assert count == 4
        items = list(list_active_library(db))
        assert len(items) == 4


def test_mp3_cdg_pairing_and_search(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        results = search_library(db, "friends in low places")
        assert any("friends in low places" in row.search_blob for row in results)
        fuzzy = search_library(db, "Garth_Brooks Friends-In-Low-Places")
        assert fuzzy
        artist = search_library(db, "Garth Brooks")
        assert artist
        case_insensitive = search_library(db, "FRIENDS IN LOW PLACES")
        assert case_insensitive
        punctuation_tolerant = search_library(db, "Friends, in Low Places!!!")
        assert punctuation_tolerant


def test_traditional_search_normalizes_artist_queries(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        results = search_library_traditional(db, "garth brooks")
        assert results
        assert any(row.artist == "Garth Brooks" for row in results)


def test_traditional_search_prioritizes_artist_matches(app, test_karaoke_folder) -> None:
    bonus_dir = test_karaoke_folder / "Bonus"
    bonus_dir.mkdir()
    (bonus_dir / "Zed Artist - Garth Tribute.mp3").write_text("a")
    (bonus_dir / "Zed Artist - Garth Tribute.cdg").write_text("b")

    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        results = search_library_traditional(db, "garth")
        assert results
        assert results[0].artist == "Garth Brooks"
        assert any(row.title == "Garth Tribute" for row in results)


def test_database_uses_wal_so_reads_never_wait_on_a_scan(tmp_path: Path) -> None:
    manager = DatabaseManager(f"sqlite:///{(tmp_path / 'wal.db').as_posix()}")
    manager.create_all()
    with manager.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
