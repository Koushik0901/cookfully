from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import utc_now
from vigor_vine.infrastructure.models.jobs import OutboxEvent


class OutboxDispatcher:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        publisher: Callable[[dict[str, object]], None],
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher

    def dispatch_batch(self, limit: int = 100) -> int:
        published = 0
        with self._session_factory.begin() as session:
            events = session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for event in events:
                event.publish_attempts += 1
                try:
                    self._publisher(event.payload)
                except (ConnectionError, TimeoutError):
                    continue
                event.published_at = utc_now()
                published += 1
        return published
