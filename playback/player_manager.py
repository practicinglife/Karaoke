"""Persistent player lifecycle coordinator for playback jobs."""

from __future__ import annotations

import logging
from threading import RLock

from .playback_job import PlaybackJob
from .players.apple_music_player import AppleMusicPlayer
from .players.base_player import BasePlayer
from .players.kanto_player import KantoPlayer
from .players.youtube_music_player import YouTubeMusicPlayer

logger = logging.getLogger(__name__)


class PlayerManager:
    """Manage persistent player instances and service switching."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._lock = RLock()
        self._players: dict[str, BasePlayer] = {
            "kanto": KantoPlayer(self._config),
            "apple_music": AppleMusicPlayer(self._config),
            "youtube_music": YouTubeMusicPlayer(self._config),
        }
        self._active_service: str | None = None
        self._active_job: PlaybackJob | None = None

    def initialize_players(self) -> None:
        """Initialize passive discovery for all players without forcing launches."""
        for service, player in self._players.items():
            try:
                player.discover()
                logger.info("Player discovery initialized: %s", service)
            except Exception as exc:
                logger.warning("Player discovery initialization failed for %s: %s", service, exc)

    def ensure_players_running(self) -> None:
        """Ensure every known player is running."""
        for player in self._players.values():
            try:
                player.ensure_running()
            except Exception as exc:
                logger.warning("ensure_running failed: %s", exc)

    def get_player(self, service: str) -> BasePlayer:
        """Get player for service."""
        if service not in self._players:
            raise ValueError(f"Unsupported service: {service}")
        return self._players[service]

    def get_active_player(self) -> BasePlayer | None:
        """Return active player instance if available."""
        if not self._active_service:
            return None
        return self._players.get(self._active_service)

    def stop_all_players(self) -> None:
        """Stop all players safely."""
        with self._lock:
            for service, player in self._players.items():
                try:
                    player.stop()
                    logger.info("Stopped player service=%s", service)
                except Exception as exc:
                    logger.warning("Failed stopping service=%s error=%s", service, exc)
            self._active_service = None

    def stop_all_other_players(self, target_service: str) -> None:
        """Stop all players except target service."""
        with self._lock:
            for service, player in self._players.items():
                if service == target_service:
                    continue
                try:
                    player.pause()
                    if player.is_playing():
                        player.stop()
                    logger.info("Stopped other player service=%s", service)
                except Exception as exc:
                    logger.warning("Failed stopping other service=%s error=%s", service, exc)

    def activate_player(self, service: str) -> None:
        """Bring target player into active state."""
        player = self.get_player(service)
        player.ensure_running()
        player.discover()
        player.activate()
        self._active_service = service

    def switch_to_player(self, service: str) -> BasePlayer:
        """Switch active playback service safely."""
        self.stop_all_other_players(service)
        self.activate_player(service)
        return self.get_player(service)

    def prepare_job(self, job: PlaybackJob) -> None:
        """Prepare job with active player context."""
        with self._lock:
            logger.info("prepare_job start queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player = self.switch_to_player(job.service)
            logger.info("prepare_job discover-before queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player.discover()
            logger.info("prepare_job place-before queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player.place_windows()
            logger.info("prepare_job activate-before queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player.activate()
            logger.info("prepare_job prepare queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player.prepare(job)
            logger.info("prepare_job load queue_item_id=%s service=%s source=%s", job.queue_item_id, job.service, job.path_or_url)
            player.load(job)
            logger.info("prepare_job select queue_item_id=%s service=%s title=%s artist=%s", job.queue_item_id, job.service, job.title, job.artist)
            player.select(job)
            player.discover()
            player.place_windows()
            player.activate()
            self._active_job = job
            logger.info("prepare_job complete queue_item_id=%s service=%s", job.queue_item_id, job.service)

    def start_job(self, job: PlaybackJob) -> bool:
        """Start playback and verify it started."""
        with self._lock:
            logger.info("start_job begin queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player = self.get_player(job.service)
            player.discover()
            player.place_windows()
            player.activate()
            logger.info("start_job send-start queue_item_id=%s service=%s", job.queue_item_id, job.service)
            player.start()
            started = player.verify_started(job)
            logger.info("start_job verify queue_item_id=%s service=%s started=%s", job.queue_item_id, job.service, started)
            if not started:
                try:
                    logger.warning(
                        "start_job verification failed queue_item_id=%s service=%s diagnostics=%s",
                        job.queue_item_id,
                        job.service,
                        player.capture_diagnostics(),
                    )
                except Exception as diagnostics_exc:
                    logger.warning(
                        "start_job diagnostics capture failed queue_item_id=%s service=%s error=%s",
                        job.queue_item_id,
                        job.service,
                        diagnostics_exc,
                    )
            if started:
                self._active_service = job.service
                self._active_job = job
            return started

    def monitor_job(self, job: PlaybackJob) -> bool:
        """Return true if current job has finished playback."""
        player = self.get_player(job.service)
        finished = player.has_finished()
        logger.info("monitor_job queue_item_id=%s service=%s finished=%s", job.queue_item_id, job.service, finished)
        return finished

    def finish_job(self, job: PlaybackJob) -> None:
        """Stop player output for completed job."""
        with self._lock:
            player = self.get_player(job.service)
            player.pause()
            self._active_job = None

    def fail_job(self, job: PlaybackJob, reason: str) -> None:
        """Handle failed job by stopping active service."""
        with self._lock:
            player = self.get_player(job.service)
            try:
                player.stop()
            except Exception:
                pass
            self._active_job = None
            logger.error("Playback job failed queue_item_id=%s reason=%s", job.queue_item_id, reason)
