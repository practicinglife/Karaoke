"""Singer rotation vs FIFO tests."""

from karaoke.queue_manager import QueueManager
from karaoke.services import active_session, create_or_get_user, create_song


def _add(db, session_id: int, user_name: str, idx: int) -> None:
    user = create_or_get_user(db, user_name)
    song = create_song(
        db,
        user_id=user.id,
        title=f"{user_name} Song {idx}",
        artist=user_name,
        service="youtube",
        url=f"https://youtu.be/{user_name}{idx}",
    )
    QueueManager(db).add_song(session_id, user.id, song.id)


def test_singer_rotation_on(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        _add(db, session.id, "Dale", 1)
        _add(db, session.id, "Dale", 2)
        _add(db, session.id, "Melissa", 1)
        _add(db, session.id, "Mike", 1)
        order = QueueManager(db).ordered_up_next(session.id, singer_rotation_on=True)
        names = [item.user.display_name for item in order]
        assert names[:4] == ["Dale", "Melissa", "Mike", "Dale"]


def test_fifo_mode_off(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        _add(db, session.id, "Dale", 1)
        _add(db, session.id, "Dale", 2)
        _add(db, session.id, "Melissa", 1)
        order = QueueManager(db).ordered_up_next(session.id, singer_rotation_on=False)
        names = [item.user.display_name for item in order]
        assert names[:3] == ["Dale", "Dale", "Melissa"]



def _names(db, session_id: int) -> list[str]:
    return [i.user.display_name for i in QueueManager(db).ordered_up_next(session_id, singer_rotation_on=True)]


def _sing_next(db, session_id: int) -> str:
    """Play the first up-next song to completion (as the stage does: intermission between songs)."""
    from karaoke.queue_manager import COMPLETED

    qm = QueueManager(db)
    item = qm.ordered_up_next(session_id, singer_rotation_on=True)[0]
    qm.mark_now_playing(item.id)
    qm.mark_status(item.id, COMPLETED)
    return item.user.display_name


def test_singer_who_sang_and_requeues_keeps_their_place_not_the_top(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        for name in ("Amy", "Bob", "Cat"):
            _add(db, session.id, name, 1)
        assert _sing_next(db, session.id) == "Amy"
        assert _sing_next(db, session.id) == "Bob"
        _add(db, session.id, "Amy", 2)  # Amy sang, had nothing queued, re-queues
        assert _names(db, session.id) == ["Cat", "Amy"]


def test_singer_with_nothing_queued_is_skipped_but_keeps_their_place(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        for name in ("Amy", "Bob", "Cat"):
            _add(db, session.id, name, 1)
        _add(db, session.id, "Bob", 2)
        _add(db, session.id, "Cat", 2)
        assert _sing_next(db, session.id) == "Amy"  # Amy has nothing left
        assert _names(db, session.id) == ["Bob", "Cat", "Bob", "Cat"]  # Amy's turns skipped
        _add(db, session.id, "Amy", 2)
        assert _names(db, session.id) == ["Bob", "Cat", "Amy", "Bob", "Cat"]  # back in her place


def test_new_singer_joins_at_the_start_of_the_next_round(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        for name in ("Amy", "Bob", "Cat"):
            _add(db, session.id, name, 1)
            _add(db, session.id, name, 2)
        assert _sing_next(db, session.id) == "Amy"
        _add(db, session.id, "Dee", 1)  # joins during the first round
        assert _names(db, session.id)[:5] == ["Bob", "Cat", "Dee", "Amy", "Bob"]


def test_nobody_sings_twice_in_a_row_during_intermission(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        _add(db, session.id, "Amy", 1)
        _add(db, session.id, "Amy", 2)
        _add(db, session.id, "Bob", 1)
        first = _sing_next(db, session.id)  # nothing is NOW_PLAYING afterwards (intermission)
        assert _names(db, session.id)[0] != first


def test_admin_move_up_swaps_singers_places_in_the_rotation(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        for name in ("Amy", "Bob", "Cat"):
            _add(db, session.id, name, 1)
            _add(db, session.id, name, 2)
        qm = QueueManager(db)
        bob_first = [i for i in qm.ordered_up_next(session.id, True) if i.user.display_name == "Bob"][0]
        qm.move_item(bob_first.id, "up", True)
        assert _names(db, session.id) == ["Bob", "Amy", "Cat", "Bob", "Amy", "Cat"]
