"""Install check for the stage screen: ``KaraokeTicker.exe --self-test [report.json]``.

Checks that Playwright's driver and the stage scripts are bundled, that Edge is installed,
and that a stage window really opens, runs the injected scripts, and closes. Uses a
throwaway browser profile, so sign-ins and the database are never touched. Writes a JSON
report (a windowed .exe has no console) and returns 0 when everything passed.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path


def run(report_path: str | None = None) -> int:
    report: dict[str, object] = {"frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    checks: dict[str, object] = report["checks"]  # type: ignore[assignment]

    try:
        from playwright._impl._driver import compute_driver_executable

        driver, entrypoint = compute_driver_executable()
        checks["playwright_driver"] = Path(driver).exists() and Path(entrypoint).exists()
    except Exception as exc:
        checks["playwright_driver"] = f"error: {exc}"

    from . import browser as stage_browser
    from .plans import load_selectors

    checks["stage_scripts"] = stage_browser.MEDIA_WATCH_JS.exists() and stage_browser.RECORDER_JS.exists()
    try:
        checks["selectors"] = sorted(load_selectors())
    except Exception as exc:
        checks["selectors"] = f"error: {exc}"
    edge = stage_browser.find_browser("msedge")
    checks["edge"] = edge or False

    window: dict[str, object] = {}
    if edge and checks["playwright_driver"] is True:
        profile = Path(tempfile.mkdtemp(prefix="kt-selftest-"))
        closed = threading.Event()
        events: list[str] = []

        def on_event(kind: str, _play_id: int, detail: str) -> None:
            events.append(f"{kind}: {detail}")
            if kind == "closed":
                closed.set()

        class Probe(stage_browser.StageBrowser):
            def probe(self):
                return self._call("probe", (), 30)

            def _loop(self, page):
                original = self._commands.get_nowait

                def get_nowait():
                    command = original()
                    if command[0] == "probe":
                        page.goto("data:text/html,<title>Karaoke Ticker self-test</title>")
                        command[2].set_result(
                            {
                                "media_watch": page.evaluate("() => typeof window.__ktState === 'function'"),
                                "recorder": page.evaluate("() => Boolean(window.__ktRecorderInstalled)"),
                            }
                        )
                        return ("", (), None)
                    return command

                self._commands.get_nowait = get_nowait
                super()._loop(page)

        probe = Probe(profile_dir=profile, on_event=on_event)
        try:
            probe.start(monitor_rect=None, fullscreen=False, extra_args=["--mute-audio", "--window-size=640,400"])
            time.sleep(2)
            window = probe.probe()
        except Exception as exc:
            window = {"error": str(exc)}
        finally:
            probe.close(wait_seconds=20)
            closed.wait(20)
            shutil.rmtree(profile, ignore_errors=True)
        window["events"] = events
    checks["stage_window"] = window

    passed = (
        checks["playwright_driver"] is True
        and checks["stage_scripts"] is True
        and isinstance(checks["selectors"], list)
        and bool(checks["edge"])
        and window.get("media_watch") is True
        and window.get("recorder") is True
    )
    report["passed"] = passed
    text = json.dumps(report, indent=2)
    target = Path(report_path) if report_path else Path(tempfile.gettempdir()) / "karaoke-ticker-selftest.json"
    target.write_text(text, encoding="utf-8")
    if sys.stdout is not None:
        try:
            print(text)
        except Exception:
            pass
    return 0 if passed else 1
