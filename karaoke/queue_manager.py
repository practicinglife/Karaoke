"""Queue management and singer rotation logic."""

from __future__ import annotations

from collections import deque

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .models import QueueItem, SessionRecord, SessionSinger
from .utils import utcnow

WAITING = "WAITING"
NOW_PLAYING = "NOW_PLAYING"
COMPLETED = "COMPLETED"
SKIPPED = "SKIPPED"
REMOVED = "REMOVED"


class QueueManager:
    """Queue operations for active karaoke sessions."""

    def __init__(self, db_session: Session) -> None:
        self.db_session = db_session

    def add_song(self, session_id: int, user_id: int, song_id: int) -> QueueItem:
        """Insert a song into queue with duplicate-waiting protection."""
        duplicate = self.find_waiting_song(session_id, user_id, song_id)
        if duplicate:
            raise ValueError("This exact song is already waiting in the queue.")

        next_position = (
            self.db_session.scalar(
                select(func.coalesce(func.max(QueueItem.queue_position), 0)).where(
                    QueueItem.session_id == session_id
                )
            )
            or 0
        )
        item = QueueItem(
            session_id=session_id,
            user_id=user_id,
            song_id=song_id,
            status=WAITING,
            queue_position=next_position + 1,
            added_at=utcnow(),
        )
        self.db_session.add(item)
        self.db_session.flush()
        self._join_rotation(session_id, user_id)
        return item

    def find_waiting_song(self, session_id: int, user_id: int, song_id: int) -> QueueItem | None:
        """Return the user's waiting queue item for the given song, if present."""
        return self.db_session.scalar(
            select(QueueItem).where(
                QueueItem.session_id == session_id,
                QueueItem.user_id == user_id,
                QueueItem.song_id == song_id,
                QueueItem.status == WAITING,
            )
        )

    def remove_waiting_song(self, session_id: int, user_id: int, song_id: int) -> QueueItem | None:
        """Remove the user's waiting queue item for the given song, if present."""
        item = self.find_waiting_song(session_id, user_id, song_id)
        if not item:
            return None
        item.status = REMOVED
        self.db_session.flush()
        return item

    def waiting_items(self, session_id: int) -> list[QueueItem]:
        """Get waiting queue items in FIFO order."""
        return list(
            self.db_session.scalars(
                select(QueueItem)
                .options(joinedload(QueueItem.user), joinedload(QueueItem.song))
                .where(
                    QueueItem.session_id == session_id,
                    QueueItem.status == WAITING,
                )
                .order_by(QueueItem.queue_position.asc(), QueueItem.added_at.asc())
            )
        )

    def now_playing(self, session_id: int) -> QueueItem | None:
        """Get current now-playing item."""
        return self.db_session.scalar(
            select(QueueItem)
            .options(joinedload(QueueItem.user), joinedload(QueueItem.song))
            .where(
                QueueItem.session_id == session_id,
                QueueItem.status == NOW_PLAYING,
            )
            .order_by(QueueItem.updated_at.desc())
        )

    def ordered_up_next(self, session_id: int, singer_rotation_on: bool) -> list[QueueItem]:
        """Return up-next order according to settings.

        Rotation: singers keep the place they first joined in tonight, one song per turn.
        A new singer joins at the end of the order (so they sing at the start of the next
        round). A singer with nothing queued keeps their place and their turn is skipped.
        The cycle continues after whoever sang last, so nobody sings twice in a row while
        others are waiting.
        """
        waiting = self.waiting_items(session_id)
        if not singer_rotation_on:
            return waiting

        buckets: dict[int, deque[QueueItem]] = {}
        for item in waiting:
            buckets.setdefault(item.user_id, deque()).append(item)
        order = self.rotation_order(session_id)
        for user_id in buckets:  # safety net: anyone missing from the rotation goes last
            if user_id not in order:
                order.append(user_id)

        last_item = self.now_playing(session_id) or self.db_session.scalar(
            select(QueueItem)
            .where(QueueItem.session_id == session_id, QueueItem.status.in_([COMPLETED, SKIPPED]))
            .order_by(QueueItem.updated_at.desc(), QueueItem.id.desc())
        )
        start = 0
        if last_item and last_item.user_id in order:
            start = order.index(last_item.user_id) + 1

        output: list[QueueItem] = []
        while any(buckets.values()):
            for offset in range(len(order)):
                user_id = order[(start + offset) % len(order)]
                bucket = buckets.get(user_id)
                if bucket:
                    output.append(bucket.popleft())
        return output

    def rotation_order(self, session_id: int) -> list[int]:
        """Singers in tonight's rotation order, adding anyone not registered yet."""
        rows = list(
            self.db_session.scalars(
                select(SessionSinger)
                .where(SessionSinger.session_id == session_id)
                .order_by(SessionSinger.rotation_order)
            )
        )
        known = {row.user_id for row in rows}
        # Singers whose songs were queued before rotation tracking existed: in the order
        # of their first queued song tonight.
        first_positions = self.db_session.execute(
            select(QueueItem.user_id, func.min(QueueItem.queue_position))
            .where(QueueItem.session_id == session_id)
            .group_by(QueueItem.user_id)
            .order_by(func.min(QueueItem.queue_position))
        ).all()
        missing = [user_id for user_id, _ in first_positions if user_id not in known]
        if missing:
            next_order = (rows[-1].rotation_order if rows else 0) + 1
            for user_id in missing:
                row = SessionSinger(session_id=session_id, user_id=user_id, rotation_order=next_order)
                self.db_session.add(row)
                rows.append(row)
                next_order += 1
            self.db_session.flush()
        return [row.user_id for row in rows]

    def _join_rotation(self, session_id: int, user_id: int) -> None:
        exists = self.db_session.scalar(
            select(SessionSinger.id).where(SessionSinger.session_id == session_id, SessionSinger.user_id == user_id)
        )
        if exists is None:
            self.rotation_order(session_id)  # register earlier singers first, in their order
            exists = self.db_session.scalar(
                select(SessionSinger.id).where(SessionSinger.session_id == session_id, SessionSinger.user_id == user_id)
            )
        if exists is None:
            last = self.db_session.scalar(
                select(func.max(SessionSinger.rotation_order)).where(SessionSinger.session_id == session_id)
            ) or 0
            self.db_session.add(SessionSinger(session_id=session_id, user_id=user_id, rotation_order=last + 1))
            self.db_session.flush()

    def mark_now_playing(self, queue_item_id: int) -> QueueItem:
        """Mark selected item as now playing and clear previous now playing."""
        item = self.db_session.get(QueueItem, queue_item_id)
        if not item:
            raise ValueError("Queue item not found.")
        session_id = item.session_id
        current = self.now_playing(session_id)
        if current and current.id != item.id:
            current.status = COMPLETED
        item.status = NOW_PLAYING
        self.db_session.flush()
        return item

    def mark_status(self, queue_item_id: int, status: str) -> QueueItem:
        """Set status of queue item."""
        item = self.db_session.get(QueueItem, queue_item_id)
        if not item:
            raise ValueError("Queue item not found.")
        item.status = status
        self.db_session.flush()
        return item

    def next_song(self, session_id: int, singer_rotation_on: bool) -> QueueItem | None:
        """Advance queue and return new now playing."""
        current = self.now_playing(session_id)
        if current:
            current.status = COMPLETED
        up_next = self.ordered_up_next(session_id, singer_rotation_on)
        if not up_next:
            return None
        up_next[0].status = NOW_PLAYING
        self.db_session.flush()
        return up_next[0]

    def remove_item(self, queue_item_id: int) -> QueueItem:
        """Mark item as removed."""
        return self.mark_status(queue_item_id, REMOVED)

    def skip_item(self, queue_item_id: int) -> QueueItem:
        """Mark item as skipped."""
        return self.mark_status(queue_item_id, SKIPPED)

    def move_item(self, queue_item_id: int, direction: str, singer_rotation_on: bool = False) -> None:
        """Move queue item up/down in waiting list."""
        item = self.db_session.get(QueueItem, queue_item_id)
        if not item or item.status != WAITING:
            raise ValueError("Waiting queue item not found.")

        if direction not in {"up", "down"}:
            raise ValueError("Invalid direction.")

        if singer_rotation_on:
            ordered = self.ordered_up_next(item.session_id, True)
            index_by_id = {entry.id: idx for idx, entry in enumerate(ordered)}
            index = index_by_id.get(item.id)
            if index is None:
                return
            swap_index = index - 1 if direction == "up" else index + 1
            if swap_index < 0 or swap_index >= len(ordered):
                return
            other = ordered[swap_index]
            if other.user_id == item.user_id:
                # Same singer (only singer left): reorder their own songs.
                item.queue_position, other.queue_position = other.queue_position, item.queue_position
            else:
                # Different singers: swap their places in tonight's rotation.
                rows = {
                    row.user_id: row
                    for row in self.db_session.scalars(
                        select(SessionSinger).where(
                            SessionSinger.session_id == item.session_id,
                            SessionSinger.user_id.in_([item.user_id, other.user_id]),
                        )
                    )
                }
                a, b = rows[item.user_id], rows[other.user_id]
                a.rotation_order, b.rotation_order = b.rotation_order, a.rotation_order
            self.db_session.flush()
            return

        comparator = (
            QueueItem.queue_position < item.queue_position
            if direction == "up"
            else QueueItem.queue_position > item.queue_position
        )
        order = (
            QueueItem.queue_position.desc()
            if direction == "up"
            else QueueItem.queue_position.asc()
        )
        neighbor = self.db_session.scalar(
            select(QueueItem).where(
                QueueItem.session_id == item.session_id,
                QueueItem.status == WAITING,
                comparator,
            ).order_by(order)
        )
        if not neighbor:
            return
        item.queue_position, neighbor.queue_position = (
            neighbor.queue_position,
            item.queue_position,
        )
        self.db_session.flush()

    def clear_queue(self, session_id: int) -> int:
        """Remove all waiting/now-playing items from active queue."""
        items = list(
            self.db_session.scalars(
                select(QueueItem).where(
                    QueueItem.session_id == session_id,
                    QueueItem.status.in_([WAITING, NOW_PLAYING]),
                )
            )
        )
        for item in items:
            item.status = REMOVED
        self.db_session.flush()
        return len(items)

    def active_session(self) -> SessionRecord | None:
        """Return current active session."""
        return self.db_session.scalar(
            select(SessionRecord)
            .where(SessionRecord.status == "RUNNING")
            .order_by(SessionRecord.started_at.desc())
        )

