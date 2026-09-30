"""Local karaoke library indexing and search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json

from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .models import KaraokeLibrary
from .utils import normalize_text, split_artist_title_from_name
from config import DATA_DIR

SUPPORTED_EXTENSIONS = {
    ".cdg",
    ".mp3",
    ".mps",
    ".zip",
    ".kar",
    ".mid",
    ".midi",
    ".mp4",
    ".mkv",
    ".avi",
    ".wmv",
}


def _record_from_stem(stem: str) -> dict[str, str]:
    artist, title = split_artist_title_from_name(stem)
    display_name = f"{artist} - {title}".strip(" -")
    normalized_blob = normalize_text(f"{artist} {title} {display_name} {stem}")
    return {
        "title": title or stem,
        "artist": artist,
        "display_name": display_name or stem,
        "search_blob": normalized_blob,
    }


def _record_from_file(path: Path) -> dict[str, str | int]:
    stem_data = _record_from_stem(path.stem)
    stat = path.stat()
    return {
        "title": stem_data["title"],
        "artist": stem_data["artist"],
        "display_name": stem_data["display_name"],
        "primary_file": str(path),
        "audio_file": str(path) if path.suffix.lower() == ".mp3" else "",
        "cdg_file": str(path) if path.suffix.lower() == ".cdg" else "",
        "folder": str(path.parent),
        "extension": path.suffix.lower(),
        "modified_time": str(int(stat.st_mtime)),
        "file_size": int(stat.st_size),
        "active": True,
        "search_blob": stem_data["search_blob"],
    }


def _finalize_index_outputs(session: Session, cache_path: Path) -> None:
    """Write server cache and static client index from current active DB rows."""
    new_cache: dict[str, dict[str, Any]] = {}
    for row in session.scalars(select(KaraokeLibrary).where(KaraokeLibrary.active == True)):  # noqa: E712
        new_cache[row.primary_file] = {
            "title": row.title,
            "artist": row.artist,
            "display_name": row.display_name,
            "modified_time": row.modified_time,
            "file_size": row.file_size,
        }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as fh:
        json.dump(new_cache, fh, ensure_ascii=False)

    project_root = Path(__file__).resolve().parent.parent
    static_data_dir = project_root / "web" / "static" / "data"
    static_data_dir.mkdir(parents=True, exist_ok=True)
    static_file = static_data_dir / "karaoke_index.json"

    items: list[dict[str, Any]] = []
    for row in session.scalars(select(KaraokeLibrary).where(KaraokeLibrary.active == True)):  # noqa: E712
        raw_name = Path(row.primary_file).stem
        items.append(
            {
                "id": row.id,
                "title": row.title,
                "artist": row.artist,
                "display_name": row.display_name,
                "raw_name": raw_name,
                "extension": row.extension,
            }
        )

    with static_file.open("w", encoding="utf-8") as sf:
        json.dump(items, sf, ensure_ascii=False)


def build_index(session: Session, karaoke_root: str) -> int:
    """Scan karaoke root and rebuild active index."""
    root = Path(karaoke_root)
    if not root.exists():
        raise FileNotFoundError(f"Karaoke folder not found: {karaoke_root}")

    files: list[Path] = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    # Load on-disk cache mapping primary_file -> metadata to avoid re-processing unchanged files.
    cache_path = Path(DATA_DIR) / "karaoke_index_cache.json"
    cached: dict[str, dict] = {}
    try:
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
    except Exception:
        # If cache is unreadable, ignore and rebuild; do not crash indexing.
        cached = {}

    # Mark all existing DB entries inactive and create a fast lookup map.
    existing_rows = list(session.scalars(select(KaraokeLibrary)))
    for item in existing_rows:
        item.active = False
    existing_by_primary: dict[str, KaraokeLibrary] = {
        row.primary_file: row for row in existing_rows
    }

    paired: set[Path] = set()
    created = 0

    for path in files:
        if path in paired:
            continue
        suffix = path.suffix.lower()
        if suffix in {".mp3", ".cdg"}:
            companion = path.with_suffix(".cdg" if suffix == ".mp3" else ".mp3")
            if companion.exists():
                base = _record_from_stem(path.stem)
                mp3_path = path.with_suffix(".mp3")
                cdg_path = path.with_suffix(".cdg")
                if mp3_path.exists():
                    paired.add(mp3_path)
                if cdg_path.exists():
                    paired.add(cdg_path)
                record = KaraokeLibrary(
                    title=base["title"],  # type: ignore[arg-type]
                    artist=base["artist"],  # type: ignore[arg-type]
                    display_name=base["display_name"],  # type: ignore[arg-type]
                    primary_file=str(mp3_path if mp3_path.exists() else cdg_path),
                    audio_file=str(mp3_path) if mp3_path.exists() else None,
                    cdg_file=str(cdg_path) if cdg_path.exists() else None,
                    folder=str(path.parent),
                    extension=".mp3+.cdg",
                    modified_time=str(
                        int(
                            max(
                                mp3_path.stat().st_mtime if mp3_path.exists() else 0,
                                cdg_path.stat().st_mtime if cdg_path.exists() else 0,
                            )
                        )
                    ),
                    file_size=int(
                        (mp3_path.stat().st_size if mp3_path.exists() else 0)
                        + (cdg_path.stat().st_size if cdg_path.exists() else 0)
                    ),
                    active=True,
                    search_blob=normalize_text(
                        f"{base['artist']} {base['title']} {base['display_name']} {path.stem}"
                    ),
                )
                session.add(record)
                created += 1
                continue
        # Quick path: if cache contains matching metadata and file stats match, re-activate DB row.
        primary = str(path)
        try:
            stat = path.stat()
            mtime = str(int(stat.st_mtime))
            fsize = int(stat.st_size)
        except Exception:
            mtime = ""
            fsize = 0

        cached_entry = cached.get(primary)
        existing = existing_by_primary.get(primary)
        if cached_entry and cached_entry.get("modified_time") == mtime and cached_entry.get("file_size") == fsize:
            # Reactivate existing DB record if present
            if existing:
                existing.active = True
                paired.add(path)
                # nothing new created
                continue

        # If no cache hit, check existing row metadata as fallback
        if existing:
            try:
                if existing.modified_time == mtime and existing.file_size == fsize:
                    existing.active = True
                    paired.add(path)
                    continue
            except Exception:
                pass

        record_data = _record_from_file(path)
        if existing:
            existing.title = record_data["title"]  # type: ignore[assignment]
            existing.artist = record_data["artist"]  # type: ignore[assignment]
            existing.display_name = record_data["display_name"]  # type: ignore[assignment]
            existing.audio_file = record_data["audio_file"] or None  # type: ignore[assignment]
            existing.cdg_file = record_data["cdg_file"] or None  # type: ignore[assignment]
            existing.folder = record_data["folder"]  # type: ignore[assignment]
            existing.extension = record_data["extension"]  # type: ignore[assignment]
            existing.modified_time = record_data["modified_time"]  # type: ignore[assignment]
            existing.file_size = record_data["file_size"]  # type: ignore[assignment]
            existing.active = True
            existing.search_blob = record_data["search_blob"]  # type: ignore[assignment]
        else:
            row = KaraokeLibrary(
                title=record_data["title"],  # type: ignore[arg-type]
                artist=record_data["artist"],  # type: ignore[arg-type]
                display_name=record_data["display_name"],  # type: ignore[arg-type]
                primary_file=record_data["primary_file"],  # type: ignore[arg-type]
                audio_file=record_data["audio_file"] or None,  # type: ignore[arg-type]
                cdg_file=record_data["cdg_file"] or None,  # type: ignore[arg-type]
                folder=record_data["folder"],  # type: ignore[arg-type]
                extension=record_data["extension"],  # type: ignore[arg-type]
                modified_time=record_data["modified_time"],  # type: ignore[arg-type]
                file_size=record_data["file_size"],  # type: ignore[arg-type]
                active=True,
                search_blob=record_data["search_blob"],  # type: ignore[arg-type]
            )
            session.add(row)
            existing_by_primary[primary] = row
            created += 1
    session.flush()

    try:
        _finalize_index_outputs(session, cache_path)
    except Exception:
        # Don't fail indexing on cache write errors.
        pass

    return created


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def build_index_from_manifest(session: Session, manifest_path: str) -> int:
    """Build active library index from local manifest JSON.

    Manifest format is compatible with the PowerShell index script output:
    SongName, Folder, HasCDG, HasMP3, HasMPS, AudioFile, CDGFile.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    if not isinstance(payload, list):
        raise ValueError("Manifest file must contain a JSON array.")

    for item in session.scalars(select(KaraokeLibrary)):
        item.active = False

    existing_by_primary: dict[str, KaraokeLibrary] = {
        row.primary_file: row
        for row in session.scalars(select(KaraokeLibrary))
    }

    processed = 0

    for raw in payload:
        if not isinstance(raw, dict):
            continue
        song_name = str(raw.get("SongName", "")).strip()
        folder = str(raw.get("Folder", "")).strip()
        if not song_name or not folder:
            continue

        audio_name = str(raw.get("AudioFile") or "").strip()
        cdg_name = str(raw.get("CDGFile") or "").strip()
        has_mps = _to_bool(raw.get("HasMPS"))
        has_mp3 = _to_bool(raw.get("HasMP3"))
        has_cdg = _to_bool(raw.get("HasCDG"))

        audio_path = str((Path(folder) / audio_name)) if audio_name else ""
        cdg_path = str((Path(folder) / cdg_name)) if cdg_name else ""
        primary_file = audio_path or cdg_path or str(Path(folder) / song_name)

        stem_data = _record_from_stem(song_name)
        if has_mp3 and has_cdg:
            extension = ".mp3+.cdg"
        elif has_mps:
            extension = ".mps"
        elif has_mp3:
            extension = ".mp3"
        elif has_cdg:
            extension = ".cdg"
        else:
            extension = Path(audio_name or cdg_name).suffix.lower() if (audio_name or cdg_name) else ""

        existing = existing_by_primary.get(primary_file)
        if existing:
            existing.title = stem_data["title"]
            existing.artist = stem_data["artist"]
            existing.display_name = stem_data["display_name"]
            existing.audio_file = audio_path or None
            existing.cdg_file = cdg_path or None
            existing.folder = folder
            existing.extension = extension
            existing.modified_time = "0"
            existing.file_size = 0
            existing.active = True
            existing.search_blob = stem_data["search_blob"]
        else:
            created = KaraokeLibrary(
                title=stem_data["title"],
                artist=stem_data["artist"],
                display_name=stem_data["display_name"],
                primary_file=primary_file,
                audio_file=audio_path or None,
                cdg_file=cdg_path or None,
                folder=folder,
                extension=extension,
                modified_time="0",
                file_size=0,
                active=True,
                search_blob=stem_data["search_blob"],
            )
            session.add(created)
            existing_by_primary[primary_file] = created

        processed += 1

    session.flush()

    try:
        _finalize_index_outputs(session, Path(DATA_DIR) / "karaoke_index_cache.json")
    except Exception:
        pass

    return processed


