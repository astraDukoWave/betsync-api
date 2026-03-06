from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.pick import PickGrade, PickSource, PickStatus


class PickCreate(BaseModel):
    match_id: UUID
    sportsbook_id: UUID
    market: str
    selection: str
    odds_american: int
    stake: Optional[Decimal] = None
    grade: Optional[PickGrade] = None
    source: PickSource = PickSource.manual

    @model_validator(mode="after")
    def validate_odds(self):
        if -100 < self.odds_american < 100:
            raise ValueError("odds_american invalid: must be <= -100 or >= 100")
        return self


class PickUpdate(BaseModel):
    market: Optional[str] = None
    selection: Optional[str] = None
    odds_american: Optional[int] = None
    stake: Optional[Decimal] = None
    grade: Optional[PickGrade] = None

    @model_validator(mode="after")
    def validate_odds(self):
        if self.odds_american is not None and -100 < self.odds_american < 100:
            raise ValueError("odds_american invalid: must be <= -100 or >= 100")
        return self


class PickResolve(BaseModel):
    status: PickStatus
    closing_odds_decimal: Optional[Decimal] = None

    @model_validator(mode="after")
    def validate_not_pending(self):
        if self.status == PickStatus.pending:
            raise ValueError("Cannot resolve a pick to 'pending' status")
        return self


class PickConfirm(BaseModel):
    confirmed: bool


class PickResponse(BaseModel):
    pick_id: UUID
    match_id: UUID
    sportsbook_id: UUID
    run_date: date
    market: str
    selection: str
    odds_american: int
    odds_decimal: Decimal
    implied_prob: Decimal
    grade: PickGrade
    stake: Optional[Decimal] = None
    status: PickStatus
    source: PickSource
    closing_odds_decimal: Optional[Decimal] = None
    clv: Optional[Decimal] = None
    confirmed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PickListResponse(BaseModel):
    items: list[PickResponse]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total
