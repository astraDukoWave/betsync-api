from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class TaskStatus(BaseModel):
    task_id: str
    status: str  # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TriggerResponse(BaseModel):
    message: str
    task_id: str


class OddsFetchResult(BaseModel):
    fetched_at: datetime
    matches_processed: int
    odds_updated: int
    errors: int


class SettlementResult(BaseModel):
    settled_at: datetime
    picks_settled: int
    parlays_settled: int
    errors: int
