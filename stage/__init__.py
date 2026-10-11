"""Stage automation: dedicated browser, intermission screen, and singer-ready triggers."""

from __future__ import annotations

from pathlib import Path

from config import DATA_DIR

from .browser import StageBrowser
from .controller import StageController
from .hotkey import ReadyHotkey
from .monitors import monitor_rect


def create_stage_controller(db, *, emit, emit_queue) -> StageController:
    """Build the controller wired to a real Edge window and global hotkey."""
    profile_dir = Path(DATA_DIR) / "stage-profile"
    return StageController(
        db,
        emit=emit,
        emit_queue=emit_queue,
        driver_factory=lambda on_event: StageBrowser(profile_dir=profile_dir, on_event=on_event),
        monitor_rect=monitor_rect,
        hotkeys=ReadyHotkey(),
    )
