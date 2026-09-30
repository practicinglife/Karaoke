"""Launch local karaoke files or URLs."""

from __future__ import annotations

import logging
import os
import subprocess
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)


def launch_traditional_song(
    file_path: str,
    kanto_executable: str = "",
    cdg_file: str | None = None,
    server_base_url: str = "",
    song_id: int | None = None,
    external_application_path: str = "",
) -> None:
    """Launch local karaoke file through built-in/system/external playback paths.

    Preferred flow on Windows is to open the CDG file so the chosen player can
    load synchronized MP3+CDG lyrics.

    Args:
        file_path: Primary indexed karaoke path.
        kanto_executable: Legacy external executable setting for backward compatibility.
        cdg_file: Optional explicit CDG sidecar path.
        server_base_url: Optional hosted player URL.
        song_id: Optional song ID for hosted player URL.
        external_application_path: Preferred external player executable path.
    """
    primary = Path(file_path)
    if server_base_url:
        remote_url = server_base_url.rstrip("/")
        if not remote_url.endswith("/player"):
            remote_url += "/player"
        if song_id is not None:
            remote_url += f"?song_id={song_id}"
        webbrowser.open(remote_url)
        return
    if not primary.exists():
        raise FileNotFoundError(f"Karaoke file not found: {file_path}")

    target_cdg = None

    # Prefer explicit CDG path from index when it exists.
    if cdg_file:
        explicit_cdg = Path(cdg_file)
        if explicit_cdg.exists():
            target_cdg = explicit_cdg

    # Fallback: derive companion CDG from primary stem.
    if target_cdg is None:
        if primary.suffix.lower() == ".cdg":
            target_cdg = primary
        else:
            companion_cdg = primary.with_suffix(".cdg")
            if companion_cdg.exists():
                target_cdg = companion_cdg

    if target_cdg is None or not target_cdg.exists():
        raise FileNotFoundError("Matching CDG file was not found for traditional karaoke launch.")

    matching_mp3 = target_cdg.with_suffix(".mp3")
    if not matching_mp3.exists():
        raise FileNotFoundError("Matching MP3 file was not found for CDG launch.")

    configured_external_path = (external_application_path or kanto_executable or "").strip()
    logger.info(
        "Launching traditional song file=%s mode=%s external_path_set=%s",
        str(target_cdg),
        "external_application" if configured_external_path else "system_default",
        bool(configured_external_path),
    )

    if os.name == "nt":
        # Prefer direct external executable launch when configured.
        if configured_external_path:
            exe = Path(configured_external_path)
            if not exe.exists():
                raise FileNotFoundError(f"External application not found: {configured_external_path}")
            try:
                subprocess.Popen(
                    [str(exe), str(target_cdg)],
                    shell=False,
                    cwd=str(target_cdg.parent),
                )  # noqa: S603
                return
            except Exception:
                # Fall back to Windows file association if direct launch fails.
                pass

        # Non-blocking association launch via cmd/start (avoids os.startfile UI stalls).
        subprocess.Popen(
            ["cmd", "/c", "start", "", "/b", str(target_cdg)],
            shell=False,
            cwd=str(target_cdg.parent),
        )  # noqa: S603
        return

    # Non-Windows fallback
    webbrowser.open(target_cdg.as_uri())


def launch_url(url: str) -> None:
    """Open URL in default browser."""
    if not webbrowser.open(url):
        raise RuntimeError("Failed to open URL in browser.")

