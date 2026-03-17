from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.models.transaction import TransactionType
from app.schemas.transaction import (
    TransactionCreate,
    TransactionBulkCreate,
    TransactionBulkResponse,
    TransactionListResponse,
    TransactionRead,
    TransactionUpdate,
    CashflowSummary,
)
from app.services import transaction_service

router = APIRouter(prefix="/transactions")


@router.post("/", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.create_transaction(db, data)


@router.post(
    "/bulk",
    response_model=TransactionBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_transactions(
    data: TransactionBulkCreate,
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.bulk_create_transactions(db, data)


@router.get("/", response_model=TransactionListResponse)
async def list_transactions(
    sportsbook_id: Optional[UUID] = None,
    transaction_type: Optional[TransactionType] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    tax_year: Optional[int] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    items, total = await transaction_service.list_transactions(
        db,
        sportsbook_id=sportsbook_id,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        tax_year=tax_year,
        page=page,
        page_size=page_size,
    )
    return TransactionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cashflow", response_model=CashflowSummary)
async def get_cashflow_summary(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.get_cashflow_summary(db, date_from, date_to)


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.get_transaction(db, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.update_transaction(db, transaction_id, data)


@router.delete("/{transaction_id}", response_model=TransactionRead)
async def delete_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.delete_transaction(db, transaction_id)
