from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AggPickDaily(Base):
    """Daily rollup of picks keyed by run_date.

    Staleness SLA (Phase 1 shadow): populated by backfill / future workers;
    target freshness TBD when wired to mutation signals.
    """

    __tablename__ = "agg_pick_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    pick_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    won_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    lost_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    push_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    void_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_stake: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    total_profit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    total_settled_return: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    computation_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )


class AggPickDimensionDaily(Base):
    """Daily rollup partitioned by dimension (e.g. sportsbook id).

    dimension format: sb:{sportsbook_uuid}
    """

    __tablename__ = "agg_pick_dimension_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    dimension: Mapped[str] = mapped_column(String(200), primary_key=True)
    pick_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_stake: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    total_profit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    total_settled_return: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    computation_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )
