"""Motor Fiscal (Fiscal Engine) de BetSync.

Servicio que cruza los dominios Pick y Transaction para calcular
la base imponible estimada y generar datos para el reporte CSV
que se entrega al contador.

Jurisdicción objetivo: México (SAT).
Moneda base de reporte: MXN.
"""
from datetime import date
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy import func, select, case, and_, extract, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick import Pick, PickStatus
from app.models.transaction import Transaction, TransactionType
from app.schemas.fiscal import FiscalSummaryResponse

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

ZERO = Decimal("0.00")

# Tipos que representan entradas de dinero (ingresos / depósitos)
INFLOW_TYPES = {TransactionType.deposit, TransactionType.bonus}
# Tipos que representan salidas de dinero
OUTFLOW_TYPES = {TransactionType.withdrawal}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _pick_fiscal_year(pick: Pick) -> int:
    """Devuelve el año fiscal de un pick.

    Prioriza resolved_at; si es None usa run_date.
    Esto garantiza que el pick se contabilice en el año en que
    se liquidó la apuesta, no en el que se registró.
    """
    if pick.resolved_at is not None:
        return pick.resolved_at.year
    return pick.run_date.year


# ---------------------------------------------------------------------------
# Funciones de agregación principales
# ---------------------------------------------------------------------------

async def _aggregate_picks(
    db: AsyncSession,
    tax_year: int,
) -> Tuple[Decimal, Decimal, int, int]:
    """Agrega picks ganados y perdidos para el año fiscal dado.

    Lógica de fechas:
      - Si resolved_at IS NOT NULL  → usar extract(year FROM resolved_at)
      - Si resolved_at IS NULL      → usar extract(year FROM run_date)

    Returns
    -------
    (gross_winnings, gross_losses, count_won, count_lost)
    """
    # Expresión de año fiscal para cada pick:
    # CASE WHEN resolved_at IS NOT NULL
    #      THEN EXTRACT(year FROM resolved_at)
    #      ELSE EXTRACT(year FROM run_date) END
    fiscal_year_expr = case(
        (Pick.resolved_at.isnot(None), extract("year", Pick.resolved_at)),
        else_=extract("year", Pick.run_date),
    )

    # --- Picks WON ---
    won_stmt = select(
        func.coalesce(
            func.sum((Pick.stake * Pick.odds_decimal) - Pick.stake), ZERO
        ).label("gross_winnings"),
        func.count(Pick.pick_id).label("count_won"),
    ).where(
        and_(
            Pick.status == PickStatus.won,
            Pick.stake.isnot(None),
            fiscal_year_expr == tax_year,
        )
    )

    # --- Picks LOST ---
    lost_stmt = select(
        func.coalesce(
            func.sum(Pick.stake), ZERO
        ).label("gross_losses"),
        func.count(Pick.pick_id).label("count_lost"),
    ).where(
        and_(
            Pick.status == PickStatus.lost,
            Pick.stake.isnot(None),
            fiscal_year_expr == tax_year,
        )
    )

    won_result = await db.execute(won_stmt)
    lost_result = await db.execute(lost_stmt)

    won_row = won_result.one()
    lost_row = lost_result.one()

    gross_winnings = Decimal(str(won_row.gross_winnings or ZERO))
    gross_losses = Decimal(str(lost_row.gross_losses or ZERO))
    count_won = won_row.count_won or 0
    count_lost = lost_row.count_lost or 0

    return gross_winnings, gross_losses, count_won, count_lost


async def _aggregate_transactions(
    db: AsyncSession,
    tax_year: int,
) -> Tuple[Decimal, Decimal]:
    """Agrega transacciones de entrada y salida para el año fiscal.

    Las transacciones ya tienen el campo `tax_year` en la BD,
    y `amount_mxn` se calcula como amount * exchange_rate.

    Returns
    -------
    (total_deposits_mxn, total_withdrawals_mxn)
    """
    # Columna calculada amount_mxn = amount * exchange_rate
    amount_mxn_expr = Transaction.amount * Transaction.exchange_rate

    # --- Entradas (deposit + bonus) ---
    inflow_stmt = select(
        func.coalesce(func.sum(amount_mxn_expr), ZERO).label("total_in"),
    ).where(
        and_(
            Transaction.type.in_(list(INFLOW_TYPES)),
            Transaction.tax_year == tax_year,
        )
    )

    # --- Salidas (withdrawal) ---
    outflow_stmt = select(
        func.coalesce(func.sum(amount_mxn_expr), ZERO).label("total_out"),
    ).where(
        and_(
            Transaction.type.in_(list(OUTFLOW_TYPES)),
            Transaction.tax_year == tax_year,
        )
    )

    inflow_result = await db.execute(inflow_stmt)
    outflow_result = await db.execute(outflow_stmt)

    total_deposits = Decimal(str(inflow_result.scalar() or ZERO))
    total_withdrawals = Decimal(str(outflow_result.scalar() or ZERO))

    return total_deposits, total_withdrawals


# ---------------------------------------------------------------------------
# Función principal del servicio
# ---------------------------------------------------------------------------

