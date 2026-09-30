"""Song persistence tests."""

from sqlalchemy import select

from karaoke.library_indexer import build_index, search_library
from karaoke.models import Song
from karaoke.services import create_or_get_user, create_song, list_user_songs


def test_song_creation_all_services(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Jennifer")
        build_index(db, str(test_karaoke_folder))
        traditional_match = search_library(db, "friends in low places")[0]

        traditional = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=traditional_match.id,
        )
        youtube = create_song(
            db,
            user_id=user.id,
            title="Don't Stop Believin'",
            artist="Journey",
            service="youtube",
            url="https://www.youtube.com/watch?v=test123",
        )
        apple = create_song(
            db,
            user_id=user.id,
            title="Faithfully",
            artist="Journey",
            service="apple_music",
            url="https://music.apple.com/us/album/test/123",
        )
        spotify = create_song(
            db,
            user_id=user.id,
            title="Separate Ways",
            artist="Journey",
            service="spotify",
            url="https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6",
        )
        assert traditional.service == "traditional"
        assert youtube.service == "youtube"
        assert apple.service == "apple_music"
        assert spotify.service == "spotify"


def test_song_persistence_between_sessions(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Persistent Singer")
        create_song(
            db,
            user_id=user.id,
            title="Song A",
            artist="Artist A",
            service="youtube",
            url="https://youtu.be/test123",
        )
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Persistent Singer")
        songs = list_user_songs(db, user.id)
        assert len(songs) == 1
        persisted = db.scalar(select(Song).where(Song.user_id == user.id))
        assert persisted is not None

