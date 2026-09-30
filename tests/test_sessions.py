"""Session and house code tests."""

from karaoke.services import (
    active_session,
    create_or_get_user,
    create_session,
    create_song,
    stop_session,
    validate_house_code,
)


def test_session_creation_and_house_code_validation(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = create_session(db, "Cooper Karaoke")
        assert len(session.house_code) == 6
        valid = validate_house_code(db, session.house_code)
        assert valid is not None


def test_stopped_session_rejection(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        stop_session(db, session.id)
        assert validate_house_code(db, session.house_code) is None


def test_user_and_song_persistence_between_sessions(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Dale Persist")
        create_song(
            db,
            user_id=user.id,
            title="Persist Song",
            artist="Persist Artist",
            service="youtube",
            url="https://youtu.be/persist",
        )
        running = active_session(db)
        assert running is not None
        stop_session(db, running.id)
        create_session(db, "New House")
    with app.runtime_state.db.session_scope() as db:
        user2 = create_or_get_user(db, "Dale Persist")
        assert user2.id == user.id
        assert len(user2.songs) >= 1
