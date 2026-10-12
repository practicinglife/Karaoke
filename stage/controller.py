"""Stage controller: drives the stage browser from the queue.

States
------
IDLE          stage browser not running
INTERMISSION  intermission screen up; waiting for the next singer to press "ready"
STARTING      song page loading / service steps running
PLAYING       song confirmed playing; waiting for it to end
TEACHING      host is clicking through a song page while the app records the steps

Song end (or admin NEXT) -> mark complete -> INTERMISSION. A ready press from the
next singer's phone, the mic-stand button, the network button, or the host starts
the song at the top of the queue.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Protocol

from karaoke.models import QueueItem
from karaoke.queue_manager import COMPLETED, QueueManager
from karaoke.services import active_session, get_setting, set_setting

from .plans import forget_taught_steps, normalize_stage_url, save_taught_steps, stage_service_for

logger = logging.getLogger(__name__)

IDLE = "IDLE"
INTERMISSION = "INTERMISSION"
STARTING = "STARTING"
PLAYING = "PLAYING"
TEACHING = "TEACHING"

EXPIRY_ACTIONS = {"wait", "start", "bump"}
READY_DEBOUNCE_SECONDS = 3.0


class StageDriver(Protocol):
    is_running: bool

    def start(self, *, monitor_rect=None, fullscreen: bool = True, extra_args=None) -> None: ...
    def place(self, monitor_rect, fullscreen: bool) -> None: ...
    def teach_start(self, service: str, url: str, monitor_rect) -> None: ...
    def teach_status(self) -> list[str]: ...
    def teach_stop(self, timeout: float = 20.0) -> list[dict[str, Any]]: ...
    def show(self, url: str) -> None: ...
    def play(self, play_id: int, service: str, url: str) -> None: ...
    def close(self, wait_seconds: float = 0.0) -> None: ...
    def test_selectors(self, timeout: float = 20.0) -> dict[str, Any]: ...


class StageController:
    def __init__(
        self,
        db,
        *,
        emit: Callable[[str, dict[str, Any]], None],
        emit_queue: Callable[[], None],
        driver_factory: Callable[[Callable[[str, int, str], None]], StageDriver],
        monitor_rect: Callable[[int], tuple[int, int, int, int] | None] = lambda _monitor: None,
        hotkeys=None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.emit = emit
        self.emit_queue = emit_queue
        self.monitor_rect = monitor_rect
        self.extra_args: list[str] = []
        self.hotkeys = hotkeys
        self.clock = clock
        self.driver = driver_factory(self.handle_driver_event)
        self.base_url = ""
        self.state = IDLE
        self.message = ""
        self.play_id = 0
        self.countdown_ends_at: float | None = None
        self.teach_service = ""
        self._last_start = 0.0
        self._lock = threading.RLock()
        self._ticker_stop = threading.Event()
        self._ticker: threading.Thread | None = None

    # ----- lifecycle ---------------------------------------------------------------

    def set_base_url(self, url: str) -> None:
        if url:
            self.base_url = url.rstrip("/")

    def open(self) -> None:
        """Launch the stage browser (if needed) and show the intermission screen."""
        with self._lock:
            if not self.driver.is_running:
                with self.db.session_scope() as db:
                    monitor = int(get_setting(db, "stage_monitor") or "2")
                    fullscreen = get_setting(db, "stage_fullscreen") != "0"
                    hotkey = get_setting(db, "ready_hotkey").strip()
                self.driver.start(
                    monitor_rect=self.monitor_rect(monitor), fullscreen=fullscreen, extra_args=self.extra_args
                )
                if self.hotkeys and hotkey:
                    self.hotkeys.register(hotkey, lambda: self.singer_ready("button"))
                self._start_ticker()
            if self.state in (IDLE, INTERMISSION):
                self._enter_intermission()
        self._publish()

    def move_to_monitor(self, monitor: int) -> None:
        """Save the stage monitor and move an open stage window there (fullscreen per settings)."""
        with self.db.session_scope() as db:
            set_setting(db, "stage_monitor", str(monitor))
            fullscreen = get_setting(db, "stage_fullscreen") != "0"
        if self.driver.is_running:
            self.driver.place(self.monitor_rect(monitor), fullscreen)

    def close(self, wait_seconds: float = 0.0) -> None:
        with self._lock:
            self.driver.close()
            if self.hotkeys:
                self.hotkeys.unregister()
            self._ticker_stop.set()
            self.state = IDLE
            self.countdown_ends_at = None
        if wait_seconds:
            # Wait outside the lock: the browser thread takes it to report "closed".
            self.driver.close(wait_seconds)
        self._publish()

    # ----- actions -----------------------------------------------------------------

    def start_item(self, item_id: int) -> tuple[bool, str]:
        """Start a specific queue item now (host PLAY or a ready press)."""
        with self._lock:
            with self.db.session_scope() as db:
                record = active_session(db)
                if not record:
                    return False, "No active session."
                qm = QueueManager(db)
                item = db.get(QueueItem, item_id)
                if not item or not item.song:
                    return False, "Queue item not found."
                plan = self._plan(db, record.admin_token, item.song)
                if not plan:
                    return False, "This song can't be played on the stage screen."
                qm.mark_now_playing(item_id)
            if not self.driver.is_running:
                self.open()
            self.play_id += 1
            self.state = STARTING
            self.message = ""
            self.countdown_ends_at = None
            self._last_start = self.clock()
            self.driver.play(self.play_id, *plan)
        self.emit_queue()
        self._publish()
        return True, ""

    def singer_ready(self, source: str, user_id: int | None = None) -> tuple[bool, str]:
        """A ready press. Phone presses must come from the singer who is up next."""
        with self._lock:
            if self.state != INTERMISSION:
                return False, "Not waiting for a singer right now."
            if self.clock() - self._last_start < READY_DEBOUNCE_SECONDS:
                return False, "Already starting."
            head = self._head_item()
            if not head:
                return False, "Nobody is in the queue."
            if user_id is not None and head["user_id"] != user_id:
                return False, "It's not your turn yet."
            logger.info("Singer ready via %s for queue item %s", source, head["item_id"])
            return self.start_item(head["item_id"])

    def song_finished(self, play_id: int | None = None) -> None:
        """Current song ended (browser event) or host pressed NEXT."""
        with self._lock:
            if play_id is not None and play_id != self.play_id:
                return
            with self.db.session_scope() as db:
                record = active_session(db)
                if record:
                    current = QueueManager(db).now_playing(record.id)
                    if current:
                        current.status = COMPLETED
            self._enter_intermission()
        self.emit_queue()
        self._publish()

    # ----- teach mode --------------------------------------------------------------

    def teach_start(self, service: str, url: str) -> None:
        """Open a song page windowed on the main screen and record the host's clicks."""
        with self._lock:
            if not self.driver.is_running:
                self.open()
            self.play_id += 1  # ignore events from any song that was playing
            self.state = TEACHING
            self.teach_service = service
            self.message = ""
            self.countdown_ends_at = None
            self.driver.teach_start(service, normalize_stage_url(service, url), self.monitor_rect(1))
        self._publish()

    def teach_finish(self, save: bool) -> list[dict[str, Any]]:
        """Stop recording; optionally save the steps. Returns to the stage screen either way."""
        with self._lock:
            if self.state != TEACHING:
                return []
            steps = self.driver.teach_stop()
            if save and steps:
                save_taught_steps(self.teach_service, steps)
                logger.info("Saved %s taught steps for %s", len(steps), self.teach_service)
            self.teach_service = ""
            with self.db.session_scope() as db:
                monitor = int(get_setting(db, "stage_monitor") or "2")
                fullscreen = get_setting(db, "stage_fullscreen") != "0"
            self.driver.place(self.monitor_rect(monitor), fullscreen)
            self._enter_intermission()
        self._publish()
        return steps

    def teach_reset(self, service: str) -> None:
        """Forget taught steps for a service and use the built-in ones again."""
        forget_taught_steps(service)

    def test_selectors(self) -> dict[str, Any]:
        if not self.driver.is_running:
            return {"error": "Stage browser is not open."}
        return self.driver.test_selectors()

    # ----- browser events ----------------------------------------------------------

    def handle_driver_event(self, kind: str, play_id: int, detail: str) -> None:
        if kind == "closed":
            with self._lock:
                self.state = IDLE
                self.message = detail
                self.countdown_ends_at = None
                self._ticker_stop.set()
                if self.hotkeys:
                    self.hotkeys.unregister()
            self._publish()
            return
        if play_id != self.play_id:
            return  # stale event from an earlier song
        if kind == "ended":
            self.song_finished(play_id)
            return
        with self._lock:
            if kind == "started":
                self.state = PLAYING
                self.message = ""
            elif kind == "attention":
                self.message = detail
        self._publish()

    # ----- countdown ---------------------------------------------------------------

    def tick(self) -> None:
        """Handle countdown start/expiry; runs every half second while the stage is open."""
        with self._lock:
            if self.state != INTERMISSION:
                return
            head = self._head_item()
            now = self.clock()
            if not head:
                if self.countdown_ends_at is not None:
                    self.countdown_ends_at = None
                    self._publish()
                return
            if self.countdown_ends_at is None:
                self.countdown_ends_at = now + self._countdown_seconds()
                self._publish()
                return
            if now < self.countdown_ends_at:
                return
            action = self._expiry_action()
            if action == "start":
                self.start_item(head["item_id"])
            elif action == "bump":
                with self.db.session_scope() as db:
                    record = active_session(db)
                    rotation = get_setting(db, "singer_rotation_on") == "1"
                    waiting = QueueManager(db).ordered_up_next(record.id, rotation) if record else []
                    if len(waiting) > 1:
                        QueueManager(db).move_item(head["item_id"], "down", rotation)
                self.countdown_ends_at = now + self._countdown_seconds()
                self.emit_queue()
                self._publish()

    def _start_ticker(self) -> None:
        if self._ticker and self._ticker.is_alive():
            return
        self._ticker_stop = threading.Event()

        def run() -> None:
            while not self._ticker_stop.wait(0.5):
                try:
                    self.tick()
                except Exception:
                    logger.exception("Stage countdown tick failed")

        self._ticker = threading.Thread(target=run, daemon=True, name="stage-ticker")
        self._ticker.start()

    # ----- state / payload ---------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            head = self._head_item() if self.state == INTERMISSION else None
            ends = self.countdown_ends_at
            now = self._now_item() if self.state in (STARTING, PLAYING) else None
            return {
                "state": self.state,
                "message": self.message,
                "now": now,
                "browser_running": self.driver.is_running,
                "next": {k: v for k, v in head.items() if k != "user_id"} if head else None,
                "countdown_ends_at": int(ends * 1000) if ends else None,
                "countdown_expired": bool(ends and self.clock() >= ends),
                "expiry_action": self._expiry_action(),
                "teach": {"service": self.teach_service, "steps": self.driver.teach_status()}
                if self.state == TEACHING
                else None,
            }

    def _publish(self) -> None:
        try:
            self.emit("stage_state", self.snapshot())
        except Exception:
            logger.exception("Failed to emit stage state")

    def _enter_intermission(self) -> None:
        self.state = INTERMISSION
        self.message = ""
        self.countdown_ends_at = None
        url = self._intermission_url()
        if url and self.driver.is_running:
            self.driver.show(url)

    def _head_item(self) -> dict[str, Any] | None:
        with self.db.session_scope() as db:
            record = active_session(db)
            if not record:
                return None
            rotation = get_setting(db, "singer_rotation_on") == "1"
            waiting = QueueManager(db).ordered_up_next(record.id, rotation)
            if not waiting:
                return None
            item = waiting[0]
            return {
                "item_id": item.id,
                "user_id": item.user_id,
                "user": item.user.display_name if item.user else "",
                "song": item.song.title if item.song else "",
                "artist": item.song.artist if item.song else "",
            }

    def _now_item(self) -> dict[str, Any] | None:
        with self.db.session_scope() as db:
            record = active_session(db)
            item = QueueManager(db).now_playing(record.id) if record else None
            if not item:
                return None
            return {
                "user": item.user.display_name if item.user else "",
                "song": item.song.title if item.song else "",
                "artist": item.song.artist if item.song else "",
            }

    def _intermission_url(self) -> str:
        with self.db.session_scope() as db:
            record = active_session(db)
            token = record.admin_token if record else ""
        return f"{self._base()}/stage?token={token}"

    def _plan(self, db, admin_token: str, song) -> tuple[str, str] | None:
        service = stage_service_for(song.service, song.url)
        if service is None:
            return None
        if service == "traditional":
            if not song.karaoke_library_id:
                return None
            url = f"{self._base()}/player?token={admin_token}&song_id={song.karaoke_library_id}&autoplay=1"
            return service, url
        return service, normalize_stage_url(service, song.url)

    def _base(self) -> str:
        if self.base_url:
            return self.base_url
        with self.db.session_scope() as db:
            port = get_setting(db, "web_server_port") or "8080"
        return f"http://127.0.0.1:{port}"

    def _countdown_seconds(self) -> int:
        with self.db.session_scope() as db:
            raw = get_setting(db, "countdown_seconds")
        return int(raw) if raw.isdigit() else 60

    def _expiry_action(self) -> str:
        with self.db.session_scope() as db:
            action = get_setting(db, "countdown_expiry_action")
        return action if action in EXPIRY_ACTIONS else "wait"

