"""Socket.IO event registrations."""

from __future__ import annotations


def register_socket_events(socketio) -> None:
    """Register websocket events."""

    @socketio.on("connect")
    def on_connect():
        return {"ok": True}

