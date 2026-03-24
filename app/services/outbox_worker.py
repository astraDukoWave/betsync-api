"""Transactional outbox processing (at-least-once safe with idempotent ``event_key``)."""

from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEvent


async def fetch_pending_outbox_for_update(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> list[OutboxEvent]:
    """Rows not yet delivered; ``SKIP LOCKED`` allows concurrent workers."""
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def deliver_outbox_event(
    event: OutboxEvent,
    handler: Callable[[OutboxEvent], Awaitable[None]],
) -> None:
    """Invoke side effects once; skip if already marked processed."""
    if event.processed_at is not None:
        return
    await handler(event)
    event.processed_at = datetime.now(timezone.utc)


async def run_outbox_batch(
    db: AsyncSession,
    handler: Callable[[OutboxEvent], Awaitable[None]],
    *,
    limit: int = 100,
) -> int:
    """Process up to ``limit`` pending rows in the current transaction."""
    events = await fetch_pending_outbox_for_update(db, limit=limit)
    processed = 0
    for event in events:
        await deliver_outbox_event(event, handler)
        processed += 1
    return processed
