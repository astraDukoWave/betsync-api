import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Date, DateTime, Numeric, ForeignKey, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sportsbook import Sportsbook
    from app.models.parlay_pick import ParlayPick


class ParlayStatus(str, enum.Enum):
    pending = "pending"
    won = "won"
    lost = "lost"


class ParlayType(str, enum.Enum):
    regular = "regular"
    bonus = "bonus"


class Parlay(Base):
    __tablename__ = "parlays"

    parlay_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sportsbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sportsbooks.sportsbook_id"), nullable=False
    )
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[ParlayType] = mapped_column(
        SAEnum(ParlayType, name="parlay_type"), default=ParlayType.regular
    )
    stake: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    odds_total: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    potential_return: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    actual_return: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[ParlayStatus] = mapped_column(
        SAEnum(ParlayStatus, name="parlay_status"), default=ParlayStatus.pending
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sportsbook: Mapped["Sportsbook"] = relationship(back_populates="parlays")
    parlay_picks: Mapped[List["ParlayPick"]] = relationship(back_populates="parlay")
