from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEFAULT_USER_ID
from app.core.dependencies import get_db
from app.schemas.wallet import (
    LedgerEntryResponse,
    LedgerHistoryResponse,
    WalletBalanceResponse,
)
from app.services import wallet_service

router = APIRouter(prefix="/wallet")


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_balance(
    user_id: UUID = Query(default=DEFAULT_USER_ID),
    db: AsyncSession = Depends(get_db),
):
    return await wallet_service.get_balance(db, user_id)


@router.get("/ledger", response_model=LedgerHistoryResponse)
async def get_ledger(
    user_id: UUID = Query(default=DEFAULT_USER_ID),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await wallet_service.get_ledger_history(
        db, user_id, limit=limit,
    )
    return LedgerHistoryResponse(
        items=[LedgerEntryResponse.model_validate(e) for e in items],
        total=total,
    )
