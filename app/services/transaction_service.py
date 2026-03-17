"""Servicio de Transacciones: CRUD, importación masiva y flujo de caja.

Contiene toda la lógica de negocio para el módulo contable de BetSync.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sportsbook import Sportsbook
from app.models.transaction import Transaction, TransactionType
from app.schemas.transaction import (
    CashflowSummary,
    SportsbookBalance,
    TransactionBulkCreate,
    TransactionBulkResponse,
    TransactionCreate,
    TransactionUpdate,
)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_transaction(
    db: AsyncSession,
    payload: TransactionCreate,
) -> Transaction:
    """Crea una transacción individual."""
    data = payload.model_dump()
    # Si tax_year no viene, inferirlo de transaction_date
    if data.get("tax_year") is None:
        data["tax_year"] = payload.transaction_date.year
    tx = Transaction(**data)
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


async def get_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
) -> Optional[Transaction]:
    """Obtiene una transacción por ID."""
    result = await db.execute(
        select(Transaction).where(Transaction.transaction_id == transaction_id)
    )
    return result.scalar_one_or_none()


async def list_transactions(
    db: AsyncSession,
    sportsbook_id: Optional[uuid.UUID] = None,
    type: Optional[TransactionType] = None,
    tax_year: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Transaction], int]:
    """Lista transacciones con filtros y paginación."""
    query = select(Transaction)

    if sportsbook_id:
        query = query.where(Transaction.sportsbook_id == sportsbook_id)
    if type:
        query = query.where(Transaction.type == type)
    if tax_year:
        query = query.where(Transaction.tax_year == tax_year)
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.where(Transaction.transaction_date <= date_to)

    # Total para paginación
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Página
    offset = (page - 1) * page_size
    query = query.order_by(Transaction.transaction_date.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
    payload: TransactionUpdate,
) -> Optional[Transaction]:
    """Actualiza campos de una transacción."""
    tx = await get_transaction(db, transaction_id)
    if not tx:
        return None
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tx, field, value)
    await db.commit()
    await db.refresh(tx)
    return tx


async def delete_transaction(
    db: AsyncSession,
    transaction_id: uuid.UUID,
) -> bool:
    """Elimina una transacción. Retorna True si existía."""
    tx = await get_transaction(db, transaction_id)
    if not tx:
        return False
    await db.delete(tx)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# Importación masiva (el "mata-Excel")
# ---------------------------------------------------------------------------

async def bulk_create_transactions(
    db: AsyncSession,
    payload: TransactionBulkCreate,
) -> TransactionBulkResponse:
    """Importa hasta 500 transacciones en una sola operación.

    Estrategia: intenta insertar cada item individualmente para poder
    reportar errores por índice sin abortar todo el lote.
    """
    created = 0
    failed = 0
    errors: List[str] = []

    for idx, tx_data in enumerate(payload.transactions):
        try:
            data = tx_data.model_dump()
            if data.get("tax_year") is None:
                data["tax_year"] = tx_data.transaction_date.year
            tx = Transaction(**data)
            db.add(tx)
            await db.flush()  # Detectar errores de FK sin cerrar la sesión
            created += 1
        except Exception as exc:
            await db.rollback()
            failed += 1
            errors.append(f"[{idx}] {type(exc).__name__}: {str(exc)[:120]}")

    if created > 0:
        await db.commit()

    return TransactionBulkResponse(created=created, failed=failed, errors=errors)


# ---------------------------------------------------------------------------
# Flujo de Caja y Saldos por Casa
# ---------------------------------------------------------------------------

async def get_cashflow_summary(
    db: AsyncSession,
    date_from: date,
    date_to: date,
) -> CashflowSummary:
    """Calcula el flujo de caja consolidado entre dos fechas."""

    # Agregaciones por sportsbook y tipo
    result = await db.execute(
        select(
            Transaction.sportsbook_id,
            Transaction.type,
            func.sum(Transaction.amount * Transaction.exchange_rate).label("total_mxn"),
        )
        .where(Transaction.transaction_date.between(date_from, date_to))
        .group_by(Transaction.sportsbook_id, Transaction.type)
    )
    rows = result.all()

    # Agrupar por sportsbook_id
    sportsbooks_data: dict = {}
    for sportsbook_id, tx_type, total_mxn in rows:
        if sportsbook_id not in sportsbooks_data:
            sportsbooks_data[sportsbook_id] = {
                "deposits": Decimal("0"),
                "withdrawals": Decimal("0"),
                "bonuses": Decimal("0"),
            }
        if tx_type == TransactionType.deposit:
            sportsbooks_data[sportsbook_id]["deposits"] += total_mxn or Decimal("0")
        elif tx_type == TransactionType.withdrawal:
            sportsbooks_data[sportsbook_id]["withdrawals"] += total_mxn or Decimal("0")
        elif tx_type == TransactionType.bonus:
            sportsbooks_data[sportsbook_id]["bonuses"] += total_mxn or Decimal("0")

    # Cargar nombres de sportsbooks
    sb_ids = list(sportsbooks_data.keys())
    balances: List[SportsbookBalance] = []
    total_in = Decimal("0")
    total_out = Decimal("0")

    if sb_ids:
        sb_result = await db.execute(
            select(Sportsbook).where(Sportsbook.sportsbook_id.in_(sb_ids))
        )
        sportsbooks = {sb.sportsbook_id: sb for sb in sb_result.scalars().all()}

        for sb_id, agg in sportsbooks_data.items():
            sb = sportsbooks.get(sb_id)
            name = sb.name if sb else str(sb_id)
            currency = sb.currency if sb else "MXN"
            deposits = agg["deposits"]
            withdrawals = agg["withdrawals"]
            bonuses = agg["bonuses"]
            balance = deposits + bonuses - withdrawals
            total_in += deposits + bonuses
            total_out += withdrawals

            balances.append(SportsbookBalance(
                sportsbook_id=sb_id,
                sportsbook_name=name,
                currency=currency,
                total_deposits_mxn=deposits,
                total_withdrawals_mxn=withdrawals,
                total_bonuses_mxn=bonuses,
                estimated_balance_mxn=balance,
            ))

    return CashflowSummary(
        period_start=date_from,
        period_end=date_to,
        total_in_mxn=total_in,
        total_out_mxn=total_out,
        net_cashflow_mxn=total_in - total_out,
        by_sportsbook=balances,
    )