async def get_fiscal_summary(
    db: AsyncSession,
    tax_year: int,
) -> FiscalSummaryResponse:
    """Calcula el resumen fiscal completo para el año indicado.

            - Profit neto de picks ganados (stake * odds_decimal - stake)
            - Pérdidas brutas de picks perdidos (stake)
      - Ingreso neto de apuestas
      - Total de depósitos y bonos (entradas de cash)
      - Total de retiros (salidas de cash)
      - Estimación de base imponible para el SAT

    Parameters
    ----------
    db : AsyncSession
        Sesión de base de datos asíncrona (SQLAlchemy 2.0).
    tax_year : int
        Año fiscal a consultar (ej. 2025).

    Returns
    -------
    FiscalSummaryResponse
    """
    (
        gross_winnings,
        gross_losses,
        count_won,
        count_lost,
    ) = await _aggregate_picks(db, tax_year)

    total_deposits, total_withdrawals = await _aggregate_transactions(db, tax_year)

    net_gambling_income = gross_winnings - gross_losses
    net_cashflow = total_deposits - total_withdrawals

    # Base imponible estimada: solo si hay ingreso neto positivo.
    # En México el SAT grava las ganancias netas de juegos y sorteos.
    # Si el resultado es negativo no hay obligación (aunque el contador
    # puede tener criterios adicionales).
    taxable_base = max(net_gambling_income, ZERO)

    return FiscalSummaryResponse(
        tax_year=tax_year,
        jurisdiction="MX_SAT",
        gross_winnings_mxn=gross_winnings.quantize(Decimal("0.01")),
        gross_losses_mxn=gross_losses.quantize(Decimal("0.01")),
        net_gambling_income_mxn=net_gambling_income.quantize(Decimal("0.01")),
        total_picks_won=count_won,
        total_picks_lost=count_lost,
        total_deposits_mxn=total_deposits.quantize(Decimal("0.01")),
        total_withdrawals_mxn=total_withdrawals.quantize(Decimal("0.01")),
        net_cashflow_mxn=net_cashflow.quantize(Decimal("0.01")),
        taxable_base_estimate_mxn=taxable_base.quantize(Decimal("0.01")),
        currency="MXN",
    )


# ---------------------------------------------------------------------------
# Función para el export CSV
# ---------------------------------------------------------------------------

async def get_fiscal_detail_rows(
    db: AsyncSession,
    tax_year: int,
) -> List[dict]:
    """Obtiene todas las operaciones contables del año para el CSV.

    Combina picks resueltos (won/lost/push/void) y transacciones
    del año fiscal, ordenados por fecha ascendente.

    Cada fila es un dict con las claves del CSV_HEADERS definido
    en app.schemas.fiscal.

    Returns
    -------
    List[dict]  — filas ya normalizadas, listas para csv.writer
    """
    fiscal_year_expr = case(
        (Pick.resolved_at.isnot(None), extract("year", Pick.resolved_at)),
        else_=extract("year", Pick.run_date),
    )

    fiscal_date_expr = case(
        (Pick.resolved_at.isnot(None), func.date(Pick.resolved_at)),
        else_=Pick.run_date,
    )

    # Picks resueltos del año (excluimos pending)
    picks_stmt = (
        select(Pick)
        .where(
            and_(
                Pick.status.in_([
                    PickStatus.won,
                    PickStatus.lost,
                    PickStatus.push,
                    PickStatus.void,
                ]),
                fiscal_year_expr == tax_year,
            )
        )
        .order_by(fiscal_date_expr)
    )

    # Transacciones del año
    txn_stmt = (
        select(Transaction)
        .where(Transaction.tax_year == tax_year)
        .order_by(Transaction.transaction_date)
    )

    picks_result = await db.execute(picks_stmt)
    txn_result = await db.execute(txn_stmt)

    picks = picks_result.scalars().all()
    transactions = txn_result.scalars().all()

    rows: List[dict] = []

    # --- Filas de picks ---
    for pick in picks:
        stake = pick.stake or ZERO
        odds = pick.odds_decimal or Decimal("1.0000")
        fiscal_date = (
            pick.resolved_at.date() if pick.resolved_at else pick.run_date
        )

        if pick.status == PickStatus.won:
            credit = (stake * odds).quantize(Decimal("0.01")) # Retorno total
            debit = stake.quantize(Decimal("0.01"))           # Lo que costó la apuesta
        elif pick.status == PickStatus.lost:
            credit = ZERO
            debit = stake.quantize(Decimal("0.01"))
        else:  # push / void → no hay flujo de dinero
            credit = ZERO
            debit = ZERO

        rows.append({
            "record_type": "pick",
            "fiscal_date": fiscal_date.isoformat(),
            "tax_year": tax_year,
            "description": f"Pick {pick.status.value}: {pick.selection}",
            "detail": f"{pick.market} | {pick.selection} @ {odds}",
            "debit_mxn": str(debit),
            "credit_mxn": str(credit),
            "net_mxn": str((credit - debit).quantize(Decimal("0.01"))),
            "currency": "MXN",
            "exchange_rate": "1.0000",
            "reference": str(pick.pick_id),
            "sportsbook_id": str(pick.sportsbook_id),
        })

    # --- Filas de transacciones ---
    for txn in transactions:
        amount_mxn = (txn.amount * txn.exchange_rate).quantize(Decimal("0.01"))

        if txn.type in INFLOW_TYPES:
            credit = amount_mxn
            debit = ZERO
        elif txn.type in OUTFLOW_TYPES:
            credit = ZERO
            debit = amount_mxn
        else:  # commission, void_refund → neutrales en el reporte
            credit = amount_mxn
            debit = ZERO

        rows.append({
            "record_type": "transaction",
            "fiscal_date": txn.transaction_date.isoformat(),
            "tax_year": txn.tax_year,
            "description": txn.description or f"Transacción {txn.type.value}",
            "detail": txn.type.value,
            "debit_mxn": str(debit),
            "credit_mxn": str(credit),
            "net_mxn": str((credit - debit).quantize(Decimal("0.01"))),
            "currency": txn.currency.value,
            "exchange_rate": str(txn.exchange_rate),
            "reference": txn.reference_id or txn.bank_reference or "",
            "sportsbook_id": str(txn.sportsbook_id),
        })

    # Ordenar cronológicamente el resultado combinado
    rows.sort(key=lambda r: r["fiscal_date"])

    return rows
