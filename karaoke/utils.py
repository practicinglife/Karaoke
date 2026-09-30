"""Utility helpers."""

from __future__ import annotations

import random
import re
import socket
import string
from pathlib import Path
from typing import Tuple


def normalize_text(value: str) -> str:
    """Normalize text for insensitive matching."""
    lower = value.lower().strip()
    replaced = lower.replace("_", " ").replace("-", " ")
    replaced = replaced.translate(str.maketrans({"[": " ", "]": " ", "(": " ", ")": " "}))
    cleaned = re.sub(r"[^a-z0-9\s]", " ", replaced)
    collapsed = re.sub(r"\s+", " ", cleaned).strip()
    return collapsed


def split_artist_title_from_name(file_stem: str) -> Tuple[str, str]:
    """Split common artist-title naming format."""
    cleaned = file_stem.replace("_", " ").strip()
    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        return left.strip(), right.strip()
    return "", cleaned


def generate_house_code() -> str:
    """Generate six-digit numeric house code."""
    return "".join(random.choices(string.digits, k=6))


def get_lan_ip() -> str:
    """Best-effort LAN IP lookup."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def is_path_under(root: Path, candidate: Path) -> bool:
    """Prevent path traversal by verifying a candidate lives under root."""
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
