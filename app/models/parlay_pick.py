import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.parlay import Parlay
    from app.models.pick import Pick


class ParlayPick(Base):
    __tablename__ = "parlay_picks"

    parlay_pick_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    parlay_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("parlays.parlay_id"), nullable=False
    )
    pick_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("picks.pick_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    parlay: Mapped["Parlay"] = relationship(back_populates="parlay_picks")
    pick: Mapped["Pick"] = relationship(back_populates="parlay_picks")
