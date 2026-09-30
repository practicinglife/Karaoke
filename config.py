"""Application configuration."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _resolve_runtime_root() -> Path:
    """Return writable runtime root for source and packaged builds."""
    if getattr(sys, "frozen", False):
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "KaraokeTicker"
        return Path.home() / ".karaoke-ticker"
    return Path(__file__).resolve().parent


BASE_DIR = _resolve_runtime_root()
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AppConfig:
    """Runtime configuration for Karaoke Ticker."""

    database_url: str = f"sqlite:///{(DATA_DIR / 'karaoke.db').as_posix()}"
    secret_key: str = os.getenv("KARAOKE_TICKER_SECRET", "karaoke-ticker-local-secret")
    host: str = "0.0.0.0"
    port: int = int(os.getenv("KARAOKE_TICKER_PORT", "8585"))
    default_karaoke_folder: str = ""
    default_kanto_executable: str = ""
    default_ticker_upcoming_count: int = 5
    default_singer_rotation_on: bool = True
    default_house_name: str = "Karaoke Ticker"

