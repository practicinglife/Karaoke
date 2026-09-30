"""Background indexer service for karaoke library.

Runs periodic builds of the local karaoke index and writes a static client-facing
JSON index. Indexing is skipped while a house session is RUNNING.
Also maintains a local directory snapshot JSON used for quick comparison.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import DATA_DIR

from .library_indexer import SUPPORTED_EXTENSIONS, build_index, build_index_from_manifest
from .services import active_session, get_setting


class BackgroundIndexer:
    def __init__(self, runtime_state, interval_seconds: int = 300) -> None:
        self.runtime_state = runtime_state
        self.interval = interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._request_now = threading.Event()
        self._request_compare = threading.Event()
        self._deferred_index = False
        self.snapshot_path = Path(DATA_DIR) / "karaoke_directory_snapshot.json"
        self.runtime_state.index_progress = 0.0
        self.runtime_state.index_progress_text = "Idle"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def request_index(self) -> None:
        """Request an immediate index pass (runs on the background thread)."""
        self._request_now.set()

    def request_compare(self) -> None:
        """Request a snapshot comparison pass only."""
        self._request_compare.set()

    def _set_status(self, *, status: str | None = None, compare: str | None = None) -> None:
        if status is not None:
            self.runtime_state.index_status = status
        if compare is not None:
            self.runtime_state.index_compare_summary = compare

    def _set_last_run(self) -> None:
        self.runtime_state.index_last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _set_progress(self, value: float, text: str) -> None:
        clamped = min(1.0, max(0.0, float(value)))
        self.runtime_state.index_progress = clamped
        self.runtime_state.index_progress_text = text

    def _hydrate_status_from_existing_snapshot(self) -> None:
        snapshot = self._load_snapshot()
        if not snapshot:
            return

        file_count = snapshot.get("file_count")
        generated_at = str(snapshot.get("generated_at") or "").strip()
        mode = str(snapshot.get("mode") or "directory")

        if generated_at:
            try:
                parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                self.runtime_state.index_last_run = parsed.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                self.runtime_state.index_last_run = generated_at

        if isinstance(file_count, int):
            self.runtime_state.index_compare_summary = f"Mode: {mode} | Files: {file_count}"
        self.runtime_state.index_status = "Snapshot loaded"
        self._set_progress(1.0, "Loaded previous snapshot")

    def _scan_directory_snapshot(self, karaoke_root: str) -> dict[str, Any]:
        root = Path(karaoke_root)
        files: dict[str, dict[str, int | str]] = {}
        if not root.exists():
            self._set_progress(0.0, "Snapshot: folder not found")
            return {
                "root": karaoke_root,
                "generated_at": "",
                "files": files,
                "file_names": [],
                "file_count": 0,
            }

        scanned = 0
        matched = 0
        self._set_progress(0.05, "Scanning files...")
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            scanned += 1
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                if scanned % 250 == 0:
                    pulse = 0.1 + ((scanned % 1000) / 1000.0) * 0.7
                    self._set_progress(pulse, f"Scanning checked {scanned} files")
                continue

            try:
                stat = path.stat()
            except Exception:
                continue

            rel_path = path.relative_to(root).as_posix()
            files[rel_path] = {
                "size": int(stat.st_size),
                "mtime": str(int(stat.st_mtime)),
            }
            matched += 1
            if scanned % 100 == 0:
                pulse = 0.1 + ((scanned % 1000) / 1000.0) * 0.7
                self._set_progress(pulse, f"Scanning checked {scanned}, matched {matched}")

        file_names = sorted(files.keys())
        self._set_progress(1.0, f"Scan complete ({len(files)} files)")
        return {
            "root": karaoke_root,
            "generated_at": datetime.utcnow().isoformat(),
            "files": files,
            "file_names": file_names,
            "file_count": len(files),
        }

    def _scan_manifest_snapshot(self, manifest_path: str) -> dict[str, Any]:
        path = Path(manifest_path)
        if not path.exists():
            self._set_progress(0.0, "Manifest file not found")
            return {
                "root": manifest_path,
                "generated_at": "",
                "files": {},
                "file_names": [],
                "file_count": 0,
                "mode": "manifest",
                "manifest_size": 0,
                "manifest_mtime": "0",
            }

        try:
            stat = path.stat()
        except Exception:
            stat = None

        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)

        if not isinstance(payload, list):
            payload = []

        files: dict[str, dict[str, int | str]] = {}
        file_names: list[str] = []
        total = len(payload)
        if total == 0:
            self._set_progress(1.0, "Manifest contains 0 entries")
        else:
            self._set_progress(0.05, f"Reading manifest 0/{total}")

        for idx, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            song_name = str(item.get("SongName", "")).strip()
            folder = str(item.get("Folder", "")).strip()
            audio = str(item.get("AudioFile") or "").strip()
            cdg = str(item.get("CDGFile") or "").strip()
            key = f"{folder}/{song_name}" if folder else song_name
            files[key] = {
                "audio": audio,
                "cdg": cdg,
            }
            if song_name:
                file_names.append(song_name)
            if idx == total or idx % 250 == 0:
                self._set_progress(idx / total, f"Reading manifest {idx}/{total}")

        return {
            "root": manifest_path,
            "generated_at": datetime.utcnow().isoformat(),
            "files": files,
            "file_names": sorted(file_names),
            "file_count": len(files),
            "mode": "manifest",
            "manifest_size": int(stat.st_size) if stat else 0,
            "manifest_mtime": str(int(stat.st_mtime)) if stat else "0",
        }

    def _load_snapshot(self) -> dict[str, Any]:
        if not self.snapshot_path.exists():
            return {}
        try:
            with self.snapshot_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _save_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with self.snapshot_path.open("w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False)

    def _compare_snapshot_maps(
        self,
        old_files: dict[str, dict[str, int | str]],
        new_files: dict[str, dict[str, int | str]],
    ) -> tuple[int, int, int]:
        old_keys = set(old_files.keys())
        new_keys = set(new_files.keys())
        added = len(new_keys - old_keys)
        removed = len(old_keys - new_keys)
        changed = 0
        for key in (old_keys & new_keys):
            old_meta = old_files.get(key, {})
            new_meta = new_files.get(key, {})
            if old_meta.get("size") != new_meta.get("size") or old_meta.get("mtime") != new_meta.get("mtime"):
                changed += 1
        return added, removed, changed

    def _compare_and_persist_snapshot(
        self,
        karaoke_root: str,
        manifest_path: str | None = None,
    ) -> tuple[bool, str]:
        old_snapshot = self._load_snapshot()
        old_files = old_snapshot.get("files") if isinstance(old_snapshot.get("files"), dict) else {}

        if manifest_path:
            new_snapshot = self._scan_manifest_snapshot(manifest_path)
            mode = "manifest"
        else:
            new_snapshot = self._scan_directory_snapshot(karaoke_root)
            mode = "directory"

        new_files = new_snapshot.get("files") if isinstance(new_snapshot.get("files"), dict) else {}

        added, removed, changed = self._compare_snapshot_maps(old_files, new_files)
        summary = (
            f"Mode: {mode} | Files: {len(new_files)} | Added: {added} "
            f"Removed: {removed} Changed: {changed}"
        )

        self._save_snapshot(new_snapshot)
        self._set_last_run()
        return (added + removed + changed) > 0, summary

    def _run_index_pass(
        self,
        session,
        karaoke_root: str,
        manifest_path: str | None = None,
    ) -> None:
        self._set_progress(0.05, "Snapshot compare")
        has_changes, summary = self._compare_and_persist_snapshot(karaoke_root, manifest_path)
        self._set_status(compare=summary)

        cache_file = Path(DATA_DIR) / "karaoke_index_cache.json"
        static_file = Path(__file__).resolve().parent.parent / "web" / "static" / "data" / "karaoke_index.json"
        needs_first_build = not cache_file.exists() or not static_file.exists()

        if active_session(session):
            self._set_status(status="Index deferred (house running)")
            self._set_progress(0.0, "Deferred while house running")
            self._deferred_index = self._deferred_index or has_changes or needs_first_build
            return

        if not has_changes and not needs_first_build and not self._deferred_index:
            self._set_status(status="Ready (no changes)")
            self._set_progress(1.0, "Ready")
            return

        if manifest_path:
            self._set_status(status="Indexing from local manifest...")
            self._set_progress(0.25, "Building index from manifest")
            count = build_index_from_manifest(session, manifest_path)
        else:
            self._set_status(status="Indexing local library...")
            self._set_progress(0.25, "Building local index")
            count = build_index(session, karaoke_root)

        self._deferred_index = False
        self._set_status(status=f"Ready (indexed {count} entries)")
        self._set_progress(1.0, f"Indexed {count} entries")

    def _run(self) -> None:
        self._hydrate_status_from_existing_snapshot()
        if self.runtime_state.index_status == "Idle":
            self._set_status(status="Idle (waiting for scan request)")
            self._set_progress(0.0, "Idle")
        while not self._stop.is_set():
            try:
                with self.runtime_state.db.session_scope() as session:  # type: ignore[attr-defined]
                    folder = get_setting(session, "karaoke_folder")
                    manifest_path = get_setting(session, "karaoke_manifest_path").strip()
                    manifest_ready = bool(manifest_path and Path(manifest_path).exists())

                    if not folder and not manifest_ready:
                        self._set_status(status="No karaoke folder or manifest configured")
                        self._set_progress(0.0, "Waiting for configuration")
                    else:
                        if manifest_path and not manifest_ready:
                            self._set_status(status="Manifest not found, using folder scan")

                        selected_manifest = manifest_path if manifest_ready else None
                        run_root = folder if folder else "manifest-mode"

                        compare_requested = self._request_compare.is_set()
                        requested_index_now = self._request_now.is_set()

                        if compare_requested:
                            self._request_compare.clear()
                            self._set_status(status="Comparing library snapshot...")
                            self._set_progress(0.1, "Compare requested")
                            _, summary = self._compare_and_persist_snapshot(run_root, selected_manifest)
                            self._set_status(status="Compare complete", compare=summary)
                            self._set_progress(1.0, "Compare complete")

                        if requested_index_now:
                            self._request_now.clear()
                            self._deferred_index = True

                        # Only index on explicit scan request, or when a deferred scan is pending.
                        if requested_index_now or self._deferred_index:
                            self._run_index_pass(session, run_root, selected_manifest)
                        elif not compare_requested:
                            self._set_status(status="Idle (waiting for scan request)")
                            self._set_progress(0.0, "Idle")
            except Exception:
                self._set_status(status="Indexer error")
                try:
                    import logging

                    logging.exception("BackgroundIndexer error")
                except Exception:
                    traceback.print_exc()

            wait_target = 5.0 if self._deferred_index else float(self.interval)
            waited = 0.0
            while (
                waited < wait_target
                and not self._stop.is_set()
                and not self._request_now.is_set()
                and not self._request_compare.is_set()
            ):
                time.sleep(0.5)
                waited += 0.5
