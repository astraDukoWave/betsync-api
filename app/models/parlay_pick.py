from sqlalchemy import Column, Integer, ForeignKey, Numeric, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class ParlayPickResult(str, enum.Enum):
    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"
    push = "push"


class ParlayPick(Base):
    """Association table between Parlay and Pick with per-leg metadata."""
    __tablename__ = "parlay_picks"

    id = Column(Integer, primary_key=True, index=True)
    parlay_id = Column(Integer, ForeignKey("parlays.id", ondelete="CASCADE"), nullable=False, index=True)
    pick_id = Column(Integer, ForeignKey("picks.id", ondelete="CASCADE"), nullable=False, index=True)
    odds_at_entry = Column(Numeric(8, 2), nullable=True)
    result = Column(SAEnum(ParlayPickResult), default=ParlayPickResult.pending, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    parlay = relationship("Parlay", back_populates="parlay_picks")
    pick = relationship("Pick", back_populates="parlay_picks")

    def __repr__(self) -> str:
        return f"<ParlayPick(parlay={self.parlay_id}, pick={self.pick_id}, result={self.result})>"
