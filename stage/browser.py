"""Dedicated, app-controlled stage browser.

Edge is started as a normal browser process with a DevTools port, and Playwright
attaches to it over CDP. (When Playwright launches the browser itself, a page's
fullscreen request - e.g. YouTube's fullscreen button - never takes effect, and
Google sign-in refuses automation-launched browsers.)

All Playwright calls happen on one worker thread; other threads talk to it through a
command queue. Events are reported back through ``on_event(kind, play_id, detail)``:
``started``, ``ended``, ``attention`` (song didn't start / a required button was
missing) and ``closed`` (the window was closed or failed to launch).

Teach mode records the host's clicks and key presses on a song page and turns them
into steps for that service.
"""

from __future__ import annotations

import atexit
import logging
import os
import queue
import socket
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .plans import load_selectors

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
MEDIA_WATCH_JS = HERE / "media_watch.js"
RECORDER_JS = HERE / "recorder.js"
START_TIMEOUT_SECONDS = 25.0
POLL_SECONDS = 1.0
PUMP_MS = 200
TEACH_SETTLE_SECONDS = 1.5

EventCallback = Callable[[str, int, str], None]

BROWSER_PATHS = {
    "msedge": [r"Microsoft\Edge\Application\msedge.exe"],
    "chrome": [r"Google\Chrome\Application\chrome.exe"],
}


