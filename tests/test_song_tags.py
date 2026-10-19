"""Duet and kids labels: rules, the one-time labelling of an existing library, and search."""

import sqlite3
from pathlib import Path

from sqlalchemy import select

from karaoke.database import DatabaseManager
from karaoke.library_indexer import build_index, search_library, search_library_traditional
from karaoke.models import KaraokeLibrary
from karaoke.song_tags import split_query, tags_for


def label(display_name: str) -> list[str]:
    artist, _, title = display_name.partition(" - ")
    return tags_for(artist, title, display_name, display_name)


def test_duet_rules() -> None:
    assert label("Kenny Rogers & Dolly Parton - Islands In The Stream [CB Karaoke]") == ["duet"]
    assert label("Johnny Cash With June Carter - Jackson") == ["duet"]
    assert label("ABBA (Duet) - Dance (While The Music Still Goes On) [SBI Karaoke]") == ["duet"]
    assert label("CBD-103267 - Celine Dion & R. Kelly (Duet) - I'm Your Angel") == ["duet"]
    assert label("Tom Petty & The Heartbreakers - Refugee") == []
    assert label("Kool & The Gang - Celebration") == []
    assert label("Brooks & Dunn - Neon Moon") == []
    assert label("2 Chainz Feat Kanye West - Birthday Song") == []  # featured verse, not marked as a duet


def test_kids_rules() -> None:
    assert label("Aladdin - Friend Like Me [Disney Karaoke]") == ["kids"]
    assert label("Traditional Nursery Rhymes - Mary Had A Little Lamb [SD Karaoke]") == ["kids"]
    assert label("Traditional - Twinkle Twinkle Little Star [Karaoke]") == ["kids"]
    assert label("Spongebob Square Pants - Spongebob Square Pants (Tv Theme) [SM Karaoke]") == ["kids"]
    assert label("All Time Low - Kids In The Dark [SF Karaoke]") == []      # "kids" in a song title
    assert label("Tony Christie - Happy Birthday Baby [BS Karaoke]") == []
    assert label("The Cars - Drive") == [] and label("Annie Lennox - Why") == []


def test_query_words() -> None:
    assert split_query("duets dolly") == ({"duet"}, "dolly")
    assert split_query("kids frozen") == ({"kids"}, "frozen")
    assert split_query("garth brooks") == (set(), "garth brooks")


def _library(folder: Path) -> None:
    folder.mkdir()
    for name in ["Kenny Rogers & Dolly Parton - Islands In The Stream", "Dolly Parton - Jolene",
                 "Aladdin - Friend Like Me [Disney Karaoke]", "Garth Brooks - The Dance",
                 "Dolly Parton & Ricky Van Shelton (Duet) - Rockin' Years"]:
        (folder / f"{name}.mp3").write_text("a")
        (folder / f"{name}.cdg").write_text("b")


def test_search_by_label(app, tmp_path: Path) -> None:
    _library(tmp_path / "lib")
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(tmp_path / "lib"))
        for search in (search_library, search_library_traditional):
            duets = [r.display_name for r in search(db, "duets", limit=20)]
            assert duets == ["Dolly Parton & Ricky Van Shelton (Duet) - Rockin' Years",
                             "Kenny Rogers & Dolly Parton - Islands In The Stream"]
            assert [r.display_name for r in search(db, "kids", limit=20)] == ["Aladdin - Friend Like Me [Disney Karaoke]"]
            narrowed = [r.display_name for r in search(db, "duet kenny", limit=20)]
            assert narrowed == ["Kenny Rogers & Dolly Parton - Islands In The Stream"]


def test_existing_library_is_labelled_once_on_upgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "karaoke.db"
    with sqlite3.connect(db_file) as conn:  # a library from before labels existed
        conn.execute(
            "CREATE TABLE karaoke_library (id INTEGER PRIMARY KEY, title VARCHAR(255) NOT NULL, artist VARCHAR(255) NOT NULL,"
            " display_name VARCHAR(255) NOT NULL, primary_file TEXT NOT NULL, audio_file TEXT, cdg_file TEXT, folder TEXT NOT NULL,"
            " extension VARCHAR(20) NOT NULL, modified_time VARCHAR(40) NOT NULL, file_size INTEGER NOT NULL, active BOOLEAN NOT NULL,"
            " search_blob TEXT NOT NULL)")
        conn.execute("CREATE UNIQUE INDEX ix_karaoke_library_primary_file ON karaoke_library (primary_file)")
        conn.executemany(
            "INSERT INTO karaoke_library (title, artist, display_name, primary_file, folder, extension, modified_time,"
            " file_size, active, search_blob) VALUES (?,?,?,?,'c:/k','.mp3+.cdg','1',1,1,?)",
            [("Islands In The Stream", "Kenny Rogers & Dolly Parton", "Kenny Rogers & Dolly Parton - Islands In The Stream",
              "c:/k/Kenny Rogers & Dolly Parton - Islands In The Stream.mp3", "kenny rogers dolly parton islands in the stream"),
             ("Jolene", "Dolly Parton", "Dolly Parton - Jolene", "c:/k/Dolly Parton - Jolene.mp3", "dolly parton jolene")])
    manager = DatabaseManager(f"sqlite:///{db_file.as_posix()}")
    manager.create_all()
    with manager.session_scope() as db:
        rows = {r.title: r for r in db.scalars(select(KaraokeLibrary))}
        assert rows["Islands In The Stream"].tags == "duet"
        assert "duets" in rows["Islands In The Stream"].search_blob
        assert rows["Jolene"].tags == ""
    assert (tmp_path / "backups").exists()  # backed up before the change


def test_band_names_only_count_as_the_first_part_of_the_credit() -> None:
    from karaoke.song_tags import NOT_A_DUET

    for band in ("Brooks & Dunn", "Simon & Garfunkel", "Big & Rich", "Tom Petty & The Heartbreakers",
                 "Florence + The Machine", "Mumford & Sons", "Earth, Wind & Fire"):
        assert NOT_A_DUET.search(band), band
    for duet in ("Garth Brooks & Trisha Yearwood", "Diana Ross & Lionel Richie", "Tom Petty & Stevie Nicks"):
        assert not NOT_A_DUET.search(duet), duet
