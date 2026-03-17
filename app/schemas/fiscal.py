"""Pydantic schemas para el Motor Fiscal (Fiscal Engine) de BetSync.

Contiene los schemas de respuesta para el resumen fiscal anual
y las estructuras auxiliares para el export CSV al contador.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schema principal de resumen fiscal
# ---------------------------------------------------------------------------

class FiscalSummaryResponse(BaseModel):
    """Resumen fiscal consolidado para un año tributario.

    Diseñado para cumplir con los requisitos del SAT (México).
    Todos los montos están expresados en MXN.
    """
    tax_year: int = Field(..., description="Año fiscal (YYYY)")
    jurisdiction: str = Field(default="MX_SAT", description="Jurisdicción fiscal")

    # --- Picks: ganancias y pérdidas de apuestas ---
    gross_winnings_mxn: Decimal = Field(
        ...,
        description="Suma de (stake * odds_decimal) de picks ganados en el año fiscal",
    )
    gross_losses_mxn: Decimal = Field(
        ...,
        description="Suma del stake de picks perdidos en el año fiscal",
    )
    net_gambling_income_mxn: Decimal = Field(
        ...,
        description="gross_winnings - gross_losses (puede ser negativo)",
    )
    total_picks_won: int = Field(..., description="Número de picks ganados")
    total_picks_lost: int = Field(..., description="Número de picks perdidos")

    # --- Transacciones: flujo de caja real ---
    total_deposits_mxn: Decimal = Field(
        ...,
        description="Suma de transacciones tipo deposit + bonus (monto * exchange_rate)",
    )
    total_withdrawals_mxn: Decimal = Field(
        ...,
        description="Suma de transacciones tipo withdrawal (monto * exchange_rate)",
    )
    net_cashflow_mxn: Decimal = Field(
        ...,
        description="total_deposits - total_withdrawals",
    )

    # --- Base imponible estimada ---
    taxable_base_estimate_mxn: Decimal = Field(
        ...,
        description=(
            "Estimación de base imponible: max(net_gambling_income, 0). "
            "Consultar con un contador para la cifra definitiva."
        ),
    )

    currency: str = Field(default="MXN", description="Moneda base de todos los montos")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Schemas auxiliares para el export CSV
# ---------------------------------------------------------------------------

class FiscalPickRow(BaseModel):
    """Fila de un pick resuelto para el reporte fiscal CSV."""
    record_type: str = "pick"
    fiscal_date: date
    tax_year: int
    description: str
    market: str
    selection: str
    stake_mxn: Optional[Decimal]
    odds_decimal: Optional[Decimal]
    gross_amount_mxn: Optional[Decimal]  # stake * odds si won, stake si lost
    outcome: str  # won / lost / push / void
    sportsbook_id: str


class FiscalTransactionRow(BaseModel):
    """Fila de una transacción para el reporte fiscal CSV."""
    record_type: str = "transaction"
    fiscal_date: date
    tax_year: int
    description: str
    transaction_type: str
    amount_original: Decimal
    currency: str
    exchange_rate: Decimal
    amount_mxn: Decimal
    reference_id: Optional[str]
    bank_reference: Optional[str]
    sportsbook_id: str


# Cabeceras canónicas del CSV exportable
CSV_HEADERS = [
    "record_type",
    "fiscal_date",
    "tax_year",
    "description",
    "detail",          # market+selection para picks / tipo para transacciones
    "debit_mxn",       # salidas: stake perdido / retiro
    "credit_mxn",      # entradas: ganancia / depósito / bono
    "net_mxn",         # credit - debit
    "currency",
    "exchange_rate",
    "reference",
    "sportsbook_id",
]
