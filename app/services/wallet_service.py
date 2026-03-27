from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.balance import UserBalance
from app.models.ledger import LedgerEntry


async def get_balance(db: AsyncSession, user_id: UUID) -> UserBalance:
    result = await db.execute(
        select(UserBalance).where(UserBalance.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError(
            "USER_BALANCE_NOT_FOUND",
            f"No balance row for user_id={user_id}",
        )
    return row


async def get_ledger_history(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int = 50,
) -> tuple[list[LedgerEntry], int]:
    balance = await db.execute(
        select(UserBalance.user_id).where(UserBalance.user_id == user_id)
    )
    if balance.scalar_one_or_none() is None:
        raise NotFoundError(
            "USER_BALANCE_NOT_FOUND",
            f"No balance row for user_id={user_id}",
        )

    total_result = await db.execute(
        select(func.count(LedgerEntry.ledger_entry_id)).where(
            LedgerEntry.user_id == user_id
        )
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
    )
    items = list(result.scalars().all())
    return items, total
