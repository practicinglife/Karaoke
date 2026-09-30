"""Pytest fixtures."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app, create_runtime_state
from config import AppConfig
from karaoke.services import create_or_get_user, create_session, set_setting


@pytest.fixture()
def test_karaoke_folder(tmp_path: Path) -> Path:
    root = tmp_path / "TestKaraoke"
    (root / "Country").mkdir(parents=True)
    (root / "Rock").mkdir(parents=True)
    (root / "Pop").mkdir(parents=True)
    (root / "Country" / "Garth Brooks - Friends in Low Places.mp3").write_text("a")
    (root / "Country" / "Garth Brooks - Friends in Low Places.cdg").write_text("b")
    (root / "Rock" / "Journey - Don't Stop Believin.zip").write_text("z")
    (root / "Rock" / "Bon Jovi - Wanted Dead or Alive.mp3").write_text("z")
    (root / "Pop" / "ABBA - Dancing Queen.mp4").write_text("z")
    return root


@pytest.fixture()
def app(tmp_path: Path, test_karaoke_folder: Path):
    db_file = tmp_path / "karaoke_test.db"
    config = AppConfig(
        database_url=f"sqlite:///{db_file.as_posix()}",
        secret_key="test-secret",
        port=5050,
    )
    state = create_runtime_state(config)
    with state.db.session_scope() as db:
        set_setting(db, "karaoke_folder", str(test_karaoke_folder))
        set_setting(db, "web_server_port", "5050")
        create_session(db, "Test House")
        create_or_get_user(db, "Dale")
    flask_app = create_app(runtime_state=state, config=config)
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()
