"""Playback job mapping tests."""

from __future__ import annotations

from dataclasses import dataclass

from playback.playback_job import PlaybackJob
from playback.playback_state import PlaybackState


@dataclass
class FakeLibrary:
    primary_file: str


@dataclass
class FakeSong:
    title: str
    artist: str
    service: str
    url: str | None = None
    karaoke_library: FakeLibrary | None = None


@dataclass
class FakeUser:
    display_name: str


@dataclass
class FakeQueueItem:
    id: int
    song: FakeSong
    user: FakeUser


def test_playback_job_maps_traditional_queue_item() -> None:
    item = FakeQueueItem(
        id=10,
        user=FakeUser(display_name="Dale"),
        song=FakeSong(
            title="My Way",
            artist="Frank Sinatra",
            service="traditional",
            karaoke_library=FakeLibrary(primary_file=r"D:\\Karaoke\\MyWay.cdg"),
        ),
    )

    job = PlaybackJob.from_queue_item(item, generation_id=3)

    assert job.queue_item_id == 10
    assert job.singer == "Dale"
    assert job.service == "kanto"
    assert job.path_or_url.endswith("MyWay.cdg")
    assert job.generation_id == 3


def test_playback_job_lifecycle_transitions() -> None:
    job = PlaybackJob(
        queue_item_id=11,
        singer="Missy",
        title="No Rain",
        artist="Blind Melon",
        service="apple_music",
        path_or_url="https://music.apple.com/us/song/id123",
        expected_player="apple_music",
    )

    job.begin()
    assert job.status == PlaybackState.PREPARING
    assert job.start_time is not None

    job.fail("selection mismatch")
    assert job.status == PlaybackState.FAILED
    assert "selection mismatch" in job.error
    assert job.end_time is not None
