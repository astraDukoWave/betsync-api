import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sport import Sport
    from app.models.match import Match


class Competition(Base):
    __tablename__ = "competitions"

    competition_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sport_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sports.sport_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(1), default="A")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sport: Mapped["Sport"] = relationship(back_populates="competitions")
    matches: Mapped[List["Match"]] = relationship(back_populates="competition")
