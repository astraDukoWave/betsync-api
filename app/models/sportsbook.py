import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.pick import Pick
    from app.models.parlay import Parlay


class Sportsbook(Base):
    __tablename__ = "sportsbooks"

    sportsbook_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="MXN")
    odds_format_default: Mapped[str] = mapped_column(String(20), default="american")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    picks: Mapped[List["Pick"]] = relationship(back_populates="sportsbook")
    parlays: Mapped[List["Parlay"]] = relationship(back_populates="sportsbook")