def find_browser(channel: str) -> str | None:
    """Locate an installed Edge/Chrome executable."""
    roots = [os.environ.get(name, "") for name in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for relative in BROWSER_PATHS.get(channel, []):
        for root in roots:
            candidate = Path(root) / relative
            if root and candidate.exists():
                return str(candidate)
    return None


def close_leftover_windows(profile_dir: Path) -> None:
    """Stop Edge processes still holding the stage profile (e.g. after an app crash).

    A second Edge started on the same profile hands off to the old one and exits,
    which would leave the app unable to connect. Only processes launched with this
    exact --user-data-dir are touched, never the user's normal browser.
    """
    if os.name != "nt":
        return
    profile = str(Path(profile_dir).resolve()).replace("'", "''")
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' OR Name='chrome.exe'\" | "
        f"Where-Object {{ $_.CommandLine -like '*--user-data-dir=*{profile}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        logger.exception("Could not check for leftover stage windows")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StageBrowser:
    """Owns one browser window with one reused tab."""

    def __init__(
        self,
        *,
        profile_dir: Path,
        on_event: EventCallback,
        channel: str = "msedge",
        selectors_path: Path | None = None,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.on_event = on_event
        self.channel = channel
        self.selectors_path = selectors_path
        self._commands: queue.Queue[tuple[str, tuple, Future | None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._watch: dict[str, Any] | None = None
        self._teach: dict[str, Any] | None = None
        self._window_bounds: dict[str, Any] = {}

    # ----- public API (any thread) -------------------------------------------------

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(
        self,
        *,
        monitor_rect: tuple[int, int, int, int] | None = None,
        fullscreen: bool = True,
        extra_args: list[str] | None = None,
    ) -> None:
        if self.is_running:
            return
        self._commands = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, args=(list(extra_args or []),), daemon=True, name="stage-browser"
        )
        self._thread.start()
        self.place(monitor_rect, fullscreen)

    def place(self, monitor_rect: tuple[int, int, int, int] | None, fullscreen: bool) -> None:
        """Move the window onto a monitor (left, top, width, height): fullscreen or maximized."""
        self._commands.put(("place", (monitor_rect, fullscreen), None))

    def show(self, url: str) -> None:
        """Load a page with no song tracking (intermission screen, sign-in page)."""
        self._commands.put(("show", (url,), None))

    def play(self, play_id: int, service: str, url: str) -> None:
        """Load a song page, run that service's steps, then watch for the song to end."""
        self._commands.put(("play", (play_id, service, url), None))

    def test_selectors(self, timeout: float = 20.0) -> dict[str, Any]:
        """Report which selectors match on the page currently shown."""
        return self._call("test", (), timeout)

    def teach_start(self, service: str, url: str, monitor_rect: tuple[int, int, int, int] | None) -> None:
        """Open a song page in a normal window and start recording the host's clicks."""
        self._commands.put(("teach_start", (service, url, monitor_rect), None))

    def teach_status(self) -> list[str]:
        teach = self._teach
        return list(teach["labels"]) if teach else []

    def teach_stop(self, timeout: float = 20.0) -> list[dict[str, Any]]:
        """Stop recording and return the recorded steps."""
        return self._call("teach_stop", (), timeout)

    def close(self) -> None:
        if self.is_running:
            self._commands.put(("close", (), None))

    def _call(self, command: str, args: tuple, timeout: float):
        future: Future = Future()
        self._commands.put((command, args, future))
        return future.result(timeout=timeout)

    # ----- worker thread -----------------------------------------------------------

    def _run(self, extra_args: list[str]) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Stage browser needs Playwright: pip install playwright")
            self.on_event("closed", 0, "Playwright is not installed.")
            return
        executable = find_browser(self.channel)
        if not executable:
            self.on_event("closed", 0, "Microsoft Edge was not found.")
            return

        port = _free_port()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        close_leftover_windows(self.profile_dir)
        subprocess.Popen(
            [
                executable,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={self.profile_dir}",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
                "--hide-crash-restore-bubble",
                "--disable-features=Translate",
                *extra_args,
                "about:blank",
            ]
        )
        # The launcher process exits straight away and hands off to the real browser,
        # so cleanup goes through DevTools (or the profile-matched process sweep).
        atexit.register(close_leftover_windows, self.profile_dir)
        message = "Stage browser closed."
        browser = None
        try:
            with sync_playwright() as pw:
                browser = self._connect(pw, port)
                if browser is None:
                    message = "Couldn't connect to the stage browser. Close any other stage windows and try again."
                    return
                context = browser.contexts[0]
                context.add_init_script(path=str(MEDIA_WATCH_JS))
                context.add_init_script(path=str(RECORDER_JS))
                context.expose_binding("__ktRecord", self._on_record)
                page = context.pages[0] if context.pages else context.new_page()
                self._loop(page)
                try:
                    browser.new_browser_cdp_session().send("Browser.close")
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Stage browser stopped")
            message = f"Stage browser stopped: {exc}"
        finally:
            self._watch = None
            self._teach = None
            if browser is None or message != "Stage browser closed.":
                close_leftover_windows(self.profile_dir)
            self.on_event("closed", 0, message)

    def _connect(self, pw, port: int):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                return pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            except Exception:
                time.sleep(0.5)
        return None

    def _loop(self, page) -> None:
        last_poll = 0.0
        while not page.is_closed():
            try:
                command, args, future = self._commands.get_nowait()
            except queue.Empty:
                command, args, future = "", (), None
                page.wait_for_timeout(PUMP_MS)  # lets Playwright deliver page events/bindings
            try:
                if command == "close":
                    return
                if command == "show":
                    self._watch = None
                    self._goto(page, args[0])
                elif command == "play":
                    self._teach = None
                    self._start_play(page, *args)
                elif command == "place":
                    self._place(page, *args)
                elif command == "test":
                    future.set_result(self._test_selectors(page))  # type: ignore[union-attr]
                elif command == "teach_start":
                    self._teach_start(page, *args)
                elif command == "teach_stop":
                    future.set_result(self._teach_stop(page))  # type: ignore[union-attr]
                if self._teach:
                    self._settle_teach_events(page)
                if self._watch and time.monotonic() - last_poll >= POLL_SECONDS:
                    last_poll = time.monotonic()
                    self._poll(page)
            except Exception as exc:
                if page.is_closed():
                    return
                logger.exception("Stage browser command %r failed", command)
                if future and not future.done():
                    future.set_exception(exc)
                if command == "play":
                    self.on_event("attention", args[0], f"Could not load the song page: {exc}")

    def _place(self, page, monitor_rect, fullscreen: bool) -> None:
        """Position the window with the DevTools window API.

        A normal-sized window is put just inside the target monitor, then made
        fullscreen (or maximized), which fills whichever monitor holds the window, so
        display scaling doesn't throw the position off.
        """
        cdp = page.context.new_cdp_session(page)
        try:
            window_id = cdp.send("Browser.getWindowForTarget")["windowId"]

            def bounds(**values) -> None:
                cdp.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": values})

            bounds(windowState="normal")
            if monitor_rect:
                left, top, width, height = monitor_rect
                bounds(left=left + 40, top=top + 40, width=max(640, width - 80), height=max(480, height - 80))
            bounds(windowState="fullscreen" if fullscreen else "maximized")
            self._window_bounds = cdp.send("Browser.getWindowBounds", {"windowId": window_id})["bounds"]
            logger.info("Stage window placed: %s", self._window_bounds)
        finally:
            cdp.detach()
        if self._watch:
            # Changing the window state drops the player's fullscreen; redo those steps.
            page.wait_for_timeout(500)
            steps = [step for step in self._watch["spec"].get("steps", []) if step.get("unless")]
            self._run_steps(page, {"steps": steps})

    def _goto(self, page, url: str) -> None:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # ----- playing songs -----------------------------------------------------------

    def _start_play(self, page, play_id: int, service: str, url: str) -> None:
        spec = load_selectors(self.selectors_path).get(service, {})
        self._watch = {
            "play_id": play_id,
            "spec": spec,
            "deadline": time.monotonic() + START_TIMEOUT_SECONDS,
            "started": False,
            "attention": False,
        }
        self._goto(page, url)
        page.evaluate(
            "selectors => { window.__ktBusySelectors = selectors; }",
            [sel for sel in spec.get("busy", []) if not sel.startswith("role=")],
        )
        missing = self._run_steps(page, spec)
        if missing and self._watch:
            self._watch["attention"] = True
            self.on_event("attention", play_id, f"Button not found: {missing}")

    def _run_steps(self, page, spec: dict[str, Any]) -> str:
        """Run the service's steps; returns the first required selector list that was missing."""
        for step in spec.get("steps", []):
            if not self._commands.empty():
                return ""  # superseded by a newer command
            # Fullscreen buttons/keys toggle, so never press them when already fullscreen.
            if step.get("unless"):
                if self._is_fullscreen(page, step["unless"]):
                    continue
                # Players ignore (or half-apply) fullscreen until the song is really
                # playing, so wait for playback and let the player settle first.
                self._wait_playing(page, 10)
                page.wait_for_timeout(1000)
                if self._is_fullscreen(page, step["unless"]):
                    continue
            if "wait_playing" in step:
                self._wait_playing(page, step["wait_playing"] / 1000)
            elif "wait" in step:
                page.wait_for_timeout(step["wait"])
            elif "click" in step:
                if step.get("when") == "paused" and self._media_state(page).get("playing"):
                    continue
                if not self._click_first(page, step["click"], step.get("timeout", 5000) / 1000):
                    if not step.get("optional"):
                        return ", ".join(step["click"])
            elif "press" in step:
                if step.get("when") == "paused" and self._media_state(page).get("playing"):
                    continue
                target = self._first_visible(page, step.get("focus") or [])
                if target is not None:
                    target.focus()
                page.keyboard.press(step["press"])
            if step.get("unless"):
                # Sites apply fullscreen asynchronously; wait so a following fallback
                # toggle doesn't see "not yet fullscreen" and switch it straight back off.
                end = time.monotonic() + 2.0
                while time.monotonic() < end and not self._is_fullscreen(page, step["unless"]):
                    page.wait_for_timeout(200)
        return ""

    def _poll(self, page) -> None:
        watch = self._watch
        if not watch:
            return
        spec = watch["spec"]
        for selector in spec.get("watch_clicks", []):
            target = self._first_visible(page, [selector])
            if target is not None:
                try:
                    target.click(timeout=2000)
                except Exception:
                    pass
        state = self._media_state(page)
        busy = self._first_visible(page, spec.get("busy", [])) is not None
        if state.get("started") and not watch["started"]:
            watch["started"] = True
            self.on_event("started", watch["play_id"], "")
        if not watch["started"] and not watch["attention"] and time.monotonic() > watch["deadline"]:
            watch["attention"] = True
            self.on_event("attention", watch["play_id"], "Song did not start. Press play in the stage window.")
        duration = float(state.get("duration") or 0)
        near_end = duration > 5 and float(state.get("position") or 0) >= duration - 0.75 and not state.get("playing")
        if watch["started"] and not busy and (state.get("ended") or near_end):
            self._watch = None
            self.on_event("ended", watch["play_id"], "")

    # ----- teach mode --------------------------------------------------------------

    def _teach_start(self, page, service: str, url: str, monitor_rect) -> None:
        self._watch = None
        self._teach = {
            "service": service,
            "host": (urlparse(url).hostname or "").lower(),
            "pending": [],
            "steps": [],
            "labels": [],
        }
        self._place(page, monitor_rect, False)
        self._goto(page, url)

    def _on_record(self, source: dict[str, Any], payload: dict[str, Any]) -> None:
        teach = self._teach
        if not teach or not isinstance(payload, dict):
            return
        frame = source.get("frame")
        host = (urlparse(frame.url).hostname or "").lower() if frame is not None else ""
        if teach["host"] and host and host != teach["host"]:
            return  # e.g. a sign-in popup on another site
        payload["at"] = time.monotonic()
        teach["pending"].append(payload)

    def _settle_teach_events(self, page, force: bool = False) -> None:
        """Turn recorded events into steps once their effect (playing/fullscreen) is visible."""
        teach = self._teach
        if not teach:
            return
        while teach["pending"] and (force or time.monotonic() - teach["pending"][0]["at"] >= TEACH_SETTLE_SECONDS):
            event = teach["pending"].pop(0)
            state = self._media_state(page)
            if event.get("type") == "click" and event.get("selectors"):
                step: dict[str, Any] = {"click": event["selectors"], "optional": True, "timeout": 8000}
                label = f"Click '{event.get('label', '')}'"
            elif event.get("type") == "press" and event.get("key"):
                step = {"press": event["key"], "optional": True}
                if event.get("focus"):
                    step["focus"] = event["focus"]
                label = f"Press {event['key']}"
            else:
                continue
            if not event.get("wasPlaying") and state.get("playing"):
                step["when"] = "paused"
                label += " (starts playback)"
            if not event.get("wasFullscreen") and state.get("fullscreen"):
                step["unless"] = "fullscreen"
                label += " (fullscreen)"
            teach["steps"].append(step)
            teach["labels"].append(label)

    def _teach_stop(self, page) -> list[dict[str, Any]]:
        if not self._teach:
            return []
        self._settle_teach_events(page, force=True)
        steps = self._teach["steps"]
        self._teach = None
        # Give autoplaying pages a moment before the first recorded click.
        return [{"wait_playing": 6000}, *steps] if steps else []

    # ----- helpers -----------------------------------------------------------------

    def _media_state(self, page) -> dict[str, Any]:
        try:
            return page.evaluate("() => window.__ktState ? window.__ktState() : null") or {}
        except Exception:
            return {}

    def _is_fullscreen(self, page, check: str) -> bool:
        """'fullscreen' = the page's player is fullscreen; otherwise a CSS selector."""
        if check == "fullscreen":
            return bool(self._media_state(page).get("fullscreen"))
        try:
            return page.locator(check).count() > 0
        except Exception:
            return False

    def _wait_playing(self, page, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._media_state(page).get("playing"):
                return True
            page.wait_for_timeout(250)
        return False

    def _first_visible(self, page, selectors: list[str]):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    def _click_first(self, page, selectors: list[str], seconds: float) -> bool:
        end = time.monotonic() + seconds
        while True:
            target = self._first_visible(page, selectors)
            if target is not None:
                try:
                    target.click(timeout=3000)
                    return True
                except Exception:
                    pass
            if time.monotonic() >= end:
                return False
            page.wait_for_timeout(250)

    def _test_selectors(self, page) -> dict[str, Any]:
        host = (urlparse(page.url).hostname or "").lower()
        specs = load_selectors(self.selectors_path)
        name = next((key for key, spec in specs.items() if host in spec.get("hosts", [])), "")
        if not name and self._watch:
            name = next((key for key, spec in specs.items() if spec == self._watch["spec"]), "")
        report: dict[str, Any] = {"url": page.url, "service": name or None, "selectors": []}
        spec = specs.get(name, {})
        groups = [("busy", spec.get("busy", [])), ("watch_clicks", spec.get("watch_clicks", []))]
        for index, step in enumerate(spec.get("steps", []), start=1):
            if "click" in step:
                groups.append((f"step {index} click", step["click"]))
            elif step.get("focus"):
                groups.append((f"step {index} focus", step["focus"]))
            if step.get("unless") and step["unless"] != "fullscreen":
                groups.append((f"step {index} already-fullscreen check", [step["unless"]]))
        for group, selectors in groups:
            for selector in selectors:
                try:
                    count = page.locator(selector).count()
                    visible = count > 0 and page.locator(selector).first.is_visible()
                except Exception as exc:
                    count, visible = -1, False
                    logger.info("Selector %r failed: %s", selector, exc)
                report["selectors"].append({"group": group, "selector": selector, "count": count, "visible": visible})
        report["media"] = self._media_state(page)
        report["window"] = self._window_bounds
        return report
