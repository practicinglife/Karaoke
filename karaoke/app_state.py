"""Shared runtime state container."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from .database import DatabaseManager


@dataclass
class RuntimeState:
    """Runtime state shared by GUI and Flask app."""

    db: DatabaseManager
    lock: Lock = field(default_factory=Lock)
    server_running: bool = False
    current_house_code: str = ""
    current_session_id: int | None = None
    admin_token: str = ""
    guest_url: str = ""
    qr_path: str = ""
    kiosk_qr_path: str = ""
    ticker_qr_path: str = ""
    # Background indexer instance (set at runtime); typed as object to avoid import cycles
    indexer: object | None = None
    index_status: str = "Idle"
    index_compare_summary: str = "No snapshot yet"
    index_last_run: str = "Never"
    index_progress: float = 0.0
    index_progress_text: str = "Idle"

