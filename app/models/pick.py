import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    String, Integer, Date, DateTime, Numeric, ForeignKey, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.match import Match
    from app.models.sportsbook import Sportsbook
    from app.models.parlay_pick import ParlayPick


class PickStatus(str, enum.Enum):
    pending = "pending"
    won = "won"
    lost = "lost"
    push = "push"
    void = "void"


class PickGrade(str, enum.Enum):
    A = "A"
    B = "B"
    C = "C"


class PickSource(str, enum.Enum):
    manual = "manual"
    pipeline = "pipeline"


class Pick(Base):
    __tablename__ = "picks"

    pick_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("matches.match_id"), nullable=False
    )
    sportsbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sportsbooks.sportsbook_id"), nullable=False
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    selection: Mapped[str] = mapped_column(String(200), nullable=False)
    odds_american: Mapped[int] = mapped_column(Integer, nullable=False)
    odds_decimal: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    implied_prob: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    grade: Mapped[PickGrade] = mapped_column(SAEnum(PickGrade, name="pick_grade"))
    stake: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[PickStatus] = mapped_column(
        SAEnum(PickStatus, name="pick_status"), default=PickStatus.pending
    )
    source: Mapped[PickSource] = mapped_column(
        SAEnum(PickSource, name="pick_source"), default=PickSource.manual
    )
    closing_odds_decimal: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(6, 4), nullable=True
    )
    clv: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    match: Mapped["Match"] = relationship(back_populates="picks")
    sportsbook: Mapped["Sportsbook"] = relationship(back_populates="picks")
    parlay_picks: Mapped[List["ParlayPick"]] = relationship(back_populates="pick")
