"""DJ phone page: the host runs the queue and the stage from a phone."""

from __future__ import annotations

from karaoke.models import KaraokeLibrary, QueueItem, Song
from karaoke.queue_manager import COMPLETED, NOW_PLAYING, REMOVED, QueueManager
from karaoke.services import active_session, set_setting
from stage.controller import STARTING
from test_stage import _csrf, _queue, _status, _token, stage  # noqa: F401  (stage is a fixture)


def _headers(app, client) -> dict[str, str]:
    return {"X-Admin-Token": _token(app), "X-CSRF-Token": _csrf(client)}


def _order(app, client) -> list[str]:
    state = client.get("/api/dj/state", headers={"X-Admin-Token": _token(app)}).get_json()
    return [item["user"] for item in state["queue"]]


def test_dj_page_and_qr_need_the_admin_token(app, client, stage) -> None:
    assert client.get("/dj").status_code == 403
    assert client.get("/dj?token=nope").status_code == 403
    page = client.get(f"/dj?token={_token(app)}")
    assert page.status_code == 200 and b"dj-queue" in page.data
    assert client.get("/admin/dj-qr.png").status_code == 403
    qr = client.get(f"/admin/dj-qr.png?token={_token(app)}")
    assert qr.status_code == 200 and qr.mimetype == "image/png"
    assert client.get("/api/dj/state").status_code == 403
    admin = client.get(f"/admin?token={_token(app)}")
    assert b"dj-qr.png" in admin.data


def test_dj_writes_need_the_csrf_token(app, client, stage) -> None:
    response = client.post("/api/dj/singer", json={"name": "Zoe"}, headers={"X-Admin-Token": _token(app)})
    assert response.status_code == 400


def test_dj_reorders_and_removes(app, client, stage) -> None:
    _queue(app, "Alice")
    _queue(app, "Bob")
    carol_id, _ = _queue(app, "Carol")
    headers = _headers(app, client)
    assert _order(app, client) == ["Alice", "Bob", "Carol"]

    assert client.post(f"/api/dj/item/{carol_id}/top", headers=headers).status_code == 200
    assert _order(app, client) == ["Carol", "Alice", "Bob"]
    assert client.post(f"/api/dj/item/{carol_id}/down", headers=headers).status_code == 200
    assert _order(app, client) == ["Alice", "Carol", "Bob"]
    assert client.post(f"/api/dj/item/{carol_id}/remove", headers=headers).status_code == 200
    assert _order(app, client) == ["Alice", "Bob"]
    assert _status(app, carol_id) == REMOVED
    assert client.post(f"/api/dj/item/{carol_id}/top", headers=headers).status_code == 400


def test_move_to_top_with_rotation_puts_that_singer_next(app, stage) -> None:
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "singer_rotation_on", "1")
    _queue(app, "Alice")
    _queue(app, "Bob")
    carol_id, _ = _queue(app, "Carol")
    with app.runtime_state.db.session_scope() as db:
        qm = QueueManager(db)
        session_id = active_session(db).id
        qm.move_to_top(carol_id, True)
        assert [i.user.display_name for i in qm.ordered_up_next(session_id, True)] == ["Carol", "Alice", "Bob"]


def test_dj_adds_a_singer_and_queues_a_library_song_next(app, client, stage) -> None:
    _queue(app, "Alice")
    headers = _headers(app, client)
    response = client.post("/api/dj/singer", json={"name": "Grandma Jo"}, headers=headers)
    assert response.status_code == 200
    singer = response.get_json()
    assert client.post("/api/dj/singer", json={"name": "grandma jo"}, headers=headers).get_json()["id"] == singer["id"]
    assert client.post("/api/dj/singer", json={"name": ""}, headers=headers).status_code == 400

    with app.runtime_state.db.session_scope() as db:
        row = KaraokeLibrary(title="Jolene [SC Karaoke]", artist="Dolly Parton", display_name="Dolly Parton - Jolene [SC Karaoke]",
                             primary_file="c:/k/1.mp3", folder="c:/k", extension=".mp3+.cdg", modified_time="1",
                             file_size=1, active=True, search_blob="dolly parton jolene", tags="")
        db.add(row)
        db.flush()
        library_id = row.id
    found = client.get("/api/dj/search?q=jolene", headers={"X-Admin-Token": _token(app)}).get_json()
    assert [s["title"] for s in found["songs"]] == ["Jolene"]

    body = {"user_id": singer["id"], "library_id": library_id, "title": "Jolene", "artist": "Dolly Parton", "next": True}
    assert client.post("/api/dj/queue", json=body, headers=headers).status_code == 200
    assert _order(app, client) == ["Grandma Jo", "Alice"]
    # Again: the saved song is reused and the waiting one stays where it is.
    assert client.post("/api/dj/queue", json=body, headers=headers).status_code == 200
    assert _order(app, client) == ["Grandma Jo", "Alice"]
    songs = client.get(f"/api/dj/singer/{singer['id']}/songs", headers={"X-Admin-Token": _token(app)}).get_json()
    assert [(s["title"], s["service"]) for s in songs] == [("Jolene", "traditional")]

    # A saved song, to the end of the queue.
    with app.runtime_state.db.session_scope() as db:
        alice_song = db.query(Song).filter(Song.title == "Alice Song").one()
    body = {"user_id": singer["id"], "song_id": alice_song.id}
    assert client.post("/api/dj/queue", json=body, headers=headers).status_code == 400  # not their song
    assert client.post("/api/dj/queue", json={"user_id": 0, "song_id": 1}, headers=headers).status_code == 400


def test_dj_stage_controls(app, client, stage) -> None:
    alice_id, _ = _queue(app, "Alice")
    bob_id, _ = _queue(app, "Bob")
    headers = _headers(app, client)

    assert client.post("/api/dj/stage/end", headers=headers).status_code == 409  # stage closed
    assert client.post("/api/dj/stage/start_next", headers=headers).status_code == 200
    assert stage.state == STARTING and _status(app, alice_id) == NOW_PLAYING

    plays = len([c for c in stage.driver.calls if c[0] == "play"])
    stage.clock_ref.now += 60
    assert client.post("/api/dj/stage/restart", headers=headers).status_code == 200
    assert len([c for c in stage.driver.calls if c[0] == "play"]) == plays + 1
    assert _status(app, alice_id) == NOW_PLAYING

    assert client.post("/api/dj/stage/end", headers=headers).status_code == 200
    assert _status(app, alice_id) == COMPLETED
    stage.clock_ref.now += 60
    assert client.post("/api/dj/stage/start_next", headers=headers).status_code == 200
    assert _status(app, bob_id) == NOW_PLAYING
    assert client.post("/api/dj/stage/nope", headers=headers).status_code == 400
    with app.runtime_state.db.session_scope() as db:
        assert db.get(QueueItem, bob_id).status == NOW_PLAYING
