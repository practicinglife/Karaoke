"""Queue operation tests."""

from karaoke.library_indexer import build_index, search_library
from karaoke.models import QueueItem
from karaoke.queue_manager import COMPLETED, NOW_PLAYING, QueueManager, SKIPPED, WAITING
from karaoke.services import active_session, create_or_get_user, create_song


def _seed_song(db, user_name: str, title: str, artist: str):
    user = create_or_get_user(db, user_name)
    song = create_song(
        db,
        user_id=user.id,
        title=title,
        artist=artist,
        service="youtube",
        url=f"https://youtu.be/{title.replace(' ', '')}",
    )
    return user, song


def test_queue_insert_duplicate_prevention_remove_reorder(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        qm = QueueManager(db)
        user, song_a = _seed_song(db, "Dale", "Song One", "A")
        _, song_b = _seed_song(db, "Dale", "Song Two", "A")
        item_a = qm.add_song(session.id, user.id, song_a.id)
        qm.add_song(session.id, user.id, song_b.id)

        try:
            qm.add_song(session.id, user.id, song_a.id)
            assert False, "Expected duplicate rejection"
        except ValueError:
            pass

        waiting = qm.waiting_items(session.id)
        assert len(waiting) == 2
        qm.move_item(waiting[1].id, "up")
        moved = qm.waiting_items(session.id)
        assert moved[0].id == waiting[1].id
        qm.remove_item(item_a.id)
        left = qm.waiting_items(session.id)
        assert len(left) == 1


def test_mark_playing_complete_skip(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        qm = QueueManager(db)
        user, song = _seed_song(db, "Mike", "Song X", "Artist X")
        item = qm.add_song(session.id, user.id, song.id)
        qm.mark_now_playing(item.id)
        assert qm.now_playing(session.id).status == NOW_PLAYING  # type: ignore[union-attr]
        qm.mark_status(item.id, COMPLETED)
        assert db.get(QueueItem, item.id).status == COMPLETED  # type: ignore[union-attr]
        item2 = qm.add_song(session.id, user.id, song.id)
        qm.mark_status(item2.id, SKIPPED)
        assert db.get(QueueItem, item2.id).status == SKIPPED  # type: ignore[union-attr]


def test_queue_with_traditional_song(app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        lib = search_library(db, "friends in low places")[0]
        user = create_or_get_user(db, "Traditional User")
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        qm = QueueManager(db)
        item = qm.add_song(session.id, user.id, song.id)
        assert item.status == WAITING


def test_rotation_order_matches_real_world_up_next_pattern(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        qm = QueueManager(db)

        dale, dale_1 = _seed_song(db, "Dale", "Summertime", "Dale Cooper")
        missy, missy_1 = _seed_song(db, "Missy", "Simple Man", "Lynyrd Skynyrd")
        _, dale_2 = _seed_song(db, "Dale", "Everything's Gonna Be Alright", "David Lee Murphy & Kenny Chesney")
        _, missy_2 = _seed_song(db, "Missy", "Baby Got Back", "Sir Mix-A-Lot")
        _, dale_3 = _seed_song(db, "Dale", "Mine Would Be You", "Blake Shelton")
        _, missy_3 = _seed_song(db, "Missy", "Blue Eyes Crying In The Rain", "Elvis Presley")
        levi, levi_1 = _seed_song(db, "Levi", "You Never Even Call Me By My Name", "David Allen Coe")
        _, missy_4 = _seed_song(db, "Missy", "Come Running", "Van Morrison")
        _, levi_2 = _seed_song(db, "Levi", "Unsteady", "X Ambassadors")
        _, missy_5 = _seed_song(db, "Missy", "No Rain", "Blind Melon")
        _, levi_3 = _seed_song(db, "Levi", "I Remember Everything", "Zach Bryan")
        kam, kam_1 = _seed_song(db, "Kam", "Heart Like a Truck", "Lainey Wilson")
        _, kam_2 = _seed_song(db, "Kam", "She Had Me At Heads Carolina", "Cole Swindell")
        _, kam_3 = _seed_song(db, "Kam", "Bloody Valentine", "MGK")
        _, kam_4 = _seed_song(db, "Kam", "Taurus", "mgk")

        qm.add_song(session.id, dale.id, dale_1.id)
        qm.add_song(session.id, missy.id, missy_1.id)
        qm.add_song(session.id, dale.id, dale_2.id)
        qm.add_song(session.id, missy.id, missy_2.id)
        qm.add_song(session.id, dale.id, dale_3.id)
        qm.add_song(session.id, missy.id, missy_3.id)
        qm.add_song(session.id, levi.id, levi_1.id)
        qm.add_song(session.id, missy.id, missy_4.id)
        qm.add_song(session.id, levi.id, levi_2.id)
        qm.add_song(session.id, missy.id, missy_5.id)
        qm.add_song(session.id, levi.id, levi_3.id)
        qm.add_song(session.id, kam.id, kam_1.id)
        qm.add_song(session.id, kam.id, kam_2.id)
        qm.add_song(session.id, kam.id, kam_3.id)
        qm.add_song(session.id, kam.id, kam_4.id)

        ordered = qm.ordered_up_next(session.id, True)
        assert [item.user.display_name for item in ordered] == [
            "Kam",
            "Dale",
            "Missy",
            "Levi",
            "Kam",
            "Dale",
            "Missy",
            "Levi",
            "Kam",
            "Dale",
            "Missy",
            "Levi",
            "Kam",
            "Missy",
            "Missy",
        ]


def test_rotation_prioritizes_latest_added_group_once_then_resumes_turns(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        qm = QueueManager(db)

        singer_a, a_1 = _seed_song(db, "Singer A", "A1", "Artist A")
        singer_b, b_1 = _seed_song(db, "Singer B", "B1", "Artist B")
        _, a_2 = _seed_song(db, "Singer A", "A2", "Artist A")
        singer_c, c_1 = _seed_song(db, "Singer C", "C1", "Artist C")

        qm.add_song(session.id, singer_a.id, a_1.id)
        qm.add_song(session.id, singer_b.id, b_1.id)
        qm.add_song(session.id, singer_a.id, a_2.id)
        qm.add_song(session.id, singer_c.id, c_1.id)

        ordered = qm.ordered_up_next(session.id, True)
        assert [item.user.display_name for item in ordered] == [
            "Singer C",
            "Singer A",
            "Singer B",
            "Singer A",
        ]
