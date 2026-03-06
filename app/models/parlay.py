from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class ParlayStatus(str, enum.Enum):
    open = "open"       # picks still pending
    won = "won"
    lost = "lost"
    partial = "partial"  # some picks won, some lost
    void = "void"


class Parlay(Base):
    __tablename__ = "parlays"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=True)  # e.g. "Ticket A - 2025-06-20"
    stake = Column(Numeric(10, 2), nullable=False, default=75.00)  # $75 MXN default
    total_odds = Column(Numeric(10, 3), nullable=True)  # product of all odds
    potential_payout = Column(Numeric(10, 2), nullable=True)
    actual_payout = Column(Numeric(10, 2), nullable=True)
    status = Column(SAEnum(ParlayStatus), default=ParlayStatus.open)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parlay_picks = relationship("ParlayPick", back_populates="parlay", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Parlay id={self.id} stake={self.stake} status={self.status} total_odds={self.total_odds}>"


class ParlayPick(Base):
    """Association table: many-to-many between Parlay and Pick"""
    __tablename__ = "parlay_picks"

    id = Column(Integer, primary_key=True, index=True)
    position = Column(Integer, default=1)  # order in the parlay ticket
    created_at = Column(DateTime, default=datetime.utcnow)

    # FKs
    parlay_id = Column(Integer, ForeignKey("parlays.id"), nullable=False)
    pick_id = Column(Integer, ForeignKey("picks.id"), nullable=False)

    # Relationships
    parlay = relationship("Parlay", back_populates="parlay_picks")
    pick = relationship("Pick", back_populates="parlay_picks")

    def __repr__(self):
        return f"<ParlayPick parlay_id={self.parlay_id} pick_id={self.pick_id} position={self.position}>"
