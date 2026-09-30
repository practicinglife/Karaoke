"""Karaoke library indexing and search tests."""

from pathlib import Path

from karaoke.library_indexer import build_index, list_active_library, search_library, search_library_traditional


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
