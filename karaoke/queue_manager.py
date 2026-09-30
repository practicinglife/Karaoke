"""Queue management and singer rotation logic."""

from __future__ import annotations

from collections import deque
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .models import QueueItem, SessionRecord

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
            added_at=datetime.utcnow(),
        )
        self.db_session.add(item)
        self.db_session.flush()
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
        """Return up-next order according to settings."""
        waiting = self.waiting_items(session_id)
        if not singer_rotation_on:
            return waiting

        user_buckets: dict[int, deque[QueueItem]] = {}
        user_order: list[int] = []
        for item in waiting:
            bucket = user_buckets.get(item.user_id)
            if bucket is None:
                bucket = deque()
                user_buckets[item.user_id] = bucket
                user_order.append(item.user_id)
            bucket.append(item)

        rotation = deque(user_order)
        current = self.now_playing(session_id)
        last_user_id = current.user_id if current else None
        output: list[QueueItem] = []

        if waiting and rotation:
            immediate_user_id = waiting[-1].user_id
            has_alternative = any(uid != immediate_user_id for uid in rotation)
            if immediate_user_id != last_user_id or not has_alternative:
                while rotation and rotation[0] != immediate_user_id:
                    rotation.rotate(-1)
                selected_user_id = rotation.popleft()
                output.append(user_buckets[selected_user_id].popleft())
                last_user_id = selected_user_id
                if user_buckets[selected_user_id]:
                    rotation.append(selected_user_id)

        while rotation:
            selectable_users = [uid for uid in rotation if user_buckets.get(uid)]
            if not selectable_users:
                break

            chosen_user_id = next((uid for uid in selectable_users if uid != last_user_id), selectable_users[0])

            while rotation and rotation[0] != chosen_user_id:
                rotation.rotate(-1)

            selected_user_id = rotation.popleft()
            output.append(user_buckets[selected_user_id].popleft())
            last_user_id = selected_user_id
            if user_buckets[selected_user_id]:
                rotation.append(selected_user_id)

        return output

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

            ordered[index], ordered[swap_index] = ordered[swap_index], ordered[index]
            for idx, entry in enumerate(ordered, start=1):
                entry.queue_position = idx
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

