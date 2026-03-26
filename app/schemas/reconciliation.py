from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReconciliationFixResponse(BaseModel):
    user_id: UUID
    drift_type_before: Literal[
        "NONE",
        "ESCROW_MISMATCH",
        "LEDGER_MISMATCH",
        "FULL_INCONSISTENT",
    ]
    repaired: bool
    previous_available: Decimal
    previous_locked: Decimal
    new_available: Decimal
    new_locked: Decimal


class ReconciliationResultSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    escrow_expected: Decimal
    escrow_actual: Decimal
    ledger_expected: Decimal
    ledger_actual: Decimal
    escrow_drift: Decimal
    ledger_drift: Decimal
    severity: Literal["OK", "WARNING", "CRITICAL"]


class ReconciliationSummarySchema(BaseModel):
    total_users: int
    ok_users: int
    warning_users: int
    critical_users: int
    anomalies: list[ReconciliationResultSchema]
    duration_seconds: float


class ReconciliationAuditRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    escrow_drift: Decimal
    ledger_drift: Decimal
    severity: str
    detail: dict[str, Any] | None = None
    created_at: datetime


class ReconciliationAnomaliesResponse(BaseModel):
    items: list[ReconciliationAuditRowSchema] = Field(default_factory=list)


class FinancialHealthSummarySchema(BaseModel):
    """Global reconciliation counts (read-only scan, no audit persistence)."""

    total_users: int
    ok_users: int
    warning_users: int
    critical_users: int
