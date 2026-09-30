"""Queue advancement safety tests for playback job mapping."""

from __future__ import annotations

from dataclasses import dataclass

from playback.playback_job import PlaybackJob


@dataclass
class FakeSong:
    title: str
    artist: str
    service: str
    url: str | None = None
    karaoke_library: object | None = None


@dataclass
class FakeUser:
    display_name: str


@dataclass
class FakeQueueItem:
    id: int
    song: FakeSong
    user: FakeUser


def test_queue_item_maps_to_expected_service() -> None:
    item = FakeQueueItem(
        id=99,
        user=FakeUser(display_name="Kam"),
        song=FakeSong(
            title="Blue Strips",
            artist="Jessie Murph",
            service="youtube",
            url="https://music.youtube.com/watch?v=abc",
        ),
    )

    job = PlaybackJob.from_queue_item(item, generation_id=1)

    assert job.service == "youtube_music"
    assert job.expected_player == "youtube_music"
    assert job.queue_item_id == 99
