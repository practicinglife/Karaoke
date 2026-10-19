"""Grouped traditional-karaoke search: artists, then their songs, then each song's versions.

Typing "dolly" lists the matching artists (Dolly Parton: 84 songs) and the matching song
titles ("Hello, Dolly!"). An artist opens to their songs; a song opens to its versions
(Karaoke and Sing Along videos made by karaoke-maker, other videos, CD+G discs by brand).
Each song also has a best version for one-tap adding.

The library index is read once into memory and re-read when the library changes, so each
keystroke only filters a list. File names are never changed; the cleaned names here are
only for grouping and display.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import KaraokeLibrary
from .song_tags import DUET, NOT_A_DUET, SEARCH_WORDS, split_display, split_query
from .utils import normalize_text

MAX_ARTISTS = 40
MAX_SONGS = 60
MIN_QUERY = 2

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".wmv", ".m4v"}
# Disc codes and track numbers in front of "Artist - Title": "CBD-105262", "DMGCRIM602-19", "06".
DISC_CODE = re.compile(r"^(?:([A-Z]{1,10})[\s-]*\d[\w-]*|\d{1,3})$", re.I)
BRAND = re.compile(r"\[([^\]]+)\]\s*$")
BRACKETS = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
# Extra markers karaoke makers put in names: kept on the version label, dropped from the song.
MARKERS = re.compile(r"\((mpx|w ?bgv|wbgv|no ?bgv|bgv|duet|mf duet|fm duet|explicit|clean|radio version)\)", re.I)
# Credits joining a featured artist: always split, the first name leads.
FEATURING = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+", re.I)
# Credits joining two singers: split only for songs labelled duets (not "Brooks & Dunn").
TOGETHER = re.compile(r"\s*(?:&|\+|,|\band\b|\bduet with\b|\bwith\b)\s*", re.I)

KT_KARAOKE, KT_SING_ALONG = "kt karaoke", "kt sing along"
# Best version first: your vocals-removed videos, other videos, CD+G, MP3, then Sing Along
# (it has the vocals, so it's never the default).
RANK_KT_KARAOKE, RANK_VIDEO, RANK_CDG, RANK_MP3, RANK_SING_ALONG = 0, 10, 20, 25, 30


@dataclass
class Entry:
    """One library file, cleaned up for grouping."""

    id: int
    artist: str  # the whole credit, e.g. "Kenny Rogers & Dolly Parton"
    title: str  # the song, without brand or markers
    singers: list[tuple[str, str]]  # (name, key) of each singer the song is listed under
    credit_key: str
    title_key: str
    label: str  # "CD+G · SC Karaoke", "Karaoke (vocals removed)"
    rank: int
    tags: list[str] = field(default_factory=list)
    blob: str = ""  # artist + title + label words, for matching

    @property
    def song_key(self) -> str:
        # Same singers in any order: "Kenny Rogers & Dolly Parton" = "Dolly Parton & Kenny Rogers".
        return "+".join(sorted(key for _, key in self.singers)) + "|" + self.title_key


def _key(name: str) -> str:
    key = normalize_text(name)
    return key[4:] if key.startswith("the ") else key


def clean_artist(artist: str) -> str:
    artist = re.sub(r"\s+", " ", BRACKETS.sub("", artist or "")).strip(" -,")
    # "Kramer, Jana" -> "Jana Kramer" (one comma, short names, no other singers).
    if artist.count(",") == 1 and not re.search(r"&|\band\b|\bwith\b", artist, re.I):
        last, first = (part.strip() for part in artist.split(","))
        if 1 <= len(first.split()) <= 3 and 1 <= len(last.split()) <= 3:
            artist = f"{first} {last}"
    return artist


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", BRACKETS.sub("", title or "")).strip(" -") or (title or "").strip()


def singers_of(credit: str, is_duet: bool) -> list[str]:
    lead, *featured = FEATURING.split(credit)
    names = [lead] + featured
    if is_duet and not NOT_A_DUET.search(lead):
        names = [part for name in names for part in TOGETHER.split(name)]
    seen, result = set(), []
    for name in (n.strip() for n in names):
        if name and _key(name) and _key(name) not in seen:
            seen.add(_key(name))
            result.append(name)
    return result or [credit]


def version_of(artist_field: str, title_field: str, extension: str) -> tuple[str, int]:
    """(label, rank) for one file: what kind of version it is."""
    lowered = (title_field or "").lower()
    if KT_KARAOKE in lowered:
        return "Karaoke (vocals removed)", RANK_KT_KARAOKE
    if KT_SING_ALONG in lowered:
        return "Sing Along (with vocals)", RANK_SING_ALONG
    extension = (extension or "").lower()
    if extension in VIDEO_EXTENSIONS:
        kind, rank = "Video", RANK_VIDEO
    elif "cdg" in extension or extension == ".zip":
        kind, rank = "CD+G", RANK_CDG
    else:
        kind, rank = "MP3", RANK_MP3
    details = []
    brand = BRAND.search(title_field or "")
    code = DISC_CODE.match((artist_field or "").strip())
    if brand:
        details.append(brand.group(1).strip())
    elif code and code.group(1):
        details.append(code.group(1).upper())
    details += [m.group(1).upper().replace(" ", "") for m in MARKERS.finditer(title_field or "")]
    return " · ".join([kind] + details), rank


def entry_from_row(row_id: int, artist_field: str, title_field: str, display_name: str,
                   extension: str, tags: str) -> Entry:
    artist_part, song_part = split_display(artist_field, title_field, display_name)
    if DISC_CODE.match((artist_part or "").strip()) and " - " in song_part:
        artist_part, song_part = song_part.split(" - ", 1)
    tag_list = [t for t in (tags or "").split(",") if t]
    artist = clean_artist(artist_part) or "Unknown artist"
    title = clean_title(song_part)
    singers = [(name, _key(name)) for name in singers_of(artist, DUET in tag_list)]
    label, rank = version_of(artist_field, title_field or display_name, extension)
    words = " ".join(word for tag in tag_list for word in SEARCH_WORDS.get(tag, ()))
    return Entry(
        id=row_id, artist=artist, title=title, singers=singers, credit_key=_key(artist),
        title_key=normalize_text(title), label=label, rank=rank, tags=tag_list,
        blob=" ".join(filter(None, [_key(artist), normalize_text(title), words])),
    )


class GroupedLibrary:
    """The library index in memory, grouped for searching. Re-read when the library changes."""

    def __init__(self) -> None:
        self._entries: list[Entry] = []
        self._signature: tuple | None = None
        self._lock = threading.Lock()

    def entries(self, session: Session) -> list[Entry]:
        active = KaraokeLibrary.active == True  # noqa: E712
        signature = tuple(session.execute(
            select(func.count(KaraokeLibrary.id), func.max(KaraokeLibrary.id), func.total(KaraokeLibrary.id))
            .where(active)).one())
        with self._lock:
            if signature != self._signature:
                rows = session.execute(select(
                    KaraokeLibrary.id, KaraokeLibrary.artist, KaraokeLibrary.title, KaraokeLibrary.display_name,
                    KaraokeLibrary.extension, KaraokeLibrary.tags).where(active)).all()
                self._entries = [entry_from_row(*row) for row in rows]
                self._signature = signature
            return self._entries

    def search(self, session: Session, query: str) -> dict:
        """Artists and songs matching what's typed so far."""
        normalized = normalize_text(query or "")
        wanted_tags, rest = split_query(normalized)
        if len(normalized) < MIN_QUERY:
            return {"artists": [], "songs": [], "more_artists": 0, "more_songs": 0}
        tokens = rest.split()
        pool = [e for e in self.entries(session) if all(tag in e.tags for tag in wanted_tags)]
        matched = [e for e in pool if all(token in e.blob for token in tokens)]

        # Artists: a singer whose own name contains what's typed (all of it).
        artists: dict[str, dict] = {}
        if rest:
            for entry in matched:
                names = list(entry.singers)
                if len(entry.singers) > 1:
                    names.append((entry.artist, entry.credit_key))  # "Dolly Parton & Kenny Rogers" too
                for name, key in names:
                    if rest in key:
                        group = artists.setdefault(key, {"key": key, "names": Counter(), "songs": set(), "files": 0})
                        group["names"][name] += 1
                        group["songs"].add(entry.title_key)
                        group["files"] += 1
        artist_list = sorted(artists.values(), key=lambda g: (not g["key"].startswith(rest), -len(g["songs"]), g["key"]))
        artist_out = [{"key": g["key"], "name": g["names"].most_common(1)[0][0], "songs": len(g["songs"]),
                       "files": g["files"]} for g in artist_list[:MAX_ARTISTS]]

        # Songs: the title has what's typed (or part of it, with the rest in the artist), or a
        # label search like "duets" on its own.
        def title_hit(entry: Entry) -> bool:
            if not tokens:
                return True
            if rest in entry.title_key:
                return True
            return any(token in entry.title_key for token in tokens) and len(tokens) > 1

        songs = group_songs([e for e in matched if title_hit(e)])
        songs.sort(key=lambda s: (not s["title_key"].startswith(rest), s["title"].lower(), s["artist"].lower()))
        return {"artists": artist_out, "songs": songs[:MAX_SONGS],
                "more_artists": max(0, len(artist_list) - MAX_ARTISTS), "more_songs": max(0, len(songs) - MAX_SONGS)}

    def artist_songs(self, session: Session, artist_key: str, query: str = "") -> list[dict]:
        """Every song of one artist (including duets and featured spots), A-Z, with versions."""
        wanted_tags, _ = split_query(normalize_text(query or ""))
        entries = [e for e in self.entries(session)
                   if (artist_key == e.credit_key or any(key == artist_key for _, key in e.singers))
                   and all(tag in e.tags for tag in wanted_tags)]
        songs = group_songs(entries)
        songs.sort(key=lambda s: (s["title"].lower(), s["artist"].lower()))
        return songs


def save_title(entry: Entry) -> str:
    """The title saved on the singer's list. The app's own two versions say which they are,
    so a singer can save both."""
    if entry.rank == RANK_KT_KARAOKE:
        return f"{entry.title} [Karaoke]"
    if entry.rank == RANK_SING_ALONG:
        return f"{entry.title} [Sing Along]"
    return entry.title


def group_songs(entries: list[Entry]) -> list[dict]:
    """One group per song (same credit and title), versions best first."""
    groups: dict[str, list[Entry]] = {}
    for entry in entries:
        groups.setdefault(entry.song_key, []).append(entry)
    result = []
    for versions in groups.values():
        versions.sort(key=lambda e: (e.rank, e.label, e.id))
        # Files that look the same (same kind and brand) are shown once.
        seen_labels: set[str] = set()
        versions = [e for e in versions if not (e.label in seen_labels or seen_labels.add(e.label))]
        best = versions[0]
        tags = sorted({tag for e in versions for tag in e.tags})
        result.append({
            "title": best.title, "artist": best.artist, "title_key": best.title_key, "tags": tags,
            "best_id": best.id,
            "versions": [{"id": e.id, "label": e.label, "save_title": save_title(e)} for e in versions],
        })
    return result
