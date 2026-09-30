"""Integration-style workflow test."""

from karaoke.library_indexer import build_index, search_library
from karaoke.queue_manager import QueueManager
from karaoke.services import (
    active_session,
    create_or_get_user,
    create_session,
    create_song,
    stop_session,
)


def test_house_workflow_integration(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        build_index(db, str(test_karaoke_folder))
        session = active_session(db)
        assert session is not None
        dale = create_or_get_user(db, "Dale")
        local_match = search_library(db, "Friends in Low Places")[0]
        local_song = create_song(
            db,
            user_id=dale.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=local_match.id,
        )
        yt_song = create_song(
            db,
            user_id=dale.id,
            title="Don't Stop Believin'",
            artist="Journey",
            service="youtube",
            url="https://www.youtube.com/watch?v=test123",
        )
        am_song = create_song(
            db,
            user_id=dale.id,
            title="Faithfully",
            artist="Journey",
            service="apple_music",
            url="https://music.apple.com/us/album/test/123",
        )

        qm = QueueManager(db)
        item_local = qm.add_song(session.id, dale.id, local_song.id)
        qm.add_song(session.id, dale.id, yt_song.id)
        qm.add_song(session.id, dale.id, am_song.id)
        qm.mark_now_playing(item_local.id)
        assert qm.now_playing(session.id) is not None
        qm.next_song(session.id, singer_rotation_on=True)
        assert qm.now_playing(session.id) is not None
        stop_session(db, session.id)
        create_session(db, "Restarted House")

    with app.runtime_state.db.session_scope() as db:
        dale_again = create_or_get_user(db, "Dale")
        assert len(dale_again.songs) >= 3
        assert active_session(db) is not None

