"""Stage automation tests (controller, routes) with a fake browser driver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from karaoke.models import QueueItem
from karaoke.queue_manager import COMPLETED, NOW_PLAYING, QueueManager
from karaoke.services import active_session, create_or_get_user, create_song, get_setting, set_setting
from stage.controller import IDLE, INTERMISSION, PLAYING, STARTING, TEACHING, StageController
from stage import plans
from stage.plans import load_selectors, normalize_stage_url, save_taught_steps, stage_service_for


class FakeDriver:
    def __init__(self, on_event) -> None:
        self.on_event = on_event
        self.is_running = False
        self.calls: list[tuple] = []

    def start(self, *, monitor_rect=None, fullscreen=True, extra_args=None) -> None:
        self.is_running = True
        self.calls.append(("start", monitor_rect, fullscreen))

    def place(self, monitor_rect, fullscreen: bool) -> None:
        self.calls.append(("place", monitor_rect, fullscreen))

    def show(self, url: str) -> None:
        self.calls.append(("show", url))

    def play(self, play_id: int, service: str, url: str, automate: bool = True) -> None:
        self.calls.append(("play", play_id, service, url))
        self.automate = automate

    def close(self, wait_seconds: float = 0.0) -> None:
        self.is_running = False

    def test_selectors(self, timeout: float = 20.0) -> dict[str, Any]:
        return {"service": "youtube", "selectors": []}

    def teach_start(self, service: str, url: str, monitor_rect) -> None:
        self.calls.append(("teach_start", service, url, monitor_rect))
        self.recorded = [{"click": ["button[aria-label=\"Lyrics\"]"], "optional": True, "timeout": 8000}]

    def teach_status(self) -> list[str]:
        return ["Click 'Lyrics'"]

    def teach_stop(self, timeout: float = 20.0) -> list[dict[str, Any]]:
        return [{"wait_playing": 6000}, *self.recorded]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def stage(app):
    clock = Clock()
    events: list[tuple[str, dict]] = []
    controller = StageController(
        app.runtime_state.db,
        emit=lambda event, payload: events.append((event, payload)),
        emit_queue=lambda: None,
        driver_factory=FakeDriver,
        monitor_rect=lambda n: (1920 * (n - 1), 0, 1920, 1080),
        clock=clock,
    )
    controller.clock_ref = clock  # type: ignore[attr-defined]
    controller.events = events  # type: ignore[attr-defined]
    app.runtime_state.stage = controller
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "stage_enabled", "1")
        set_setting(db, "singer_rotation_on", "0")
    return controller


def _queue(app, singer: str, url: str = "https://www.youtube.com/watch?v=abc123") -> tuple[int, int]:
    with app.runtime_state.db.session_scope() as db:
        session = active_session(db)
        user = create_or_get_user(db, singer)
        song = create_song(db, user_id=user.id, title=f"{singer} Song", artist="Artist", service="youtube", url=url)
        item = QueueManager(db).add_song(session.id, user.id, song.id)
        return item.id, user.id


def _status(app, item_id: int) -> str:
    with app.runtime_state.db.session_scope() as db:
        return db.get(QueueItem, item_id).status


def _token(app) -> str:
    with app.runtime_state.db.session_scope() as db:
        return active_session(db).admin_token


def _csrf(client) -> str:
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf"
    return "test-csrf"


def test_admin_play_runs_song_on_stage_then_intermission_after_end(app, client, stage) -> None:
    item_id, _ = _queue(app, "Alice")
    second_id, _ = _queue(app, "Bob")
    response = client.post(
        "/admin/action",
        data={"csrf_token": _csrf(client), "action": "play", "queue_item_id": str(item_id)},
        headers={"X-Admin-Token": _token(app)},
    )
    assert response.status_code == 200
    assert stage.state == STARTING
    play = [c for c in stage.driver.calls if c[0] == "play"][-1]
    assert play[2:] == ("youtube", "https://www.youtube.com/watch?v=abc123")
    assert _status(app, item_id) == NOW_PLAYING

    stage.handle_driver_event("started", play[1], "")
    assert stage.state == PLAYING

    stage.handle_driver_event("ended", play[1], "")
    assert stage.state == INTERMISSION
    assert _status(app, item_id) == COMPLETED
    assert stage.driver.calls[-1][0] == "show" and "/stage?token=" in stage.driver.calls[-1][1]
    assert stage.snapshot()["next"]["item_id"] == second_id


def test_stale_driver_events_are_ignored(app, stage) -> None:
    item_id, _ = _queue(app, "Alice")
    stage.start_item(item_id)
    stage.handle_driver_event("ended", stage.play_id - 1, "")
    assert stage.state == STARTING


def test_phone_ready_only_works_for_the_singer_up_next(app, stage) -> None:
    item_id, alice_id = _queue(app, "Alice")
    _, bob_id = _queue(app, "Bob")
    stage.open()
    assert stage.state == INTERMISSION

    ok, message = stage.singer_ready("phone", user_id=bob_id)
    assert not ok and "not your turn" in message.lower()

    ok, _ = stage.singer_ready("phone", user_id=alice_id)
    assert ok
    assert stage.state == STARTING
    assert _status(app, item_id) == NOW_PLAYING

    # A second press while starting is ignored.
    assert not stage.singer_ready("button")[0]


def test_countdown_expiry_bump_moves_singer_down(app, stage) -> None:
    first_id, _ = _queue(app, "Alice")
    second_id, _ = _queue(app, "Bob")
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "countdown_expiry_action", "bump")
        set_setting(db, "countdown_seconds", "30")
    stage.open()
    stage.tick()
    assert stage.snapshot()["countdown_ends_at"] == int((1000 + 30) * 1000)

    stage.clock_ref.now += 31
    stage.tick()
    assert stage.snapshot()["next"]["item_id"] == second_id
    assert stage.state == INTERMISSION


def test_countdown_expiry_start_starts_the_song(app, stage) -> None:
    first_id, _ = _queue(app, "Alice")
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "countdown_expiry_action", "start")
        set_setting(db, "countdown_seconds", "10")
    stage.open()
    stage.tick()
    stage.clock_ref.now += 11
    stage.tick()
    assert stage.state == STARTING
    assert _status(app, first_id) == NOW_PLAYING


def test_admin_next_in_stage_mode_goes_to_intermission(app, client, stage) -> None:
    item_id, _ = _queue(app, "Alice")
    _queue(app, "Bob")
    stage.start_item(item_id)
    response = client.post(
        "/admin/action",
        data={"csrf_token": _csrf(client), "action": "next"},
        headers={"X-Admin-Token": _token(app)},
    )
    assert response.status_code == 200
    assert stage.state == INTERMISSION
    assert _status(app, item_id) == COMPLETED


def test_driver_closed_returns_to_idle(app, stage) -> None:
    stage.open()
    stage.handle_driver_event("closed", 0, "Stage browser closed.")
    assert stage.state == IDLE
    assert stage.snapshot()["message"] == "Stage browser closed."


def test_network_ready_button_requires_key(app, client, stage) -> None:
    _queue(app, "Alice")
    stage.open()
    assert client.post("/api/stage/ready?key=wrong").status_code == 403
    with app.runtime_state.db.session_scope() as db:
        key = get_setting(db, "stage_button_secret")
    assert key
    response = client.get(f"/api/stage/ready?key={key}")
    assert response.status_code == 200
    assert stage.state == STARTING


def test_stage_page_and_filler_routes(app, client, stage, tmp_path) -> None:
    folder = tmp_path / "filler"
    folder.mkdir()
    (folder / "song.mp3").write_bytes(b"ID3")
    (folder / "notes.txt").write_text("skip me")
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "intermission_folder", str(folder))
    token = _token(app)
    assert client.get(f"/stage?token={token}").status_code == 200
    assert client.get(f"/stage/filler?token={token}").get_json() == {"count": 1}
    assert client.get(f"/stage/filler/0?token={token}").status_code == 200
    assert client.get(f"/stage/filler/1?token={token}").status_code == 404
    assert client.get("/stage/filler/0").status_code == 403


def test_service_mapping_and_url_normalization() -> None:
    assert stage_service_for("youtube", "https://music.youtube.com/watch?v=x") == "youtube_music"
    assert stage_service_for("youtube", "https://youtu.be/x") == "youtube"
    assert stage_service_for("spotify", "https://open.spotify.com/track/x") == "spotify"
    assert stage_service_for("traditional", None) == "traditional"
    assert stage_service_for("youtube", None) is None
    album_link = "https://music.apple.com/us/album/some-album/111?i=222"
    assert normalize_stage_url("apple_music", album_link) == album_link


def test_open_places_window_on_chosen_monitor_and_move_saves_setting(app, client, stage) -> None:
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "stage_monitor", "2")
    stage.open()
    assert stage.driver.calls[0] == ("start", (1920, 0, 1920, 1080), True)

    response = client.post(
        "/admin/stage",
        data={"csrf_token": _csrf(client), "action": "move", "monitor": "1"},
        headers={"X-Admin-Token": _token(app)},
    )
    assert response.status_code == 200
    assert stage.driver.calls[-1] == ("place", (0, 0, 1920, 1080), True)
    with app.runtime_state.db.session_scope() as db:
        assert get_setting(db, "stage_monitor") == "1"


def test_teach_records_and_saves_steps_for_service(app, client, stage, tmp_path, monkeypatch) -> None:
    overrides = tmp_path / "stage_selectors.json"
    monkeypatch.setattr(plans, "overrides_path", lambda: overrides)
    token = _token(app)

    def post(action: str, **extra):
        return client.post(
            "/admin/stage",
            data={"csrf_token": _csrf(client), "action": action, **extra},
            headers={"X-Admin-Token": token},
        )

    assert post("teach_start", service="apple_music", url="not a link").status_code == 400
    response = post("teach_start", service="apple_music", url="https://music.apple.com/us/album/a/1?i=2")
    assert response.status_code == 200
    assert stage.state == TEACHING
    assert stage.driver.calls[-1] == ("teach_start", "apple_music", "https://music.apple.com/us/album/a/1?i=2", (0, 0, 1920, 1080))
    assert stage.snapshot()["teach"] == {"service": "apple_music", "steps": ["Click 'Lyrics'"]}

    saved = post("teach_save").get_json()
    assert saved["saved_steps"] == 2
    assert stage.state == INTERMISSION
    merged = load_selectors()["apple_music"]
    assert merged["steps"][1]["click"] == ['button[aria-label="Lyrics"]']
    assert merged["hosts"] == ["music.apple.com"]  # built-in fields are kept

    assert post("teach_reset", service="apple_music").status_code == 200
    assert load_selectors()["apple_music"]["steps"][1].get("click") != ['button[aria-label="Lyrics"]']


def test_teach_cancel_saves_nothing(app, stage, tmp_path, monkeypatch) -> None:
    overrides = tmp_path / "stage_selectors.json"
    monkeypatch.setattr(plans, "overrides_path", lambda: overrides)
    stage.teach_start("spotify", "https://open.spotify.com/track/x")
    stage.teach_finish(save=False)
    assert not overrides.exists()
    assert stage.state == INTERMISSION


def test_overrides_merge_per_service(tmp_path) -> None:
    overrides = tmp_path / "o.json"
    save_taught_steps("spotify", [{"press": "f"}], overrides=overrides)
    merged = load_selectors(overrides=overrides)
    assert merged["spotify"]["steps"] == [{"press": "f"}]
    assert merged["spotify"]["hosts"] == ["open.spotify.com"]
    assert merged["youtube"]["steps"] == load_selectors(overrides=tmp_path / "missing.json")["youtube"]["steps"]


def test_recently_played_can_be_played_again_on_open_stage_even_if_setting_off(app, client, stage) -> None:
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "stage_enabled", "0")
    item_id, _ = _queue(app, "Alice")
    stage.open()  # window open, Settings checkbox off
    stage.start_item(item_id)
    stage.song_finished()
    assert _status(app, item_id) == COMPLETED

    token = _token(app)
    recent = client.get("/api/queue", headers={"X-Admin-Token": token}).get_json()["recent"]
    assert [r["id"] for r in recent] == [item_id]

    response = client.post(
        "/admin/action",
        data={"csrf_token": _csrf(client), "action": "play", "queue_item_id": str(item_id)},
        headers={"X-Admin-Token": token},
    )
    assert response.status_code == 200
    assert stage.state == STARTING
    assert _status(app, item_id) == NOW_PLAYING


def test_preview_clip_ending_is_reported_not_treated_as_song_end(monkeypatch) -> None:
    from stage.browser import StageBrowser

    events: list[tuple] = []
    browser = StageBrowser(profile_dir=Path("unused"), on_event=lambda *e: events.append(e))
    browser._watch = {"play_id": 7, "service": "apple_music", "spec": {}, "deadline": 0, "started": True, "attention": False}
    monkeypatch.setattr(browser, "_media_state", lambda page: {"started": True, "ended": True, "duration": 30.0, "position": 30.0})
    monkeypatch.setattr(browser, "_first_visible", lambda page, selectors: None)
    browser._poll(page=None)
    assert events and events[0][0] == "attention" and "preview" in events[0][2]

    events.clear()
    browser._watch = {"play_id": 8, "service": "apple_music", "spec": {}, "deadline": 0, "started": True, "attention": False}
    monkeypatch.setattr(browser, "_media_state", lambda page: {"started": True, "ended": True, "duration": 241.0, "position": 241.0})
    browser._poll(page=None)
    assert events == [("ended", 8, "")]


def test_admin_play_opens_stage_and_plays_even_when_stage_closed(app, client, stage) -> None:
    item_id, _ = _queue(app, "Alice")
    assert not stage.driver.is_running
    response = client.post(
        "/admin/action",
        data={"csrf_token": _csrf(client), "action": "play", "queue_item_id": str(item_id)},
        headers={"X-Admin-Token": _token(app)},
    )
    assert response.status_code == 200
    assert stage.driver.is_running
    assert [c[0] for c in stage.driver.calls][-1] == "play"
    assert stage.snapshot()["now"]["user"] == "Alice"


def test_mic_stand_page_and_button(app, client, stage) -> None:
    with app.runtime_state.db.session_scope() as db:
        key = get_setting(db, "stage_button_secret")
    assert client.get("/mic").status_code == 403
    assert client.get("/mic?key=nope").status_code == 403
    page = client.get(f"/mic?key={key}")
    assert page.status_code == 200 and b"mic-start" in page.data

    qr = client.get(f"/admin/mic-qr.png?token={_token(app)}")
    assert qr.status_code == 200 and qr.mimetype == "image/png"
    assert client.get("/admin/mic-qr.png").status_code == 403

    # Stage closed: START opens it and plays whoever is up.
    _queue(app, "Bob")
    assert stage.state == IDLE
    response = client.post(f"/api/stage/ready?key={key}")
    assert response.status_code == 200
    assert stage.state == STARTING
    assert stage.snapshot()["now"]["user"] == "Bob"


def test_apple_steps_target_the_linked_track_row() -> None:
    from stage.browser import resolve_spec

    spec = load_selectors(overrides=Path("missing.json"))["apple_music"]
    with_track = resolve_spec(spec, {"track_id": "305517585"})
    clicks = [s["click"] for s in with_track["steps"] if "click" in s]
    assert "a[href$='/305517585']" in clicks[0][0]          # the highlighted track's own Play
    assert not any("click-action" in sel for sel in clicks[0])  # never the album's Play
    assert any("lyrics-button" in sel for c in clicks for sel in c)
    assert any("lyrics-fullscreen-button" in sel for c in clicks for sel in c)

    no_track = resolve_spec(spec, {"track_id": ""})
    first_click = [s["click"] for s in no_track["steps"] if "click" in s][0]
    assert first_click[0] == "button[data-testid='click-action'][aria-label='Play']"
    assert all("Shuffle" in sel or "aria-label='Play'" in sel for sel in first_click)  # never Shuffle


def test_track_title_change_counts_as_song_end(monkeypatch) -> None:
    from stage.browser import StageBrowser

    events: list[tuple] = []
    browser = StageBrowser(profile_dir=Path("unused"), on_event=lambda *e: events.append(e))
    browser._watch = {"play_id": 3, "service": "apple_music", "spec": {}, "deadline": 1e12,
                      "started": False, "attention": False, "title": ""}
    monkeypatch.setattr(browser, "_first_visible", lambda page, selectors: None)
    states = iter([
        {"started": True, "playing": True, "title": "Pray for Rain", "duration": 240, "position": 10},
        {"started": True, "playing": True, "title": "Pray for Rain", "duration": 240, "position": 120},
        {"started": True, "playing": True, "title": "Kristi Don't Care", "duration": 200, "position": 1},
    ])
    monkeypatch.setattr(browser, "_media_state", lambda page: next(states))
    browser._poll(None)
    browser._poll(None)
    assert [e[0] for e in events] == ["started"]
    browser._poll(None)
    assert events[-1] == ("ended", 3, "")


def test_quick_clicks_credit_fullscreen_only_to_the_click_that_caused_it(monkeypatch) -> None:
    from stage.browser import StageBrowser

    browser = StageBrowser(profile_dir=Path("unused"), on_event=lambda *e: None)
    browser._teach = {"service": "spotify", "host": "open.spotify.com", "steps": [], "labels": [], "pending": [
        {"type": "click", "selectors": ["button:has-text('Show more')"], "label": "Show more",
         "wasPlaying": True, "wasFullscreen": False, "at": 0},
        {"type": "click", "selectors": ["button[aria-label='Enter full screen']"], "label": "Enter full screen",
         "wasPlaying": True, "wasFullscreen": False, "at": 0},
    ]}
    monkeypatch.setattr(browser, "_media_state", lambda page: {"playing": True, "fullscreen": True})
    browser._settle_teach_events(page=None, force=True)
    show_more, enter_fullscreen = browser._teach["steps"]
    assert "unless" not in show_more
    assert enter_fullscreen["unless"] == "fullscreen"


def test_admin_lists_taught_services(app, client, stage, tmp_path, monkeypatch) -> None:
    overrides = tmp_path / "stage_selectors.json"
    monkeypatch.setattr(plans, "overrides_path", lambda: overrides)
    page = client.get(f"/admin?token={_token(app)}")
    assert b"No services taught yet" in page.data
    save_taught_steps("spotify", [{"wait_playing": 6000}, {"click": ["x"]}], overrides=overrides)
    page = client.get(f"/admin?token={_token(app)}")
    assert b"Spotify: 2 steps" in page.data


def test_apple_song_page_link_opens_album_with_track_highlighted() -> None:
    from stage.plans import apple_album_link

    page = '<a href="https://music.apple.com/us/album/winning-streak/1772965592?i=1772965597">x</a>'
    song = "https://music.apple.com/us/song/winning-streak/1772965597"
    assert apple_album_link(song, fetch=lambda url: page) == "https://music.apple.com/us/album/winning-streak/1772965592?i=1772965597"
    album = "https://music.apple.com/us/album/pray-for-rain/305517559?i=305517585"
    assert apple_album_link(album, fetch=lambda url: 1 / 0) == album  # album links are left alone

    def offline(url):
        raise OSError("no network")

    other = "https://music.apple.com/us/song/other/999"
    assert apple_album_link(other, fetch=offline) == other  # falls back to the saved link


def test_host_clicking_during_a_song_takes_over_from_the_automation(monkeypatch) -> None:
    import time as _time

    from stage.browser import StageBrowser

    events: list[tuple] = []
    browser = StageBrowser(profile_dir=Path("unused"), on_event=lambda *e: events.append(e))
    browser._watch = {"play_id": 5, "service": "apple_music", "spec": {}, "deadline": 0,
                      "started": True, "attention": False, "title": "Winning Streak", "manual": False}

    browser._last_automation = _time.monotonic()
    browser._on_record({}, {"type": "click"})  # the app's own click: ignored
    assert browser._watch["manual"] is False and events == []

    browser._last_automation = _time.monotonic() - 10
    browser._on_record({}, {"type": "click"})  # the host's click
    assert browser._watch["manual"] is True and browser._watch["title"] == ""
    assert events[0][0] == "manual"
    assert browser._run_steps(page=None, spec={"steps": [{"click": ["x"]}]}) == ""  # remaining steps skipped


def test_manual_mode_switch_is_passed_to_the_stage(app, client, stage) -> None:
    item_id, _ = _queue(app, "Alice")
    response = client.post(
        "/admin/stage",
        data={"csrf_token": _csrf(client), "action": "toggle_auto_steps"},
        headers={"X-Admin-Token": _token(app)},
    )
    assert response.get_json()["stage"]["auto_steps"] is False
    stage.start_item(item_id)
    assert stage.driver.automate is False


def test_settings_page_reports_intermission_music(app, client, stage, tmp_path) -> None:
    token = _token(app)
    assert b"No intermission folder set" in client.get(f"/settings?token={token}").data
    folder = tmp_path / "Break Music"
    folder.mkdir()
    (folder / "a.mp3").write_bytes(b"x")
    (folder / "b.m4a").write_bytes(b"x")
    with app.runtime_state.db.session_scope() as db:
        set_setting(db, "intermission_folder", str(folder))
    assert b"2 songs found" in client.get(f"/settings?token={token}").data
