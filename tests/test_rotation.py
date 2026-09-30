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
        assert names[:4] == ["Mike", "Dale", "Melissa", "Dale"]


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

