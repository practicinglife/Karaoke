"""User persistence and lookup tests."""

from sqlalchemy import select

from karaoke.models import User
from karaoke.services import create_or_get_user, get_user_by_name, list_users


def test_user_creation(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Melissa")
        assert user.id is not None
        assert user.display_name == "Melissa"


def test_returning_user_lookup(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        first = create_or_get_user(db, "Mike")
        second = create_or_get_user(db, "mike")
        assert first.id == second.id
        lookup = get_user_by_name(db, "MIKE")
        assert lookup is not None
        assert lookup.id == first.id


def test_many_users_creation(app) -> None:
    with app.runtime_state.db.session_scope() as db:
        for i in range(250):
            create_or_get_user(db, f"User {i}")
        users = list_users(db)
        assert len(users) >= 250
        count = len(list(db.scalars(select(User))))
        assert count >= 250

