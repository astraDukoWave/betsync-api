from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    created_at: datetime


class ReconciliationAnomaliesResponse(BaseModel):
    items: list[ReconciliationAuditRowSchema] = Field(default_factory=list)
