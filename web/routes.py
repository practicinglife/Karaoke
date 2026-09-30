"""Flask routes for guest, admin, and ticker pages."""

from __future__ import annotations

import secrets
import logging
import json
import mimetypes
import os
import re
from pathlib import Path
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session as flask_session,
    url_for,
)
from flask_socketio import SocketIO
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from karaoke.library_indexer import (
    build_index,
    build_index_from_manifest,
    list_active_library,
    search_library,
    search_library_traditional,
)
from karaoke.models import KaraokeLibrary, QueueItem, SessionRecord, Song, User
from karaoke.queue_manager import COMPLETED, NOW_PLAYING, QueueManager, SKIPPED, WAITING
from karaoke.services import (
    active_session,
    create_or_get_user,
    create_song,
    ensure_default_settings,
    get_external_application_path,
    get_playback_mode,
    get_setting,
    list_user_songs,
    list_users,
    set_external_application_path,
    set_playback_mode,
    set_setting,
    validate_house_code,
)
from karaoke.validators import (
    is_valid_apple_music_url,
    is_valid_spotify_url,
    is_valid_traditional_karaoke_server_url,
    is_valid_youtube_url,
    normalize_user_name,
    validate_artist_name,
    validate_display_name,
    validate_song_title,
)
from karaoke.utils import is_path_under

logger = logging.getLogger(__name__)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".wmv"}


