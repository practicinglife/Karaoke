"""Playback job model for independent queue-driven playback work."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .playback_state import PlaybackState

if TYPE_CHECKING:
    from karaoke.models import QueueItem


SERVICE_MAP = {
    "traditional": "kanto",
    "apple_music": "apple_music",
    "youtube": "youtube_music",
}


@dataclass
class PlaybackJob:
    """Independent playback job derived from a queue item."""

    queue_item_id: int
    singer: str
    title: str
    artist: str
    service: str
    path_or_url: str
    expected_player: str
    expected_window: str = ""
    status: PlaybackState = PlaybackState.IDLE
    retry_count: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str = ""
    generation_id: int = 0

    def begin(self) -> None:
        """Mark playback job as started."""
        self.start_time = datetime.utcnow()
        self.status = PlaybackState.PREPARING

    def finish(self) -> None:
        """Mark playback job as finished."""
        self.end_time = datetime.utcnow()
        self.status = PlaybackState.FINISHED

    def fail(self, reason: str) -> None:
        """Mark playback job as failed with reason."""
        self.end_time = datetime.utcnow()
        self.error = reason
        self.status = PlaybackState.FAILED

    @classmethod
    def from_queue_item(cls, queue_item: "QueueItem", generation_id: int = 0) -> "PlaybackJob":
        """Build PlaybackJob from an existing QueueItem entity."""
        song = queue_item.song
        user = queue_item.user
        service = SERVICE_MAP.get(song.service, song.service)

        if song.service == "traditional":
            path_or_url = song.karaoke_library.primary_file if song.karaoke_library else ""
        else:
            path_or_url = song.url or ""

        return cls(
            queue_item_id=queue_item.id,
            singer=user.display_name if user else "",
            title=song.title if song else "",
            artist=song.artist if song else "",
            service=service,
            path_or_url=path_or_url,
            expected_player=service,
            generation_id=generation_id,
        )
