from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WalletBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    available_balance: Decimal
    locked_balance: Decimal
    updated_at: datetime


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ledger_entry_id: UUID
    amount: Decimal
    type: str
    reference_id: Optional[UUID] = None
    balance_after: Decimal
    locked_after: Decimal
    created_at: datetime


class LedgerHistoryResponse(BaseModel):
    items: List[LedgerEntryResponse]
    total: int
