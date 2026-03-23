from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnprocessableError
from app.models.balance import UserBalance
from app.models.ledger import LedgerEntry, LedgerEntryType


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
