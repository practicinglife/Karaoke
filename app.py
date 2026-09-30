"""Karaoke Ticker Flask entrypoint."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread

from flask import Flask
from flask_socketio import SocketIO

# Ensure PyInstaller includes Socket.IO threading async drivers for frozen builds.
try:
    import engineio.async_drivers.threading  # noqa: F401
    import socketio.async_drivers.threading  # noqa: F401
except Exception:
    # Runtime fallback: if imports fail in source mode, Flask-SocketIO may still auto-resolve.
    pass

from config import AppConfig, LOG_DIR
from karaoke.app_state import RuntimeState
from karaoke.database import DatabaseManager
from karaoke.services import ensure_default_settings
from web.routes import register_routes
from web.socket_events import register_socket_events
from karaoke.index_service import BackgroundIndexer


socketio = SocketIO(async_mode="threading")


def configure_logging() -> None:
    """Configure app logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = Path(LOG_DIR) / "karaoke-ticker.log"
    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(
        isinstance(existing, RotatingFileHandler)
        and getattr(existing, "baseFilename", "") == str(log_file)
        for existing in root.handlers
    ):
        root.addHandler(handler)


def create_runtime_state(config: AppConfig | None = None) -> RuntimeState:
    """Create runtime state and initialize database."""
    cfg = config or AppConfig()
    db = DatabaseManager(cfg.database_url)
    db.create_all()
    with db.session_scope() as session:
        ensure_default_settings(session)
    state = RuntimeState(db=db)
    # Start background indexer to maintain static client index. It will skip indexing
    # while a house session is running.
    try:
        indexer = BackgroundIndexer(state, interval_seconds=300)
        indexer.start()
        state.indexer = indexer
    except Exception:
        # Do not fail creation if background indexer cannot start; continue without it.
        pass
    return state


def create_app(
    runtime_state: RuntimeState | None = None, config: AppConfig | None = None
) -> Flask:
    """Create and configure Flask app."""
    cfg = config or AppConfig()
    configure_logging()
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    app.config["SECRET_KEY"] = cfg.secret_key
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    state = runtime_state or create_runtime_state(cfg)
    register_routes(app, state, socketio)
    register_socket_events(socketio)
    socketio.init_app(app)
    app.runtime_state = state  # type: ignore[attr-defined]
    app.karaoke_config = cfg  # type: ignore[attr-defined]
    return app


def start_server_thread(app: Flask, host: str, port: int) -> Thread:
    """Start Flask-SocketIO server in a daemon thread."""

    def run() -> None:
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)

    thread = Thread(target=run, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    application = create_app()
    cfg = AppConfig()
    socketio.run(
        application,
        host=cfg.host,
        port=cfg.port,
        allow_unsafe_werkzeug=True,
    )
