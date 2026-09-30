"""Web route and live update tests."""

import json
from pathlib import Path

from sqlalchemy import select

from app import socketio
from karaoke.library_indexer import build_index, search_library
from karaoke.models import QueueItem, Song
from karaoke.queue_manager import QueueManager, REMOVED
from karaoke.services import active_session, create_or_get_user, create_song
from karaoke.services import get_setting, set_setting
from karaoke.services import stop_session


def _csrf(client):
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf"
    return "test-csrf"


def test_guest_join_route_and_user_page(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code
    response = client.get(f"/join?code={code}")
    assert response.status_code == 200

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Dale"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}
    user_page = client.get("/user")
    assert user_page.status_code == 200


def test_guest_traditional_search_uses_indexed_library(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Dale"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    response = client.get("/song/search?service=traditional&q=garth%20brooks&limit=10")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert any(item["artist"] == "Garth Brooks" for item in payload)


def test_guest_traditional_search_returns_video_extension_for_mp4_entries(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Video Finder"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    response = client.get("/song/search?service=traditional&q=dancing%20queen&limit=10")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, list)
    assert any(item.get("extension") == ".mp4" for item in payload)


def test_guest_user_page_marks_queued_songs(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        user = create_or_get_user(db, "Dale")
        lib = search_library(db, "friends in low places")[0]
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        QueueManager(db).add_song(session.id, user.id, song.id)
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Dale"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    response = client.get("/user")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "queued-song" in html
    assert "Queued tonight" in html


def test_guest_user_page_renders_up_next_notification_state(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        user = create_or_get_user(db, "Next Notification User")
        song = create_song(
            db,
            user_id=user.id,
            title="Next Song",
            artist="Next Artist",
            service="youtube",
            url="https://youtu.be/nextsong",
        )
        QueueManager(db).add_song(session.id, user.id, song.id)
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "existing_name": "Next Notification User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    response = client.get("/user")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="user-queue-notification"' in html
    assert 'data-phase="up-next"' in html
    assert 'data-song="Next Song"' in html
    assert 'js/user-notifications.js' in html


def test_guest_user_page_renders_up_now_notification_state(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        user = create_or_get_user(db, "Now Notification User")
        song = create_song(
            db,
            user_id=user.id,
            title="Now Song",
            artist="Now Artist",
            service="youtube",
            url="https://youtu.be/nowsong",
        )
        item = QueueManager(db).add_song(session.id, user.id, song.id)
        QueueManager(db).mark_now_playing(item.id)
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "existing_name": "Now Notification User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    response = client.get("/user")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-phase="up-now"' in html
    assert 'data-song="Now Song"' in html
    assert 'data-artist="Now Artist"' in html


def test_admin_and_ticker_routes(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        admin_token = session.admin_token
        ticker_token = session.ticker_token
    assert client.get(f"/admin?token={admin_token}").status_code == 200
    assert client.get(f"/ticker?token={ticker_token}").status_code == 200
    assert client.get("/admin").status_code == 403
    assert client.get("/admin?token=bad-token").status_code == 403
    assert client.get("/ticker?token=bad-token").status_code == 403
    assert client.get("/api/queue", headers={"X-Admin-Token": "bad-token"}).status_code == 403
    assert client.get("/api/ticker", headers={"X-Ticker-Token": "bad-token"}).status_code == 403


def test_websocket_queue_update_event(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        user = create_or_get_user(db, "Socket Tester")
        lib = search_library(db, "friends in low places")[0]
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        QueueManager(db).add_song(session.id, user.id, song.id)
    test_client = socketio.test_client(app)
    socketio.emit("queue_updated", {"status": "ok"})
    events = test_client.get_received()
    assert any(event["name"] == "queue_updated" for event in events)
    test_client.disconnect()


def test_queue_add_route_emits_live_update(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        running = active_session(db)
        assert running is not None
        user = create_or_get_user(db, "Live Queue User")
        song = create_song(
            db,
            user_id=user.id,
            title="Live Update Song",
            artist="Live Artist",
            service="youtube",
            url="https://youtu.be/liveupdatesong",
        )
        code = running.house_code
        song_id = song.id

    csrf = _csrf(client)
    client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "existing_name": "Live Queue User"},
        follow_redirects=False,
    )
    sio_client = socketio.test_client(app)
    csrf = _csrf(client)
    response = client.post(
        f"/queue/add/{song_id}",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    events = sio_client.get_received()
    assert any(event["name"] == "queue_updated" for event in events)
    sio_client.disconnect()


def test_queue_add_route_second_click_removes_waiting_song(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        running = active_session(db)
        assert running is not None
        user = create_or_get_user(db, "Toggle Queue User")
        song = create_song(
            db,
            user_id=user.id,
            title="Toggle Queue Song",
            artist="Toggle Artist",
            service="youtube",
            url="https://youtu.be/togglequeuesong",
        )
        code = running.house_code
        song_id = song.id

    csrf = _csrf(client)
    client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "existing_name": "Toggle Queue User"},
        follow_redirects=False,
    )

    csrf = _csrf(client)
    first_response = client.post(
        f"/queue/add/{song_id}",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert first_response.status_code == 200
    assert b"Added to queue." in first_response.data

    sio_client = socketio.test_client(app)
    csrf = _csrf(client)
    second_response = client.post(
        f"/queue/add/{song_id}",
        data={"csrf_token": csrf},
        follow_redirects=True,
    )
    assert second_response.status_code == 200
    assert b"Removed from queue." in second_response.data

    events = sio_client.get_received()
    queue_updates = [event for event in events if event["name"] == "queue_updated"]
    assert queue_updates
    assert queue_updates[-1]["args"][0]["queue_all"] == []
    sio_client.disconnect()

    with app.runtime_state.db.session_scope() as db:
        queue_items = list(db.scalars(select(QueueItem).where(QueueItem.song_id == song_id)))

    assert len(queue_items) == 1
    assert queue_items[0].status == REMOVED

    user_page = client.get("/user")
    assert user_page.status_code == 200
    assert "queued-song" not in user_page.get_data(as_text=True)


def test_admin_action_clear_queue_emits_live_update_and_clears_user_highlight(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        running = active_session(db)
        assert running is not None
        user = create_or_get_user(db, "Clear Queue User")
        song = create_song(
            db,
            user_id=user.id,
            title="Clear Queue Song",
            artist="Clear Artist",
            service="youtube",
            url="https://youtu.be/clearqueuesong",
        )
        QueueManager(db).add_song(running.id, user.id, song.id)
        code = running.house_code
        token = running.admin_token

    csrf = _csrf(client)
    client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "existing_name": "Clear Queue User"},
        follow_redirects=False,
    )
    sio_client = socketio.test_client(app)
    csrf = _csrf(client)
    response = client.post(
        "/admin/action",
        data={"csrf_token": csrf, "action": "clear"},
        headers={"X-Admin-Token": token},
        follow_redirects=False,
    )
    assert response.status_code == 200
    events = sio_client.get_received()
    queue_updates = [event for event in events if event["name"] == "queue_updated"]
    assert queue_updates and queue_updates[-1]["args"][0]["queue_all"] == []
    user_page = client.get("/user")
    assert user_page.status_code == 200
    assert "queued-song" not in user_page.get_data(as_text=True)
    sio_client.disconnect()


def test_join_rejected_after_session_stopped(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code
        stop_session(db, session.id)
    csrf = _csrf(client)
    response = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Late Guest"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Invalid or expired house code" in response.data


def test_admin_action_play_uses_external_application_mode_and_marks_now_playing(client, app, test_karaoke_folder, monkeypatch) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        set_setting(db, "playback_mode", "external_application")
        set_setting(db, "external_application_path", r"C:\Kanto\KantoPlayer.exe")
        user = create_or_get_user(db, "Admin Play User")
        lib = search_library(db, "friends in low places")[0]
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        lib.active = False
        item = QueueManager(db).add_song(session.id, user.id, song.id)
        token = session.admin_token
        queued_item_id = item.id

    launch_calls: list[dict] = []

    def capture_launch(file_path: str, *args, **kwargs):
        launch_calls.append({"file_path": file_path, "args": args, "kwargs": kwargs})

    monkeypatch.setattr("karaoke.launcher.launch_traditional_song", capture_launch)
    monkeypatch.setattr("karaoke.launcher.launch_url", lambda *args, **kwargs: None)

    csrf = _csrf(client)
    response = client.post(
        "/admin/action",
        data={"csrf_token": csrf, "action": "play", "queue_item_id": str(queued_item_id)},
        headers={"X-Admin-Token": token},
    )

    assert response.status_code == 200
    assert launch_calls and launch_calls[0]["kwargs"].get("external_application_path") == r"C:\Kanto\KantoPlayer.exe"
    with app.runtime_state.db.session_scope() as db:
        qm = QueueManager(db)
        now_playing = qm.now_playing(session.id)
        assert now_playing is not None
        assert now_playing.id == queued_item_id


def test_settings_persist_remote_traditional_server_url(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        token = session.admin_token

    csrf = _csrf(client)
    response = client.post(
        f"/settings?token={token}",
        data={
            "csrf_token": csrf,
            "house_name": "House",
            "karaoke_folder": "",
            "external_application_path": r"C:\Kanto\KantoPlayer.exe",
            "playback_mode": "built_in",
            "traditional_karaoke_server_url": "https://karaoke.example.com",
            "web_server_port": "8080",
            "ticker_upcoming_count": "5",
            "singer_rotation_on": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.runtime_state.db.session_scope() as db:
        assert get_setting(db, "playback_mode") == "built_in"
        assert get_setting(db, "external_application_path") == r"C:\Kanto\KantoPlayer.exe"
        assert get_setting(db, "kanto_executable_path") == r"C:\Kanto\KantoPlayer.exe"
        assert get_setting(db, "traditional_karaoke_server_url") == "https://karaoke.example.com"


def test_admin_action_opens_local_player_for_traditional_song(client, app, test_karaoke_folder, monkeypatch) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        set_setting(db, "playback_mode", "built_in")
        user = create_or_get_user(db, "Web Player User")
        lib = search_library(db, "friends in low places")[0]
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        item = QueueManager(db).add_song(session.id, user.id, song.id)
        token = session.admin_token
        queued_item_id = item.id

    launch_urls: list[str] = []

    def capture_launch(url: str, *args, **kwargs):
        launch_urls.append(url)

    monkeypatch.setattr("karaoke.launcher.launch_url", capture_launch)

    csrf = _csrf(client)
    response = client.post(
        "/admin/action",
        data={"csrf_token": csrf, "action": "play", "queue_item_id": str(queued_item_id)},
        headers={"X-Admin-Token": token},
    )

    assert response.status_code == 200
    assert launch_urls and "/player?token=" in launch_urls[0]
    assert f"song_id={lib.id}" in launch_urls[0]
    with app.runtime_state.db.session_scope() as db:
        qm = QueueManager(db)
        now_playing = qm.now_playing(session.id)
        assert now_playing is not None
        assert now_playing.id == queued_item_id


def test_player_route_includes_selected_song_data(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        user = create_or_get_user(db, "Player Route User")
        lib = search_library(db, "friends in low places")[0]
        song = create_song(
            db,
            user_id=user.id,
            title="Friends in Low Places",
            artist="Garth Brooks",
            service="traditional",
            karaoke_library_id=lib.id,
        )
        QueueManager(db).add_song(session.id, user.id, song.id)
        token = session.admin_token

    response = client.get(f"/player?token={token}&song_id={lib.id}")
    assert response.status_code == 200
    assert f'window.KT_PLAYER = {{ token: "{token}", songId: {lib.id}, song: '.encode("utf-8") in response.data
    assert b'preload="auto"' in response.data
    assert b"search-input" not in response.data
    assert b"song-select" not in response.data
    assert b"player-now-playing" not in response.data


def test_player_script_requires_manual_playback_start() -> None:
    player_js = Path(__file__).resolve().parents[1] / "web" / "static" / "js" / "player.js"
    content = player_js.read_text(encoding="utf-8")
    assert ".then(() => startPlayback())" not in content
    assert "videoPlayer || document.documentElement" in content
    assert "canvas || document.documentElement" in content
    assert "canvas.parentElement" not in content


def test_player_media_routes_serve_indexed_media(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        token = session.admin_token
        lib = search_library(db, "friends in low places")[0]

    audio_response = client.get(f"/player/media/{lib.id}/audio?token={token}")
    cdg_response = client.get(f"/player/media/{lib.id}/cdg?token={token}")

    assert audio_response.status_code == 200
    assert cdg_response.status_code == 200
    assert audio_response.mimetype.startswith("audio/") or audio_response.mimetype == "application/octet-stream"
    assert cdg_response.mimetype == "application/octet-stream"


def test_player_route_includes_video_song_data_for_mp4_entries(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        token = session.admin_token
        lib = search_library(db, "dancing queen")[0]

    response = client.get(f"/player?token={token}&song_id={lib.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '"media_kind": "video"' in body
    assert f'/player/media/{lib.id}/video?token=' in body


def test_player_media_video_route_serves_mp4(client, app, test_karaoke_folder) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        build_index(db, str(test_karaoke_folder))
        token = session.admin_token
        lib = search_library(db, "dancing queen")[0]

    video_response = client.get(f"/player/media/{lib.id}/video?token={token}")

    assert video_response.status_code == 200
    assert video_response.mimetype.startswith("video/")


def test_admin_action_invalid_security_tokens(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        token = session.admin_token
    csrf = _csrf(client)
    bad_csrf = client.post(
        "/admin/action",
        data={"csrf_token": "wrong", "action": "next"},
        headers={"X-Admin-Token": token},
    )
    assert bad_csrf.status_code == 400
    bad_admin = client.post(
        "/admin/action",
        data={"csrf_token": csrf, "action": "next"},
        headers={"X-Admin-Token": "bad-token"},
    )
    assert bad_admin.status_code == 403


def test_settings_validation_failures(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        token = session.admin_token
    csrf = _csrf(client)
    bad_port = client.post(
        f"/settings?token={token}",
        data={
            "csrf_token": csrf,
            "house_name": "House",
            "karaoke_folder": "",
            "external_application_path": "",
            "playback_mode": "built_in",
            "web_server_port": "70000",
            "ticker_upcoming_count": "5",
            "singer_rotation_on": "on",
        },
        follow_redirects=True,
    )
    assert bad_port.status_code == 200
    assert b"Port must be 1-65535" in bad_port.data

    csrf = _csrf(client)
    bad_upcoming = client.post(
        f"/settings?token={token}",
        data={
            "csrf_token": csrf,
            "house_name": "House",
            "karaoke_folder": "",
            "external_application_path": "",
            "playback_mode": "built_in",
            "web_server_port": "8080",
            "ticker_upcoming_count": "0",
            "singer_rotation_on": "on",
        },
        follow_redirects=True,
    )
    assert bad_upcoming.status_code == 200
    assert b"Upcoming singers must be 1-20" in bad_upcoming.data

    csrf = _csrf(client)
    bad_remote_url = client.post(
        f"/settings?token={token}",
        data={
            "csrf_token": csrf,
            "house_name": "House",
            "karaoke_folder": "",
            "external_application_path": "",
            "playback_mode": "built_in",
            "traditional_karaoke_server_url": "https://karaoke.example.com/traditional",
            "web_server_port": "8080",
            "ticker_upcoming_count": "5",
            "singer_rotation_on": "on",
        },
        follow_redirects=True,
    )
    assert bad_remote_url.status_code == 200
    assert b"Traditional Karaoke Server URL must be a valid http(s) base URL." in bad_remote_url.data


def test_guest_bulk_add_accepts_spotify_and_rejects_duplicate_lines(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Bulk Spotify User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    payload = "\n".join(
        [
            "provider,url,artist,title",
            "spotify|https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6|Journey|Separate Ways",
            "spotify|https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6|Journey|Separate Ways",
            "youtube|https://youtu.be/test123|Journey|Faithfully",
        ]
    )
    csrf = _csrf(client)
    response = client.post(
        "/song/bulk-add",
        data={
            "csrf_token": csrf,
            "default_service": "spotify",
            "bulk_lines": payload,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Bulk Spotify User")
        songs = list(db.scalars(select(Song).where(Song.user_id == user.id)))
        assert len(songs) == 2
        services = {song.service for song in songs}
        assert services == {"spotify", "youtube"}


def test_guest_bulk_add_rejects_invalid_spotify_url(client, app) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Invalid Link User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    csrf = _csrf(client)
    response = client.post(
        "/song/bulk-add",
        data={
            "csrf_token": csrf,
            "default_service": "spotify",
            "bulk_lines": "spotify|https://example.com/track/abc|Nope|Bad Link",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.runtime_state.db.session_scope() as db:
        user = create_or_get_user(db, "Invalid Link User")
        songs = list(db.scalars(select(Song).where(Song.user_id == user.id)))
        assert songs == []


def test_spotify_link_metadata_parses_non_generic_title(client, app, monkeypatch) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Spotify Metadata User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    class _FakeSpotifyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"title": "Separate Ways by Journey on Spotify", "provider_name": "Spotify"}).encode("utf-8")

    monkeypatch.setattr("web.routes.urlopen", lambda _req, timeout=6: _FakeSpotifyResponse())

    metadata_response = client.get(
        "/song/link-metadata?service=spotify&url=https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
    )
    assert metadata_response.status_code == 200
    payload = metadata_response.get_json()
    assert payload == {"ok": True, "title": "Separate Ways", "artist": "Journey"}


def test_spotify_link_metadata_falls_back_to_embedded_page_metadata(client, app, monkeypatch) -> None:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        assert session is not None
        code = session.house_code

    csrf = _csrf(client)
    joined = client.post(
        "/join",
        data={"csrf_token": csrf, "code": code, "name": "Spotify Fallback User"},
        follow_redirects=False,
    )
    assert joined.status_code in {302, 303}

    class _FakeSpotifyResponse:
        def __init__(self, body: str, final_url: str):
            self._body = body
            self._final_url = final_url

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return self._body.encode("utf-8")

        def geturl(self):
            return self._final_url

    def _fake_urlopen(req, timeout=6):
        _ = timeout
        url = req.full_url
        if "open.spotify.com/oembed" in url:
            return _FakeSpotifyResponse(json.dumps({"title": "Spotify", "provider_name": "Spotify"}), url)
        return _FakeSpotifyResponse(
            '<meta property="og:title" content="Separate Ways">\n<meta property="og:description" content="Separate Ways · Song · Journey">',
            "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6",
        )

    monkeypatch.setattr("web.routes.urlopen", _fake_urlopen)

    metadata_response = client.get(
        "/song/link-metadata?service=spotify&url=https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
    )
    assert metadata_response.status_code == 200
    payload = metadata_response.get_json()
    assert payload == {"ok": True, "title": "Separate Ways", "artist": "Journey"}
