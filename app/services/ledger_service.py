from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, UnprocessableError
from app.models.balance import UserBalance
from app.models.ledger import LedgerEntry, LedgerEntryType
from app.models.pick import Pick, PickStatus

if TYPE_CHECKING:
    from app.services.pick_service import PickPersistSnapshot


def pick_created_outbox_event_key(pick_id: UUID) -> str:
    """Stable idempotency key for pick.created outbox rows."""
    return hashlib.sha256(f"{pick_id}:pick.created".encode()).hexdigest()


def pick_settled_outbox_event_key(pick_id: UUID, status: PickStatus) -> str:
    """Idempotency key = hash(pick_id + terminal status) for settlement."""
    return hashlib.sha256(f"{pick_id}:{status.value}".encode()).hexdigest()


_SETTLEMENT_LEDGER_TYPES: tuple[LedgerEntryType, ...] = (
    LedgerEntryType.PICK_PAYOUT,
    LedgerEntryType.PICK_LOSS,
    LedgerEntryType.PICK_REFUND,
)


def _ledger_type_for_settlement(status: PickStatus) -> LedgerEntryType:
    if status == PickStatus.won:
        return LedgerEntryType.PICK_PAYOUT
    if status == PickStatus.lost:
        return LedgerEntryType.PICK_LOSS
    if status in (PickStatus.push, PickStatus.void):
        return LedgerEntryType.PICK_REFUND
    raise UnprocessableError(
        "SETTLEMENT_STATUS_INVALID",
        "Settlement ledger only applies to terminal pick statuses",
        meta={"status": status.value},
    )


