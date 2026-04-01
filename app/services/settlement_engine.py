"""Central settlement orchestration: single entry point for terminal Pick transitions."""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import DEFAULT_USER_ID
from app.core.exceptions import ConflictError, NotFoundError
from app.models.ledger import LedgerEntry, LedgerEntryType
from app.models.outbox import OutboxEvent
from app.models.pick import Pick, PickStatus
from app.services.ledger_service import (
    lock_and_get_balance,
    pick_settled_outbox_event_key,
    record_settlement,
)
from app.services.reconciliation_service import assert_financial_health

logger = logging.getLogger(__name__)

_RESOLVE_LEDGER_TYPES = (
    LedgerEntryType.PICK_PAYOUT,
    LedgerEntryType.PICK_LOSS,
)


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate == "23505":
        return True
    pgcode = getattr(orig, "pgcode", None)
    return pgcode == "23505"


async def execute_settlement(
    db: AsyncSession,
    pick_id: UUID,
    target_status: PickStatus,
    *,
    idempotency_key: str | None = None,
    closing_odds_decimal: Decimal | None = None,
) -> Pick:
    """
    Deterministic settlement: lock pick (1), then balance (2) when money moves.
    All terminal pick mutations for WON/LOST/PUSH/VOID go through this function.
    """
    from app.services.pick_service import (  # noqa: PLC0415 — break import cycle at load time
        _TERMINAL_STATUSES,
        pick_persist_snapshot,
    )
    from app.worker.pipeline.calculator import calc_clv  # noqa: PLC0415

    if idempotency_key:
        logger.debug(
            "execute_settlement idempotency_key=%s pick_id=%s target=%s",
            idempotency_key,
            pick_id,
            target_status.value,
        )

    try:
        async with db.begin_nested():
            result = await db.execute(
                select(Pick)
                .options(selectinload(Pick.match))
                .options(selectinload(Pick.sportsbook))
                .where(Pick.pick_id == pick_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            pick = result.scalar_one_or_none()
            if not pick:
                raise NotFoundError("PICK_NOT_FOUND", f"Pick {pick_id} not found")

            if pick.status == target_status:
                await db.refresh(pick)
                return pick

            if pick.status in _TERMINAL_STATUSES:
                raise ConflictError(
                    "TERMINAL_STATE_CONFLICT",
                    "Pick is already in a terminal state different from the requested target",
                    meta={
                        "current_status": pick.status.value,
                        "requested": target_status.value,
                        "pick_id": str(pick_id),
                    },
                )

            if pick.user_id is not None and pick.user_id != DEFAULT_USER_ID:
                raise ConflictError(
                    "PICK_OWNERSHIP_MISMATCH",
                    "Pick does not belong to the current operational user",
                    meta={
                        "pick_id": str(pick_id),
                        "pick_user_id": str(pick.user_id),
                    },
                )

            if target_status == PickStatus.void:
                payout_or_loss = await db.scalar(
                    select(LedgerEntry.ledger_entry_id).where(
                        LedgerEntry.reference_id == pick.pick_id,
                        LedgerEntry.type.in_(_RESOLVE_LEDGER_TYPES),
                    ).limit(1)
                )
                if payout_or_loss is not None:
                    raise ConflictError(
                        "SETTLEMENT_ALREADY_DECIDED",
                        "Resolve outcome (payout/loss) already recorded; void cannot override",
                        meta={"pick_id": str(pick_id)},
                    )

            prior = pick_persist_snapshot(pick)

            if closing_odds_decimal is not None:
                pick.closing_odds_decimal = closing_odds_decimal
                pick.clv = Decimal(
                    str(
                        calc_clv(
                            float(pick.odds_decimal),
                            float(closing_odds_decimal),
                        )
                    )
                )

            user_balance = None
            financial = (
                pick.user_id is not None
                and pick.stake is not None
                and pick.stake > 0
            )
            if financial:
                await assert_financial_health(db, pick.user_id)
                user_balance = await lock_and_get_balance(db, pick.user_id)

            await record_settlement(
                db,
                pick,
                target_status,
                prior=prior,
                user_balance=user_balance,
            )

            db.add(
                OutboxEvent(
                    event_type="pick.settled",
                    event_key=pick_settled_outbox_event_key(pick.pick_id, target_status),
                    payload={
                        "pick_id": str(pick.pick_id),
                        "user_id": str(pick.user_id) if pick.user_id else None,
                        "status": target_status.value,
                    },
                )
            )
            await db.flush()
    except IntegrityError as exc:
        if _is_unique_violation(exc):
            raise ConflictError(
                "SETTLEMENT_RACE_CONDITION",
                "Concurrent settlement detected (unique constraint violation)",
                meta={"pick_id": str(pick_id)},
            ) from exc
        raise

    await db.refresh(pick)
    return pick