def register_routes(app, runtime_state, socketio: SocketIO) -> None:
    """Register all routes."""
    bp = Blueprint("web", __name__)

    def ensure_csrf() -> str:
        token = flask_session.get("csrf_token")
        if not token:
            token = secrets.token_hex(16)
            flask_session["csrf_token"] = token
        return token

    def verify_csrf() -> None:
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not sent or sent != flask_session.get("csrf_token"):
            abort(400, "Invalid CSRF token.")

    def emit_queue_update() -> None:
        payload = queue_snapshot()
        socketio.emit("queue_updated", payload)

    def queue_snapshot() -> dict[str, Any]:
        with runtime_state.db.session_scope() as db:
            qm = QueueManager(db)
            current = qm.active_session()
            if not current:
                return {
                    "running": False,
                    "now_playing": None,
                    "up_next": [],
                }
            rotation = get_setting(db, "singer_rotation_on") == "1"
            upcoming_count = int(get_setting(db, "ticker_upcoming_count") or "5")
            now = qm.now_playing(current.id)
            ordered = qm.ordered_up_next(current.id, rotation)
            return {
                "running": True,
                "house_code": current.house_code,
                "session_id": current.id,
                "now_playing": serialize_item(now) if now else None,
                "up_next": [serialize_item(i) for i in ordered[:upcoming_count]],
                "queue_all": [serialize_item(i) for i in ordered],
            }

    def serialize_item(item: QueueItem | None) -> dict[str, Any] | None:
        if not item:
            return None
        return {
            "id": item.id,
            "song_id": item.song_id,
            "user": item.user.display_name if item.user else "",
            "song": item.song.title if item.song else "",
            "artist": item.song.artist if item.song else "",
            "service": item.song.service if item.song else "",
            "status": item.status,
            "added_at": item.added_at.isoformat(),
        }

    def user_notification_state(
        user_name: str,
        now_playing: QueueItem | None,
        up_next_items: list[QueueItem],
    ) -> dict[str, str]:
        normalized_user = user_name.strip().casefold()
        if not normalized_user:
            return {"phase": "none", "song": "", "artist": ""}

        def _matches(item: QueueItem | None) -> bool:
            return bool(
                item
                and item.user
                and item.user.display_name.strip().casefold() == normalized_user
            )

        if _matches(now_playing):
            return {
                "phase": "up-now",
                "song": now_playing.song.title if now_playing and now_playing.song else "",
                "artist": now_playing.song.artist if now_playing and now_playing.song else "",
            }

        first_up_next = up_next_items[0] if up_next_items else None
        if _matches(first_up_next):
            return {
                "phase": "up-next",
                "song": first_up_next.song.title if first_up_next and first_up_next.song else "",
                "artist": first_up_next.song.artist if first_up_next and first_up_next.song else "",
            }

        return {"phase": "none", "song": "", "artist": ""}

    def _validate_external_application_path(path_value: str) -> tuple[bool, str]:
        raw = (path_value or "").strip()
        if not raw:
            return False, "External application path is required for External Application mode."

        path = Path(raw).expanduser()
        if not path.exists():
            return False, "External application path does not exist."

        if path.suffix.lower() == ".app" and path.is_dir():
            return True, ""

        if path.is_file():
            if os.name == "nt":
                if path.suffix.lower() in {".exe", ".bat", ".cmd", ".com"}:
                    return True, ""
                return False, "On Windows, external application must be an executable (.exe/.bat/.cmd/.com)."
            if os.access(path, os.X_OK):
                return True, ""
            return False, "External application file is not executable."

        return False, "External application path must point to an executable file or .app bundle."

    def _ensure_traditional_library_index(db) -> bool:
        if db.scalar(select(KaraokeLibrary.id).where(KaraokeLibrary.active == True).limit(1)) is not None:  # noqa: E712
            return False

        folder = str(get_setting(db, "karaoke_folder") or "").strip()
        manifest_path = str(get_setting(db, "karaoke_manifest_path") or "").strip()
        try:
            if manifest_path and Path(manifest_path).exists():
                build_index_from_manifest(db, manifest_path)
                return True
            if folder:
                build_index(db, folder)
                return True
        except Exception:
            logger.exception("Failed to rebuild the traditional karaoke index on demand")
        return False

    def _player_media_root(db_session) -> Path:
        folder = str(get_setting(db_session, "karaoke_folder") or "").strip()
        if not folder:
            raise FileNotFoundError("Karaoke folder is not configured.")
        return Path(folder).expanduser()

    def _resolve_player_media_path(entry: KaraokeLibrary, kind: str, root: Path) -> Path:
        primary_suffix = Path(entry.primary_file).suffix.lower()
        if kind == "audio":
            candidates = [entry.audio_file] if entry.audio_file else []
            if primary_suffix == ".mp3":
                candidates.append(entry.primary_file)
        elif kind == "cdg":
            candidates = [entry.cdg_file] if entry.cdg_file else []
            if primary_suffix == ".cdg":
                candidates.append(entry.primary_file)
        elif kind == "video":
            candidates: list[str | None] = []
            if primary_suffix in VIDEO_EXTENSIONS:
                candidates.append(entry.primary_file)
            if entry.audio_file and Path(entry.audio_file).suffix.lower() in VIDEO_EXTENSIONS:
                candidates.append(entry.audio_file)
        else:
            raise ValueError("Unsupported media kind.")

        for raw_path in candidates:
            if not raw_path:
                continue
            path = Path(raw_path)
            if not path.exists():
                continue
            if root and not is_path_under(root, path):
                continue
            return path

        raise FileNotFoundError(f"Matching {kind.upper()} file was not found for the selected library item.")

    def require_guest_session() -> tuple[int, SessionRecord]:
        user_id = flask_session.get("user_id")
        session_id = flask_session.get("session_id")
        if not user_id or not session_id:
            abort(403, "Guest session not found.")
        with runtime_state.db.session_scope() as db:
            record = db.get(SessionRecord, session_id)
            if not record or record.status != "RUNNING":
                abort(403, "Session is no longer active.")
            return user_id, record

    def require_admin() -> SessionRecord:
        token = request.args.get("token") or request.headers.get("X-Admin-Token")
        if not token:
            abort(403, "Missing admin token.")
        with runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record or record.admin_token != token:
                abort(403, "Invalid admin token.")
            return record

    def require_ticker() -> SessionRecord:
        token = request.args.get("token") or request.headers.get("X-Ticker-Token")
        if not token:
            abort(403, "Missing ticker token.")
        with runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record or record.ticker_token != token:
                abort(403, "Invalid ticker token.")
            return record

    def _http_json_get(url: str) -> dict[str, Any]:
        req = Request(url, headers={"User-Agent": "KaraokeTicker/1.0"})
        with urlopen(req, timeout=6) as response:
            payload = response.read().decode("utf-8")
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}

    def _http_text_get(url: str, *, validator=None, provider_name: str = "link") -> str:
        req = Request(url, headers={"User-Agent": "KaraokeTicker/1.0"})
        with urlopen(req, timeout=6) as response:
            final_url = ""
            if hasattr(response, "geturl"):
                final_url = str(response.geturl() or "").strip()
            if final_url and validator and not validator(final_url):
                logger.warning("Rejected non-%s redirect during metadata fetch: %s", provider_name, final_url)
                return ""
            return response.read().decode("utf-8", errors="ignore")

    def _extract_html_meta(html: str, *keys: str) -> str:
        lookup = {k.lower() for k in keys}
        for tag_match in re.finditer(r"<meta\b[^>]*>", html, flags=re.IGNORECASE):
            tag = tag_match.group(0)
            name_match = re.search(
                r"(?:property|name)\s*=\s*[\"']([^\"']+)[\"']",
                tag,
                flags=re.IGNORECASE,
            )
            content_match = re.search(
                r"content\s*=\s*[\"']([^\"']+)[\"']",
                tag,
                flags=re.IGNORECASE,
            )
            if not name_match or not content_match:
                continue
            if name_match.group(1).strip().lower() in lookup:
                return unescape(content_match.group(1)).strip()
        return ""

    def _split_artist_title_from_youtube_title(raw_title: str) -> tuple[str, str] | None:
        """Infer artist/title from common YouTube title patterns like 'Artist - Song'."""
        cleaned = " ".join(str(raw_title).strip().split())
        if not cleaned:
            return None
        for separator in (" - ", " – ", " | ", " — "):
            if separator in cleaned:
                left, right = cleaned.split(separator, 1)
                artist = left.strip()
                title = right.strip()
                if artist and title:
                    return artist, title
        return None

    def _resolve_youtube_metadata(url: str) -> tuple[str, str] | None:
        if not is_valid_youtube_url(url):
            return None

        endpoints = (
            f"https://www.youtube.com/oembed?url={quote_plus(url)}&format=json",
            f"https://noembed.com/embed?url={quote_plus(url)}",
        )
        for endpoint in endpoints:
            try:
                data = _http_json_get(endpoint)
            except Exception as exc:
                logger.warning("YouTube metadata lookup failed for URL '%s' (%s): %s", url, endpoint, exc)
                continue

            title = str(data.get("title", "")).strip()
            artist = str(data.get("author_name", "")).strip()
            if title and artist:
                return title, artist

            guessed = _split_artist_title_from_youtube_title(title)
            if guessed:
                guessed_artist, guessed_title = guessed
                return guessed_title, guessed_artist

        try:
            html = _http_text_get(url, validator=is_valid_youtube_url, provider_name="YouTube")
        except Exception as exc:
            logger.warning("YouTube page metadata fetch failed for URL '%s': %s", url, exc)
            return None

        if not html:
            return None

        title = _extract_html_meta(html, "og:title", "twitter:title")
        artist = _extract_html_meta(html, "author", "twitter:creator")

        if not artist:
            owner_match = re.search(r'"ownerChannelName":"([^\"]+)"', html)
            if owner_match:
                artist = unescape(owner_match.group(1)).strip()

        if title and artist:
            return title, artist

        guessed = _split_artist_title_from_youtube_title(title)
        if guessed:
            guessed_artist, guessed_title = guessed
            return guessed_title, guessed_artist

        return None

    def _resolve_apple_music_metadata(url: str) -> tuple[str, str] | None:
        if not is_valid_apple_music_url(url):
            return None

        parsed = urlparse(url)
        query_track_id = parse_qs(parsed.query).get("i", [""])[0].strip()
        path_parts = [part.strip() for part in parsed.path.split("/") if part.strip()]
        path_track_id = next((part for part in reversed(path_parts) if part.isdigit()), "")

        lookup_candidates: list[str] = []
        if query_track_id.isdigit():
            lookup_candidates.append(query_track_id)
        if path_track_id.isdigit() and path_track_id not in lookup_candidates:
            lookup_candidates.append(path_track_id)

        for track_id in lookup_candidates:
            lookup_url = f"https://itunes.apple.com/lookup?id={track_id}&entity=song"
            try:
                data = _http_json_get(lookup_url)
            except Exception as exc:
                logger.warning("Apple Music metadata lookup failed for URL '%s': %s", url, exc)
                continue

            rows = data.get("results")
            if not isinstance(rows, list):
                continue

            song_row = next(
                (
                    row
                    for row in rows
                    if isinstance(row, dict)
                    and row.get("wrapperType") == "track"
                    and row.get("kind") == "song"
                ),
                None,
            )
            if not isinstance(song_row, dict):
                continue

            title = str(song_row.get("trackName", "")).strip()
            artist = str(song_row.get("artistName", "")).strip()
            if title or artist:
                return title, artist

        return None

    def _resolve_spotify_metadata(url: str) -> tuple[str, str] | None:
        if not is_valid_spotify_url(url):
            return None

        def _parse_spotify_title(raw: str) -> tuple[str, str] | None:
            cleaned = re.sub(r"\s*\|\s*Spotify\s*$", "", raw, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"\s+on\s+Spotify\s*$", "", cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(
                r"\s*-\s*song(?:\s*and\s*lyrics)?\s*by\s+",
                " by ",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            if not cleaned or cleaned.casefold() == "spotify":
                return None

            artist_name = ""
            title_name = cleaned

            by_split = re.split(r"\s+by\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)
            if len(by_split) == 2:
                title_name = by_split[0].strip()
                artist_name = by_split[1].strip()
            elif " - " in cleaned:
                left, right = cleaned.split(" - ", 1)
                if left.strip() and right.strip():
                    artist_name = left.strip()
                    title_name = right.strip()

            if title_name and artist_name and artist_name.casefold() != "spotify":
                return title_name, artist_name
            if title_name:
                return title_name, ""
            return None

        endpoint = f"https://open.spotify.com/oembed?url={quote_plus(url)}"
        title = ""
        artist = ""

        try:
            data = _http_json_get(endpoint)
        except Exception as exc:
            logger.warning("Spotify metadata lookup failed for URL '%s': %s", url, exc)
            data = {}

        parsed = _parse_spotify_title(str(data.get("title", "")).strip())
        if parsed:
            title, artist = parsed
            if title and artist:
                return title, artist

        try:
            html = _http_text_get(url, validator=is_valid_spotify_url, provider_name="Spotify")
        except Exception as exc:
            logger.warning("Spotify page metadata fetch failed for URL '%s': %s", url, exc)
            html = ""

        if html:
            if not title:
                title = _extract_html_meta(html, "og:title", "twitter:title")

            if not artist:
                artist = _extract_html_meta(
                    html,
                    "music:musician_description",
                    "twitter:audio:artist_name",
                    "twitter:creator",
                )

            if not artist:
                description = _extract_html_meta(html, "og:description", "twitter:description")
                if description:
                    by_match = re.search(r"\bby\s+([^|·•]+)", description, flags=re.IGNORECASE)
                    if by_match:
                        artist = by_match.group(1).strip()
                    else:
                        parts = [part.strip() for part in re.split(r"[|·•]", description) if part.strip()]
                        non_artist_tokens = {"song", "single", "album", "ep"}
                        if title and parts and parts[0].casefold() == title.casefold() and len(parts) > 1:
                            candidate = parts[1]
                            if candidate.casefold() in non_artist_tokens and len(parts) > 2:
                                candidate = parts[2]
                            artist = candidate
                        elif len(parts) >= 2:
                            candidate = parts[1]
                            if candidate.casefold() in non_artist_tokens and len(parts) > 2:
                                candidate = parts[2]
                            artist = candidate

        title = title.strip()
        artist = artist.strip()
        if artist.casefold() == "spotify":
            artist = ""
        if not title:
            return None
        return title, artist

    def _resolve_metadata_for_service(service: str, url: str) -> tuple[str, str] | None:
        if service == "youtube":
            return _resolve_youtube_metadata(url)
        if service == "apple_music":
            return _resolve_apple_music_metadata(url)
        if service == "spotify":
            return _resolve_spotify_metadata(url)
        return None

    def _split_bulk_song_line(line: str) -> list[str]:
        """Split a bulk song line by supported delimiters while preserving content."""
        trimmed = line.strip()
        if not trimmed:
            return []
        for delimiter in ("|", "\t", ","):
            parts = [part.strip() for part in trimmed.split(delimiter)]
            if len(parts) >= 3:
                return parts
        return [trimmed]

    def _infer_streaming_service(url: str) -> str | None:
        """Infer supported streaming service from URL."""
        if is_valid_youtube_url(url):
            return "youtube"
        if is_valid_apple_music_url(url):
            return "apple_music"
        if is_valid_spotify_url(url):
            return "spotify"
        return None

    def _is_valid_streaming_url(service: str, url: str) -> bool:
        if service == "youtube":
            return is_valid_youtube_url(url)
        if service == "apple_music":
            return is_valid_apple_music_url(url)
        if service == "spotify":
            return is_valid_spotify_url(url)
        return False

    def _is_bulk_header_row(parts: list[str]) -> bool:
        lowered = [part.strip().lower() for part in parts]
        if len(lowered) >= 2 and lowered[0] in {"provider", "service"} and lowered[1] == "url":
            return True
        return False

    def _song_duplicate_exists(db, *, user_id: int, service: str, url: str, title: str, artist: str) -> bool:
        if url:
            existing = db.scalar(
                select(Song.id).where(
                    Song.user_id == user_id,
                    Song.service == service,
                    Song.url == url,
                ).limit(1)
            )
            if existing is not None:
                return True

        existing = db.scalar(
            select(Song.id).where(
                Song.user_id == user_id,
                Song.service == service,
                Song.title == title,
                Song.artist == artist,
            ).limit(1)
        )
        return existing is not None


    @bp.get("/")
    def home() -> Response:
        return redirect(url_for("web.join"))

    @bp.get("/join")
    def join() -> str:
        code = request.args.get("code", "").strip()
        with runtime_state.db.session_scope() as db:
            ensure_default_settings(db)
            users = list_users(db)
            running = active_session(db)
            code_valid = bool(running and code and running.house_code == code)
            return render_template(
                "join.html",
                users=users,
                code=code,
                code_valid=code_valid,
                csrf_token=ensure_csrf(),
            )

    @bp.get("/kiosk")
    def kiosk() -> str:
        """Simple kiosk mode entry: choose a display name and join the active session without a house code."""
        with runtime_state.db.session_scope() as db:
            ensure_default_settings(db)
            running = active_session(db)
            if not running:
                flash("No active session available for kiosk mode.", "error")
                return redirect(url_for("web.join"))
            return render_template("kiosk.html", csrf_token=ensure_csrf())

    @bp.post("/kiosk")
    def kiosk_submit() -> Response:
        verify_csrf()
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("web.kiosk"))
        with runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record:
                flash("No active session for kiosk.", "error")
                return redirect(url_for("web.join"))
            try:
                user = create_or_get_user(db, name)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("web.kiosk"))
            flask_session["user_id"] = user.id
            flask_session["session_id"] = record.id
            flask_session["house_code"] = record.house_code
            return redirect(url_for("web.user"))

    @bp.post("/join")
    def join_submit() -> Response:
        verify_csrf()
        code = request.form.get("code", "").strip()
        name = request.form.get("name", "").strip()
        existing_name = request.form.get("existing_name", "").strip()
        chosen_name = existing_name or name
        with runtime_state.db.session_scope() as db:
            record = validate_house_code(db, code)
            if not record:
                flash("Invalid or expired house code.", "error")
                return redirect(url_for("web.join"))
            try:
                user = create_or_get_user(db, chosen_name)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("web.join", code=code))
            flask_session["user_id"] = user.id
            flask_session["session_id"] = record.id
            flask_session["house_code"] = record.house_code
            return redirect(url_for("web.user"))

    @bp.get("/user")
    def user() -> str:
        user_id, record = require_guest_session()
        with runtime_state.db.session_scope() as db:
            user_rec = db.get(User, user_id)
            if not user_rec:
                abort(404, "User not found.")
            qm = QueueManager(db)
            rotation = get_setting(db, "singer_rotation_on") == "1"
            now_playing = qm.now_playing(record.id)
            ordered_up_next = qm.ordered_up_next(record.id, rotation)
            songs = list_user_songs(db, user_id)
            queued_song_ids = set(
                db.scalars(
                    select(QueueItem.song_id).where(
                        QueueItem.session_id == record.id,
                        QueueItem.status.in_([WAITING, NOW_PLAYING]),
                    )
                )
            )
            return render_template(
                "user.html",
                user=user_rec,
                songs=songs,
                queued_song_ids=queued_song_ids,
                house_code=record.house_code,
                csrf_token=ensure_csrf(),
                queue_notification_state=user_notification_state(
                    user_rec.display_name,
                    now_playing,
                    ordered_up_next,
                ),
            )

    @bp.post("/user/rename")
    def rename_user_route() -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        try:
            new_name = validate_display_name(request.form.get("display_name", ""))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("web.user"))

        normalized = normalize_user_name(new_name)
        with runtime_state.db.session_scope() as db:
            user = db.get(User, user_id)
            if not user:
                abort(404, "User not found.")
            conflict = db.scalar(
                select(User).where(User.normalized_name == normalized, User.id != user_id)
            )
            if conflict:
                flash("That name is already in use.", "error")
                return redirect(url_for("web.user"))
            user.display_name = new_name
            user.normalized_name = normalized

        flash("Singer name updated.", "success")
        return redirect(url_for("web.user"))

    @bp.post("/user/delete")
    def delete_user_route() -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        house_code = str(flask_session.get("house_code", "")).strip()
        with runtime_state.db.session_scope() as db:
            user = db.get(User, user_id)
            if not user:
                abort(404, "User not found.")
            db.execute(delete(QueueItem).where(QueueItem.user_id == user.id))
            db.execute(delete(QueueItem).where(QueueItem.song_id.in_(select(Song.id).where(Song.user_id == user.id))))
            db.execute(delete(Song).where(Song.user_id == user.id))
            db.delete(user)

        flask_session.pop("user_id", None)
        flask_session.pop("session_id", None)
        flask_session.pop("house_code", None)
        flash("Singer profile removed.", "success")
        return redirect(url_for("web.join", code=house_code))

    @bp.post("/song/add")
    def add_song() -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        service = request.form.get("service", "").strip()
        try:
            title = validate_song_title(request.form.get("title", ""))
            artist = validate_artist_name(request.form.get("artist", ""))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("web.user"))
        with runtime_state.db.session_scope() as db:
            kwargs: dict[str, Any] = {
                "user_id": user_id,
                "title": title,
                "artist": artist,
                "service": service,
            }
            if service in {"youtube", "apple_music", "spotify"}:
                kwargs["url"] = request.form.get("url", "").strip()
            if service == "traditional":
                lib_id = request.form.get("karaoke_library_id", "").strip()
                kwargs["karaoke_library_id"] = int(lib_id) if lib_id.isdigit() else None
            try:
                create_song(db, **kwargs)
            except ValueError as exc:
                flash(str(exc), "error")
                return redirect(url_for("web.user"))
        flash("Song saved.", "success")
        return redirect(url_for("web.user"))

    @bp.post("/song/bulk-add")
    def bulk_add_songs() -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        default_service = request.form.get("default_service", "youtube").strip().lower()
        if default_service not in {"youtube", "apple_music", "spotify"}:
            default_service = "youtube"
        raw_lines = request.form.get("bulk_lines", "")
        lines = [line for line in raw_lines.splitlines() if line.strip()]
        if not lines:
            flash("Paste at least one line in bulk add.", "error")
            return redirect(url_for("web.user"))
        if len(lines) > 200:
            flash("Bulk add limit is 200 lines per submit.", "error")
            return redirect(url_for("web.user"))

        created = 0
        failed: list[str] = []
        seen_links: set[tuple[str, str]] = set()
        with runtime_state.db.session_scope() as db:
            for idx, line in enumerate(lines, start=1):
                parts = _split_bulk_song_line(line)
                if _is_bulk_header_row(parts):
                    continue

                service = ""
                url = ""
                artist = ""
                title = ""

                if len(parts) >= 4 and parts[0].lower() in {"youtube", "apple_music", "spotify"}:
                    service = parts[0].lower()
                    url = parts[1]
                    artist = parts[2]
                    title = parts[3]
                elif len(parts) >= 3:
                    url = parts[0]
                    artist = parts[1]
                    title = parts[2]
                    service = _infer_streaming_service(url) or default_service
                elif len(parts) == 2:
                    url = parts[0]
                    title = parts[1]
                    service = _infer_streaming_service(url) or default_service
                elif len(parts) == 1:
                    url = parts[0]
                    service = _infer_streaming_service(url) or default_service
                else:
                    failed.append(f"Line {idx}: expected at least a URL")
                    continue

                if service not in {"youtube", "apple_music", "spotify"}:
                    failed.append(f"Line {idx}: unsupported URL/service")
                    continue

                url = url.strip()
                if not url:
                    failed.append(f"Line {idx}: URL is required")
                    continue
                if not _is_valid_streaming_url(service, url):
                    failed.append(f"Line {idx}: invalid {service} URL")
                    continue

                dedupe_key = (service, url.casefold())
                if dedupe_key in seen_links:
                    failed.append(f"Line {idx}: duplicate URL in request")
                    continue
                seen_links.add(dedupe_key)

                if not title or not artist:
                    resolved = _resolve_metadata_for_service(service, url)
                    if resolved:
                        resolved_title, resolved_artist = resolved
                        if not title:
                            title = resolved_title
                        if not artist:
                            artist = resolved_artist

                if not title or not artist:
                    failed.append(f"Line {idx}: could not auto-resolve title/artist")
                    continue

                if _song_duplicate_exists(
                    db,
                    user_id=user_id,
                    service=service,
                    url=url,
                    title=title,
                    artist=artist,
                ):
                    failed.append(f"Line {idx}: duplicate song already saved")
                    continue

                try:
                    create_song(
                        db,
                        user_id=user_id,
                        title=title,
                        artist=artist,
                        service=service,
                        url=url,
                    )
                    created += 1
                except ValueError as exc:
                    failed.append(f"Line {idx}: {exc}")

        if created:
            flash(f"Added {created} songs from bulk input.", "success")
        if failed:
            preview = "; ".join(failed[:5])
            if len(failed) > 5:
                preview += f"; and {len(failed) - 5} more"
            flash(preview, "error")
        return redirect(url_for("web.user"))

    @bp.post("/song/delete/<int:song_id>")
    def delete_song_route(song_id: int) -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        try:
            with runtime_state.db.session_scope() as db:
                song = db.get(Song, song_id)
                if not song or song.user_id != user_id:
                    abort(404, "Song not found.")
                # Remove queue references first to satisfy FK constraints.
                db.execute(delete(QueueItem).where(QueueItem.song_id == song.id))
                db.delete(song)
            flash("Song deleted.", "success")
        except IntegrityError:
            logger.exception("Failed to delete song %s due to integrity constraint.", song_id)
            flash("Could not delete song right now. Please try again.", "error")
        return redirect(url_for("web.user"))

    @bp.post("/song/delete-bulk")
    def delete_song_bulk_route() -> Response:
        verify_csrf()
        user_id, _ = require_guest_session()
        raw_ids = request.form.getlist("song_ids")
        song_ids = [int(raw_id) for raw_id in raw_ids if raw_id.isdigit()]
        if not song_ids:
            flash("Select at least one song to delete.", "error")
            return redirect(url_for("web.user"))

        with runtime_state.db.session_scope() as db:
            allowed_song_ids = list(
                db.scalars(
                    select(Song.id).where(
                        Song.user_id == user_id,
                        Song.id.in_(song_ids),
                    )
                )
            )
            if not allowed_song_ids:
                flash("No matching songs found to delete.", "error")
                return redirect(url_for("web.user"))

            db.execute(delete(QueueItem).where(QueueItem.song_id.in_(allowed_song_ids)))
            db.execute(delete(Song).where(Song.id.in_(allowed_song_ids), Song.user_id == user_id))

        flash(f"Deleted {len(allowed_song_ids)} song(s).", "success")
        return redirect(url_for("web.user"))

    @bp.get("/song/search")
    def song_search() -> Response:
        user_id, _ = require_guest_session()
        _ = user_id
        query = request.args.get("q", "")
        service = request.args.get("service", "")
        with runtime_state.db.session_scope() as db:
            limit_raw = request.args.get("limit", "20").strip()
            try:
                limit = max(1, min(120, int(limit_raw)))
            except ValueError:
                limit = 20
            if service == "traditional":
                _ensure_traditional_library_index(db)
                results = search_library_traditional(db, query, limit=limit)
                if not results:
                    if _ensure_traditional_library_index(db):
                        results = search_library_traditional(db, query, limit=limit)
            else:
                results = search_library(db, query, limit=limit)
            return jsonify(
                [
                    {
                        "id": row.id,
                        "title": row.title,
                        "artist": row.artist,
                        "display_name": row.display_name,
                        "extension": row.extension,
                    }
                    for row in results
                ]
            )

    @bp.get("/song/link-metadata")
    def song_link_metadata() -> Response:
        user_id, _ = require_guest_session()
        _ = user_id
        service = request.args.get("service", "").strip()
        url = request.args.get("url", "").strip()
        if service not in {"youtube", "apple_music", "spotify"}:
            return jsonify({"ok": False, "message": "Unsupported service."}), 400
        if not url:
            return jsonify({"ok": False, "message": "Missing URL."}), 400

        try:
            resolved = _resolve_metadata_for_service(service, url)

            if not resolved:
                return jsonify({"ok": False, "title": "", "artist": ""})
            title, artist = resolved
            return jsonify({"ok": True, "title": title, "artist": artist})
        except Exception as exc:
            logger.exception("Failed resolving link metadata: %s", exc)
            return jsonify({"ok": False, "message": "Unable to resolve link metadata."}), 400

    @bp.get("/player")
    def player() -> str:
        record = require_admin()
        song_id = request.args.get("song_id", "").strip()
        player_song = None
        with runtime_state.db.session_scope() as db:
            enabled = get_playback_mode(db) == "built_in"
            if song_id.isdigit():
                entry = db.get(KaraokeLibrary, int(song_id))
                if entry:
                    primary_suffix = Path(entry.primary_file).suffix.lower()
                    is_video_entry = primary_suffix in VIDEO_EXTENSIONS or (entry.extension or "").lower() in VIDEO_EXTENSIONS
                    player_song = {
                        "id": entry.id,
                        "title": entry.title,
                        "artist": entry.artist,
                        "display_name": entry.display_name,
                        "extension": entry.extension,
                        "media_kind": "video" if is_video_entry else "cdg",
                    }
                    if is_video_entry:
                        player_song["video_url"] = url_for(
                            "web.player_media",
                            library_id=entry.id,
                            kind="video",
                            token=record.admin_token,
                        )
                    else:
                        player_song["audio_url"] = url_for(
                            "web.player_media",
                            library_id=entry.id,
                            kind="audio",
                            token=record.admin_token,
                        )
                        player_song["cdg_url"] = url_for(
                            "web.player_media",
                            library_id=entry.id,
                            kind="cdg",
                            token=record.admin_token,
                        )
        return render_template(
            "player.html",
            token=record.admin_token,
            csrf_token=ensure_csrf(),
            enabled=enabled,
            song_id=int(song_id) if song_id.isdigit() else None,
            player_song=player_song,
            asset_version=secrets.token_hex(8),
        )

    @bp.get("/player/catalog")
    def player_catalog() -> Response:
        _ = require_admin()
        with runtime_state.db.session_scope() as db:
            rows = list(list_active_library(db))
            return jsonify(
                [
                    {
                        "id": row.id,
                        "title": row.title,
                        "artist": row.artist,
                        "display_name": row.display_name,
                        "audio_available": bool(row.audio_file),
                        "cdg_available": bool(row.cdg_file),
                    }
                    for row in rows
                ]
            )

    @bp.get("/player/media/<int:library_id>/<kind>")
    def player_media(library_id: int, kind: str) -> Response:
        _ = require_admin()
        if kind not in {"audio", "cdg", "video"}:
            abort(404)
        with runtime_state.db.session_scope() as db:
            entry = db.get(KaraokeLibrary, library_id)
            if not entry:
                abort(404, "Library item not found.")
            root = _player_media_root(db)
            try:
                media_path = _resolve_player_media_path(entry, kind, root)
            except FileNotFoundError:
                abort(404, f"Matching {kind.upper()} file not found.")
            if kind == "audio":
                mimetype = "audio/mpeg"
            elif kind == "video":
                guessed, _ = mimetypes.guess_type(str(media_path))
                mimetype = guessed or "video/mp4"
            else:
                mimetype = "application/octet-stream"
            return send_file(media_path, mimetype=mimetype, as_attachment=False, conditional=True)

    @bp.post("/queue/add/<int:song_id>")
    def queue_add(song_id: int) -> Response:
        verify_csrf()
        user_id, record = require_guest_session()
        with runtime_state.db.session_scope() as db:
            qm = QueueManager(db)
            song = db.get(Song, song_id)
            if not song or song.user_id != user_id:
                abort(404, "Song not found.")

            removed = qm.remove_waiting_song(record.id, user_id, song_id)
            if removed:
                message = "Removed from queue."
            else:
                try:
                    qm.add_song(record.id, user_id, song_id)
                except ValueError as exc:
                    flash(str(exc), "error")
                    return redirect(url_for("web.user"))
                message = "Added to queue."
        emit_queue_update()
        flash(message, "success")
        return redirect(url_for("web.user"))

    @bp.get("/admin")
    def admin() -> str:
        record = require_admin()
        with runtime_state.db.session_scope() as db:
            qm = QueueManager(db)
            settings = {
                "rotation": get_setting(db, "singer_rotation_on") == "1",
            }
            now_playing = qm.now_playing(record.id)
            waiting = qm.ordered_up_next(record.id, settings["rotation"])
            users = list_users(db)
            return render_template(
                "admin.html",
                now_playing=now_playing,
                waiting=waiting,
                users=users,
                token=record.admin_token,
                ticker_token=record.ticker_token,
                settings=settings,
                csrf_token=ensure_csrf(),
            )

    @bp.get("/ticker")
    def ticker() -> str:
        record = require_ticker()
        return render_template("ticker.html", token=record.ticker_token)

    @bp.get("/api/ticker")
    def api_ticker() -> Response:
        _ = require_ticker()
        return jsonify(queue_snapshot())

    @bp.get("/api/queue")
    def api_queue() -> Response:
        record = require_admin()
        _ = record
        return jsonify(queue_snapshot())

    @bp.post("/admin/user/rename")
    def admin_user_rename() -> Response:
        verify_csrf()
        record = require_admin()
        user_id_raw = request.form.get("user_id", "").strip()
        display_name_raw = request.form.get("display_name", "")
        if not user_id_raw.isdigit():
            flash("Select a valid singer.", "error")
            return redirect(url_for("web.admin", token=record.admin_token))
        try:
            display_name = validate_display_name(display_name_raw)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("web.admin", token=record.admin_token))

        user_id = int(user_id_raw)
        normalized = normalize_user_name(display_name)
        with runtime_state.db.session_scope() as db:
            user = db.get(User, user_id)
            if not user:
                flash("Singer not found.", "error")
                return redirect(url_for("web.admin", token=record.admin_token))
            conflict = db.scalar(
                select(User).where(User.normalized_name == normalized, User.id != user_id)
            )
            if conflict:
                flash("That singer name is already in use.", "error")
                return redirect(url_for("web.admin", token=record.admin_token))
            user.display_name = display_name
            user.normalized_name = normalized

        flash("Singer updated.", "success")
        return redirect(url_for("web.admin", token=record.admin_token))

    @bp.post("/admin/user/delete")
    def admin_user_delete() -> Response:
        verify_csrf()
        record = require_admin()
        user_id_raw = request.form.get("user_id", "").strip()
        if not user_id_raw.isdigit():
            flash("Select a valid singer.", "error")
            return redirect(url_for("web.admin", token=record.admin_token))
        user_id = int(user_id_raw)

        with runtime_state.db.session_scope() as db:
            user = db.get(User, user_id)
            if not user:
                flash("Singer not found.", "error")
                return redirect(url_for("web.admin", token=record.admin_token))
            db.execute(delete(QueueItem).where(QueueItem.user_id == user.id))
            db.execute(delete(QueueItem).where(QueueItem.song_id.in_(select(Song.id).where(Song.user_id == user.id))))
            db.execute(delete(Song).where(Song.user_id == user.id))
            db.delete(user)

        emit_queue_update()
        flash("Singer removed.", "success")
        return redirect(url_for("web.admin", token=record.admin_token))

    @bp.post("/admin/user/bulk-add")
    def admin_user_bulk_add() -> Response:
        verify_csrf()
        record = require_admin()
        user_id_raw = request.form.get("user_id", "").strip()
        default_service = request.form.get("default_service", "youtube").strip().lower()
        if default_service not in {"youtube", "apple_music", "spotify"}:
            default_service = "youtube"
        raw_lines = request.form.get("bulk_lines", "")
        if not user_id_raw.isdigit():
            flash("Select a valid singer.", "error")
            return redirect(url_for("web.admin", token=record.admin_token))

        lines = [line for line in raw_lines.splitlines() if line.strip()]
        if not lines:
            flash("Paste at least one line in bulk add.", "error")
            return redirect(url_for("web.admin", token=record.admin_token))
        if len(lines) > 200:
            flash("Bulk add limit is 200 lines per submit.", "error")
            return redirect(url_for("web.admin", token=record.admin_token))

        user_id = int(user_id_raw)
        created = 0
        failed: list[str] = []
        seen_links: set[tuple[str, str]] = set()
        with runtime_state.db.session_scope() as db:
            if not db.get(User, user_id):
                flash("Singer not found.", "error")
                return redirect(url_for("web.admin", token=record.admin_token))

            for idx, line in enumerate(lines, start=1):
                parts = _split_bulk_song_line(line)
                if _is_bulk_header_row(parts):
                    continue

                service = ""
                url = ""
                artist = ""
                title = ""

                if len(parts) >= 4 and parts[0].lower() in {"youtube", "apple_music", "spotify"}:
                    service = parts[0].lower()
                    url = parts[1]
                    artist = parts[2]
                    title = parts[3]
                elif len(parts) >= 3:
                    url = parts[0]
                    artist = parts[1]
                    title = parts[2]
                    service = _infer_streaming_service(url) or default_service
                elif len(parts) == 2:
                    url = parts[0]
                    title = parts[1]
                    service = _infer_streaming_service(url) or default_service
                elif len(parts) == 1:
                    url = parts[0]
                    service = _infer_streaming_service(url) or default_service
                else:
                    failed.append(f"Line {idx}: expected at least a URL")
                    continue

                if service not in {"youtube", "apple_music", "spotify"}:
                    failed.append(f"Line {idx}: unsupported URL/service")
                    continue

                url = url.strip()
                if not url:
                    failed.append(f"Line {idx}: URL is required")
                    continue
                if not _is_valid_streaming_url(service, url):
                    failed.append(f"Line {idx}: invalid {service} URL")
                    continue

                dedupe_key = (service, url.casefold())
                if dedupe_key in seen_links:
                    failed.append(f"Line {idx}: duplicate URL in request")
                    continue
                seen_links.add(dedupe_key)

                if not title or not artist:
                    resolved = _resolve_metadata_for_service(service, url)
                    if resolved:
                        resolved_title, resolved_artist = resolved
                        if not title:
                            title = resolved_title
                        if not artist:
                            artist = resolved_artist

                if not title or not artist:
                    failed.append(f"Line {idx}: could not auto-resolve title/artist")
                    continue

                if _song_duplicate_exists(
                    db,
                    user_id=user_id,
                    service=service,
                    url=url,
                    title=title,
                    artist=artist,
                ):
                    failed.append(f"Line {idx}: duplicate song already saved")
                    continue

                try:
                    create_song(
                        db,
                        user_id=user_id,
                        title=title,
                        artist=artist,
                        service=service,
                        url=url,
                    )
                    created += 1
                except ValueError as exc:
                    failed.append(f"Line {idx}: {exc}")

        if created:
            flash(f"Added {created} songs to singer list.", "success")
        if failed:
            preview = "; ".join(failed[:5])
            if len(failed) > 5:
                preview += f"; and {len(failed) - 5} more"
            flash(preview, "error")
        return redirect(url_for("web.admin", token=record.admin_token))

    @bp.post("/admin/action")
    def admin_action() -> Response:
        verify_csrf()
        admin_record = require_admin()
        action = request.form.get("action", "")
        queue_item_id = request.form.get("queue_item_id", "").strip()
        with runtime_state.db.session_scope() as db:
            record = active_session(db)
            if not record:
                return jsonify({"ok": False, "message": "No active session."}), 400
            qm = QueueManager(db)
            rotation = get_setting(db, "singer_rotation_on") == "1"
            playback_mode = get_playback_mode(db)
            external_app_path = get_external_application_path(db)
            if action == "next":
                qm.next_song(record.id, rotation)
            elif action == "clear":
                qm.clear_queue(record.id)
            else:
                if not queue_item_id.isdigit():
                    return jsonify({"ok": False, "message": "Missing queue item id"}), 400
                item_id = int(queue_item_id)
                if action == "play":
                    item = db.get(QueueItem, item_id)
                    if not item:
                        return jsonify({"ok": False, "message": "Queue item not found"}), 404
                    song = item.song
                    if not song:
                        return jsonify({"ok": False, "message": "Missing song"}), 404
                    from karaoke.launcher import launch_traditional_song, launch_url

                    try:
                        if song.service == "traditional":
                            library_entry = song.karaoke_library
                            if not library_entry:
                                _ensure_traditional_library_index(db)
                                library_entry = db.get(KaraokeLibrary, song.karaoke_library_id) if song.karaoke_library_id else None
                            if not library_entry:
                                return jsonify({"ok": False, "message": "Missing indexed file"}), 404

                            if playback_mode == "built_in":
                                player_url = url_for(
                                    "web.player",
                                    token=admin_record.admin_token,
                                    song_id=library_entry.id,
                                    _external=True,
                                )
                                launch_url(player_url)
                            elif playback_mode == "external_application":
                                if not external_app_path:
                                    return jsonify({"ok": False, "message": "External application path is not configured."}), 400
                                launch_traditional_song(
                                    library_entry.primary_file,
                                    cdg_file=library_entry.cdg_file,
                                    external_application_path=external_app_path,
                                )
                            else:
                                launch_traditional_song(
                                    library_entry.primary_file,
                                    cdg_file=library_entry.cdg_file,
                                )
                        else:
                            if not song.url:
                                return jsonify({"ok": False, "message": "Missing URL"}), 404
                            launch_url(song.url)

                        qm.mark_now_playing(item_id)
                    except Exception as exc:
                        logger.exception("Failed to launch song: %s", exc)
                        return jsonify({"ok": False, "message": "Failed to launch selected item."}), 400
                elif action == "complete":
                    qm.mark_status(item_id, COMPLETED)
                elif action == "skip":
                    qm.mark_status(item_id, SKIPPED)
                elif action == "remove":
                    qm.remove_item(item_id)
                elif action == "up":
                    qm.move_item(item_id, "up", rotation)
                elif action == "down":
                    qm.move_item(item_id, "down", rotation)
                else:
                    return jsonify({"ok": False, "message": "Unsupported action"}), 400
        emit_queue_update()
        return jsonify({"ok": True})

    @bp.get("/settings")
    def settings_get() -> str:
        record = require_admin()
        with runtime_state.db.session_scope() as db:
            values = {
                key: get_setting(db, key)
                for key in (
                    "karaoke_folder",
                    "external_application_path",
                    "traditional_karaoke_server_url",
                    "web_server_port",
                    "ticker_upcoming_count",
                    "singer_rotation_on",
                    "house_name",
                )
            }
            values["playback_mode"] = get_playback_mode(db)
        return render_template("settings.html", values=values, token=record.admin_token, csrf_token=ensure_csrf())

    @bp.post("/settings")
    def settings_post() -> Response:
        verify_csrf()
        record = require_admin()
        settings_action = request.form.get("settings_action", "save").strip().lower()
        with runtime_state.db.session_scope() as db:
            set_setting(db, "karaoke_folder", request.form.get("karaoke_folder", "").strip())
            external_path = set_external_application_path(db, request.form.get("external_application_path", "").strip())
            playback_mode = set_playback_mode(db, request.form.get("playback_mode", "built_in"))
            traditional_server_url = request.form.get("traditional_karaoke_server_url", "").strip()
            if traditional_server_url and not is_valid_traditional_karaoke_server_url(traditional_server_url):
                flash("Traditional Karaoke Server URL must be a valid http(s) base URL.", "error")
                return redirect(url_for("web.settings_get", token=record.admin_token))
            set_setting(db, "traditional_karaoke_server_url", traditional_server_url)
            port = request.form.get("web_server_port", "8080").strip()
            if not port.isdigit() or not (1 <= int(port) <= 65535):
                flash("Port must be 1-65535", "error")
                return redirect(url_for("web.settings_get", token=record.admin_token))
            set_setting(db, "web_server_port", port)
            upcoming = request.form.get("ticker_upcoming_count", "5").strip()
            if not upcoming.isdigit() or not (1 <= int(upcoming) <= 20):
                flash("Upcoming singers must be 1-20", "error")
                return redirect(url_for("web.settings_get", token=record.admin_token))
            set_setting(db, "ticker_upcoming_count", upcoming)
            rotation = "1" if request.form.get("singer_rotation_on") == "on" else "0"
            set_setting(db, "singer_rotation_on", rotation)
            set_setting(db, "house_name", request.form.get("house_name", "Karaoke Ticker").strip()[:100])

            if playback_mode == "external_application":
                is_valid_path, error_message = _validate_external_application_path(external_path)
                if not is_valid_path:
                    flash(error_message, "error")
                    return redirect(url_for("web.settings_get", token=record.admin_token))

            if settings_action == "test_external":
                is_valid_path, error_message = _validate_external_application_path(external_path)
                if is_valid_path:
                    flash("External application path validation passed.", "success")
                else:
                    flash(error_message, "error")
                return redirect(url_for("web.settings_get", token=record.admin_token))

        flash("Settings saved.", "success")
        emit_queue_update()
        return redirect(url_for("web.settings_get", token=record.admin_token))

    @bp.post("/admin/refresh-library")
    def refresh_library() -> Response:
        verify_csrf()
        _ = require_admin()
        with runtime_state.db.session_scope() as db:
            folder = get_setting(db, "karaoke_folder")
            if not folder:
                return jsonify({"ok": False, "message": "Set karaoke folder first."}), 400
            count = build_index(db, folder)
        return jsonify({"ok": True, "count": count})

    @bp.get("/api/users")
    def api_users() -> Response:
        with runtime_state.db.session_scope() as db:
            users = list_users(db)
        return jsonify([{"name": user.display_name} for user in users])

    app.register_blueprint(bp)