async def lock_and_get_balance(db: AsyncSession, user_id: UUID) -> UserBalance:
    """Ensure a balance row exists, then lock it with SELECT FOR UPDATE."""
    await db.execute(
        insert(UserBalance)
        .values(
            user_id=user_id,
            available_balance=Decimal("0"),
            locked_balance=Decimal("0"),
        )
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    result = await db.execute(
        select(UserBalance)
        .where(UserBalance.user_id == user_id)
        .with_for_update()
    )
    row = result.scalar_one()
    return row


async def record_movement(
    db: AsyncSession,
    user_id: UUID,
    amount: Decimal,
    entry_type: LedgerEntryType,
    reference_id: UUID | None,
) -> LedgerEntry:
    """Update ``user_balances`` and append an immutable ledger line (same transaction)."""
    ub = await lock_and_get_balance(db, user_id)

    if entry_type == LedgerEntryType.PICK_STAKE_LOCK:
        if amount <= 0:
            raise UnprocessableError(
                "LEDGER_AMOUNT_INVALID",
                "PICK_STAKE_LOCK requires amount > 0",
                meta={"amount": str(amount)},
            )
        if ub.available_balance < amount:
            raise UnprocessableError(
                "INSUFFICIENT_AVAILABLE_BALANCE",
                "available_balance is less than stake",
                meta={
                    "available": str(ub.available_balance),
                    "required": str(amount),
                },
            )
        ub.available_balance = ub.available_balance - amount
        ub.locked_balance = ub.locked_balance + amount
    else:
        raise UnprocessableError(
            "LEDGER_TYPE_UNSUPPORTED",
            f"Ledger entry type not implemented: {entry_type.value}",
            meta={"type": entry_type.value},
        )

    entry = LedgerEntry(
        user_id=user_id,
        amount=amount,
        type=entry_type,
        reference_id=reference_id,
        balance_after=ub.available_balance,
        locked_after=ub.locked_balance,
    )
    db.add(entry)
    return entry


async def record_settlement(
    db: AsyncSession,
    pick: Pick,
    status: PickStatus,
    *,
    prior: PickPersistSnapshot,
    user_balance: UserBalance | None,
) -> Optional[LedgerEntry]:
    """Atomically settle a staked pick into balances + ledger, or repair pick state (idempotent).

    Order: update pick → update balances → insert ledger. Caller must hold pick and balance
    row locks (``SELECT FOR UPDATE``) when money moves.
    """
    from app.services.pick_service import (  # noqa: PLC0415 — avoid import cycle
        DomainValidator,
        _TERMINAL_STATUSES,
        _settlement_for_status,
    )

    settlement_type = _ledger_type_for_settlement(status)
    ref = pick.pick_id

    existing_rows = (
        (
            await db.execute(
                select(LedgerEntry).where(
                    LedgerEntry.reference_id == ref,
                    LedgerEntry.type.in_(_SETTLEMENT_LEDGER_TYPES),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(existing_rows) > 1:
        raise UnprocessableError(
            "LEDGER_SETTLEMENT_AMBIGUOUS",
            "Multiple settlement ledger rows for the same pick",
            meta={"pick_id": str(ref), "count": len(existing_rows)},
        )
    existing = existing_rows[0] if existing_rows else None

    if existing is not None:
        if existing.type != settlement_type:
            raise ConflictError(
                "SETTLEMENT_LEDGER_TYPE_MISMATCH",
                "Pick already settled under a different ledger outcome",
                meta={"ledger_type": existing.type.value, "requested": settlement_type.value},
            )
        if pick.status in _TERMINAL_STATUSES:
            return existing
        now = datetime.now(timezone.utc)
        pick.status = status
        pick.resolved_at = now
        pick.settled_return, pick.profit = _settlement_for_status(
            status, pick.stake, pick.odds_decimal
        )
        exp_repair = DomainValidator._expected_profit(
            status, pick.stake, pick.odds_decimal
        )
        if exp_repair is not None:
            assert pick.profit == exp_repair, (
                f"profit must match accounting formula: got {pick.profit!s} "
                f"expected {exp_repair!s}"
            )
        DomainValidator.validate(
            pick, prior, profit_tolerance=settings.pick_profit_tolerance
        )
        await db.flush()
        return existing

    financial = (
        pick.user_id is not None
        and pick.stake is not None
        and pick.stake > 0
    )

    if pick.status != PickStatus.pending:
        raise UnprocessableError(
            "SETTLEMENT_PICK_NOT_PENDING",
            "Pick must be pending to record a new settlement",
            meta={"status": pick.status.value},
        )

    if financial:
        if user_balance is None:
            raise UnprocessableError(
                "SETTLEMENT_BALANCE_REQUIRED",
                "user_balance row required for staked settlement",
            )
        if user_balance.user_id != pick.user_id:
            raise UnprocessableError(
                "SETTLEMENT_USER_MISMATCH",
                "Locked balance row does not match pick.user_id",
            )
        if user_balance.available_balance < 0:
            raise UnprocessableError(
                "CRITICAL_INVARIANT_BROKEN",
                "available_balance is negative before settlement",
                meta={"available": str(user_balance.available_balance)},
            )
        if user_balance.locked_balance < pick.stake:
            raise UnprocessableError(
                "CRITICAL_INVARIANT_BROKEN",
                "locked_balance is less than pick stake (escrow missing)",
                meta={
                    "locked": str(user_balance.locked_balance),
                    "stake": str(pick.stake),
                },
            )

    now = datetime.now(timezone.utc)
    pick.status = status
    pick.resolved_at = now
    pick.settled_return, pick.profit = _settlement_for_status(
        status, pick.stake, pick.odds_decimal
    )

    expected = DomainValidator._expected_profit(status, pick.stake, pick.odds_decimal)
    if expected is not None:
        assert pick.profit == expected, (
            f"profit must match accounting formula: got {pick.profit!s} "
            f"expected {expected!s}"
        )

    DomainValidator.validate(
        pick, prior, profit_tolerance=settings.pick_profit_tolerance
    )

    if not financial:
        await db.flush()
        return None

    await db.flush()

    ub = user_balance
    stake = pick.stake
    assert stake is not None and stake > 0

    if status == PickStatus.won:
        payout = stake + (pick.profit or Decimal("0"))
        ub.locked_balance = ub.locked_balance - stake
        ub.available_balance = ub.available_balance + payout
        amount = payout
    elif status == PickStatus.lost:
        ub.locked_balance = ub.locked_balance - stake
        amount = stake
    else:
        ub.locked_balance = ub.locked_balance - stake
        ub.available_balance = ub.available_balance + stake
        amount = stake

    if ub.available_balance < 0 or ub.locked_balance < 0:
        raise UnprocessableError(
            "CRITICAL_INVARIANT_BROKEN",
            "Balances would be negative after settlement",
            meta={
                "available": str(ub.available_balance),
                "locked": str(ub.locked_balance),
            },
        )

    entry = LedgerEntry(
        user_id=pick.user_id,
        amount=amount,
        type=settlement_type,
        reference_id=ref,
        balance_after=ub.available_balance,
        locked_after=ub.locked_balance,
    )
    db.add(entry)
    await db.flush()
    return entry
