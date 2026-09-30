"""Playback state definitions for controller lifecycle."""

from __future__ import annotations

from enum import Enum


class PlaybackState(str, Enum):
    """State machine values for playback processing."""

    IDLE = "IDLE"
    PREPARING = "PREPARING"
    STOPPING_PREVIOUS = "STOPPING_PREVIOUS"
    LOADING = "LOADING"
    SELECTING = "SELECTING"
    READY = "READY"
    STARTING = "STARTING"
    VERIFYING_START = "VERIFYING_START"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    BUFFERING = "BUFFERING"
    STOPPING = "STOPPING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"
