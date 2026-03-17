"""Pydantic schemas para el módulo de Transacciones.

Esquemas de entrada (Create/Update) y salida (Read) para la API REST.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.transaction import TransactionCurrency, TransactionType


# ---------------------------------------------------------------------------
# Schemas de Entrada (request body)
# ---------------------------------------------------------------------------

class TransactionCreate(BaseModel):
    """Payload para crear una transacción individual."""

    sportsbook_id: uuid.UUID
    type: TransactionType
    amount: Decimal = Field(..., gt=0, description="Monto en la moneda indicada")
    currency: TransactionCurrency = TransactionCurrency.MXN
    exchange_rate: Decimal = Field(
        default=Decimal("1.0000"),
        gt=0,
        description="TC respecto a MXN. Usar 1.0 si la moneda es MXN.",
    )
    transaction_date: date
    tax_year: Optional[int] = Field(
        default=None,
        description="Año fiscal. Si no se envía, se infiere de transaction_date.",
    )
    reference_id: Optional[str] = Field(None, max_length=100)
    bank_reference: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)

    @field_validator("tax_year", mode="before")
    @classmethod
    def infer_tax_year(cls, v, info):
        """Si tax_year no se provee, lo calcula desde transaction_date."""
        if v is None and "transaction_date" in info.data:
            return info.data["transaction_date"].year
        return v


class TransactionBulkCreate(BaseModel):
    """Payload para importación masiva de transacciones."""

    transactions: List[TransactionCreate] = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Lista de transacciones. Máximo 500 por request.",
    )


class TransactionUpdate(BaseModel):
    """Campos actualizables de una transacción."""

    amount: Optional[Decimal] = Field(None, gt=0)
    currency: Optional[TransactionCurrency] = None
    exchange_rate: Optional[Decimal] = Field(None, gt=0)
    transaction_date: Optional[date] = None
    tax_year: Optional[int] = None
    reference_id: Optional[str] = Field(None, max_length=100)
    bank_reference: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


# ---------------------------------------------------------------------------
# Schemas de Salida (response body)
# ---------------------------------------------------------------------------

class TransactionRead(BaseModel):
    """Representación completa de una transacción para la respuesta."""

    transaction_id: uuid.UUID
    sportsbook_id: uuid.UUID
    type: TransactionType
    amount: Decimal
    currency: TransactionCurrency
    exchange_rate: Decimal
    amount_mxn: Decimal  # Calculado: amount * exchange_rate
    transaction_date: date
    tax_year: int
    reference_id: Optional[str]
    bank_reference: Optional[str]
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    """Respuesta paginada de lista de transacciones."""

    items: List[TransactionRead]
    total: int
    page: int
    page_size: int


class TransactionBulkResponse(BaseModel):
    """Resultado de una importación masiva."""

    created: int
    failed: int
    errors: List[str] = []


# ---------------------------------------------------------------------------
# Schemas para Resumen de Flujo de Caja por Sportsbook
# ---------------------------------------------------------------------------

class SportsbookBalance(BaseModel):
    """Saldo estimado en una casa de apuestas."""

    sportsbook_id: uuid.UUID
    sportsbook_name: str
    currency: str
    total_deposits_mxn: Decimal
    total_withdrawals_mxn: Decimal
    total_bonuses_mxn: Decimal
    estimated_balance_mxn: Decimal  # deposits + bonuses - withdrawals


class CashflowSummary(BaseModel):
    """Resumen de flujo de caja consolidado."""

    period_start: date
    period_end: date
    total_in_mxn: Decimal    # depósitos + bonos
    total_out_mxn: Decimal   # retiros
    net_cashflow_mxn: Decimal
    by_sportsbook: List[SportsbookBalance]
