from __future__ import annotations

from karaoke.models import KaraokeLibrary
from karaoke.services import active_session
from karaoke.song_groups import GroupedLibrary, entry_from_row, group_songs


def _entry(row_id, artist, title, display=None, extension=".mp3+.cdg", tags=""):
    return entry_from_row(row_id, artist, title, display or f"{artist} - {title}", extension, tags)


def test_disc_codes_and_track_numbers_give_way_to_the_real_artist() -> None:
    for code in ("CBD-105262", "DMGCRIM602-19", "06"):
        entry = _entry(1, code, "Dolly Parton (MPX) - Jolene", f"{code} - Dolly Parton (MPX) - Jolene")
        assert (entry.artist, entry.title) == ("Dolly Parton", "Jolene")
    assert _entry(1, "CBD-105262", "Dolly Parton (MPX) - Jolene",
                  "CBD-105262 - Dolly Parton (MPX) - Jolene").label == "CD+G · CBD · MPX"
    # A band named with a number keeps it.
    assert _entry(1, "311", "Amber [SC Karaoke]").artist == "311"


def test_last_name_first_is_turned_around_but_bands_are_not() -> None:
    assert _entry(1, "Kramer, Jana", "I Hope It Rains").artist == "Jana Kramer"
    assert _entry(1, "Earth, Wind & Fire", "September").artist == "Earth, Wind & Fire"


def test_duets_are_listed_under_each_singer_and_bands_stay_whole() -> None:
    duet = _entry(1, "Kenny Rogers & Dolly Parton", "Islands In The Stream [SC Karaoke]", tags="duet")
    assert [key for _, key in duet.singers] == ["kenny rogers", "dolly parton"]
    band = _entry(2, "Brooks & Dunn", "Neon Moon [CB Karaoke]")
    assert [key for _, key in band.singers] == ["brooks dunn"]
    featured = _entry(3, "Pitbull feat. Ne-Yo", "Time Of Our Lives [ZM Karaoke]")
    assert [key for _, key in featured.singers] == ["pitbull", "ne yo"]


def test_versions_are_labelled_and_the_best_is_vocals_removed() -> None:
    entries = [
        _entry(1, "Dolly Parton", "Jolene [SC Karaoke]"),
        _entry(2, "Dolly Parton", "Jolene [KT Sing Along]", extension=".mp4"),
        _entry(3, "Dolly Parton", "Jolene [KT Karaoke]", extension=".mp4"),
        _entry(4, "Dolly Parton", "Jolene [SC Karaoke]"),  # same as 1: shown once
        _entry(5, "Dolly Parton", "Jolene [Party Tyme]", extension=".mp4"),
    ]
    [song] = group_songs(entries)
    assert song["title"] == "Jolene" and song["best_id"] == 3
    assert [v["label"] for v in song["versions"]] == [
        "Karaoke (vocals removed)", "Video · Party Tyme", "CD+G · SC Karaoke", "Sing Along (with vocals)"]
    assert [v["save_title"] for v in song["versions"]] == [
        "Jolene [Karaoke]", "Jolene", "Jolene", "Jolene [Sing Along]"]


def test_the_same_duet_credited_either_way_is_one_song() -> None:
    songs = group_songs([
        _entry(1, "Kenny Rogers & Dolly Parton", "Islands In The Stream [SC Karaoke]", tags="duet"),
        _entry(2, "Dolly Parton & Kenny Rogers", "Islands In The Stream [CB Karaoke]", tags="duet"),
    ])
    assert len(songs) == 1 and len(songs[0]["versions"]) == 2


def _add(db, rows):
    for n, (artist, title, extension, tags) in enumerate(rows, start=1):
        display = f"{artist} - {title}"
        db.add(KaraokeLibrary(
            title=title, artist=artist, display_name=display, primary_file=f"c:/k/{n}{extension[:4]}",
            folder="c:/k", extension=extension, modified_time="1", file_size=1, active=True,
            search_blob=display.lower(), tags=tags))


def test_search_groups_artists_and_songs(app) -> None:
    rows = [
        ("Dolly Parton", "Jolene [SC Karaoke]", ".mp3+.cdg", ""),
        ("Dolly Parton", "Jolene [KT Karaoke]", ".mp4", ""),
        ("Dolly Parton", "9 To 5 [CB Karaoke]", ".mp3+.cdg", ""),
        ("Kenny Rogers & Dolly Parton", "Islands In The Stream [SC Karaoke]", ".mp3+.cdg", "duet"),
        ("Louis Armstrong", "Hello Dolly [CB Karaoke]", ".mp3+.cdg", ""),
    ]
    library = GroupedLibrary()
    with app.runtime_state.db.session_scope() as db:
        _add(db, rows)
    with app.runtime_state.db.session_scope() as db:
        found = library.search(db, "dolly")
        artists = {a["name"]: a["songs"] for a in found["artists"]}
        assert artists["Dolly Parton"] == 3  # Jolene, 9 To 5 and the duet
        assert artists["Kenny Rogers & Dolly Parton"] == 1
        assert [(s["artist"], s["title"]) for s in found["songs"]] == [("Louis Armstrong", "Hello Dolly")]
        assert library.search(db, "d")["artists"] == []  # too short to search
        songs = library.artist_songs(db, "kenny rogers")
        assert [s["title"] for s in songs] == ["Islands In The Stream"]
        both = library.search(db, "dolly jolene")
        assert [s["title"] for s in both["songs"]] == ["Jolene"]
        best = both["songs"][0]
        assert best["best_id"] == best["versions"][0]["id"]
        assert best["versions"][0]["label"] == "Karaoke (vocals removed)"
        assert [a["name"] for a in library.search(db, "duets dolly")["artists"]][:1] == ["Dolly Parton"]


def test_grouped_search_routes_need_a_singer_and_answer_one(client, app) -> None:
    assert client.get("/song/search/grouped?q=garth").status_code == 403
    with app.runtime_state.db.session_scope() as db:
        code = active_session(db).house_code
    with client.session_transaction() as flask_session:
        flask_session["csrf_token"] = "test-csrf"
    client.post("/join", data={"csrf_token": "test-csrf", "code": code, "name": "Missy"})
    found = client.get("/song/search/grouped?q=garth").get_json()
    assert [a["name"] for a in found["artists"]] == ["Garth Brooks"]
    songs = client.get(f"/song/search/artist?key={found['artists'][0]['key']}").get_json()
    assert [s["title"] for s in songs] == ["Friends in Low Places"]
    assert songs[0]["versions"][0]["label"] == "CD+G"