def search_library(
    session: Session, query: str, *, limit: int = 20
) -> list[KaraokeLibrary]:
    """Search indexed karaoke library with deterministic fuzzy ranking."""
    normalized_query = normalize_text(query)
    if not normalized_query:
        return []

    candidates = list(session.scalars(select(KaraokeLibrary).where(KaraokeLibrary.active == True)))  # noqa: E712
    scored: list[tuple[int, KaraokeLibrary]] = []
    for item in candidates:
        score = fuzz.token_set_ratio(normalized_query, item.search_blob)
        if normalized_query in item.search_blob:
            score += 15
        if score >= 45:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def search_library_traditional(
    session: Session, query: str, *, limit: int = 20
) -> list[KaraokeLibrary]:
    """Search traditional karaoke with artist-group-first ranking."""
    normalized_query = normalize_text(query or "")
    if not normalized_query:
        return []

    tokens = [token for token in normalized_query.split() if token]
    if not tokens:
        return []

    candidate_limit = max(limit * 8, 120)
    query_pattern = f"%{normalized_query}%"
    prefix_pattern = f"{normalized_query}%"

    candidate_filters = [
        KaraokeLibrary.search_blob.like(query_pattern),
        func.lower(KaraokeLibrary.artist).like(prefix_pattern),
        func.lower(KaraokeLibrary.title).like(prefix_pattern),
        func.lower(KaraokeLibrary.display_name).like(prefix_pattern),
    ]
    for token in tokens[:4]:
        if len(token) < 2:
            continue
        pattern = f"%{token}%"
        candidate_filters.extend(
            [
                KaraokeLibrary.search_blob.like(pattern),
                func.lower(KaraokeLibrary.artist).like(pattern),
                func.lower(KaraokeLibrary.title).like(pattern),
                func.lower(KaraokeLibrary.display_name).like(pattern),
            ]
        )

    candidate_stmt = (
        select(KaraokeLibrary)
        .where(KaraokeLibrary.active == True)  # noqa: E712
        .where(or_(*candidate_filters))
        .limit(candidate_limit)
    )
    candidates = list(session.scalars(candidate_stmt))
    if not candidates:
        candidates = list(
            session.scalars(
                select(KaraokeLibrary)
                .where(KaraokeLibrary.active == True)
                .where(KaraokeLibrary.search_blob.like(query_pattern))
                .limit(candidate_limit)
            )
        )

    scored: list[tuple[tuple[int, int, str, str, str], KaraokeLibrary]] = []
    for item in candidates:
        try:
            artist_norm = normalize_text(item.artist or "")
            title_norm = normalize_text(item.title or "")
            display_norm = normalize_text(item.display_name or "")
            blob_norm = item.search_blob or ""
            if not blob_norm:
                blob_norm = normalize_text(f"{item.artist} {item.title} {item.display_name}")
        except Exception:
            continue

        artist_tokens = artist_norm.split()
        title_tokens = title_norm.split()
        display_tokens = display_norm.split()

        category = 5
        score = fuzz.token_set_ratio(normalized_query, blob_norm)

        if artist_norm.startswith(normalized_query):
            category = 0
            score += 60
        elif normalized_query in artist_norm or any(token.startswith(normalized_query) for token in artist_tokens):
            category = 1
            score += 45
        elif display_norm.startswith(normalized_query) or any(token.startswith(normalized_query) for token in display_tokens):
            category = 2
            score += 25
        elif title_norm.startswith(normalized_query) or any(token.startswith(normalized_query) for token in title_tokens):
            category = 3
            score += 20
        elif normalized_query in display_norm:
            category = 4
            score += 10
        elif normalized_query in title_norm:
            category = 4
            score += 8
        elif normalized_query in blob_norm:
            category = 4
            score += 5
        else:
            continue

        sort_key = (category, -score, artist_norm, title_norm, display_norm)
        scored.append((sort_key, item))

    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored[:limit]]


def list_active_library(session: Session) -> Iterable[KaraokeLibrary]:
    """List active indexed karaoke entries."""
    return session.scalars(
        select(KaraokeLibrary).where(KaraokeLibrary.active == True)  # noqa: E712
    )
