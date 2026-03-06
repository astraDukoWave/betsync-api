from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class PickResult(str, enum.Enum):
    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"  # match cancelled or odds suspended
    push = "push"  # tie / returned stake


class PickGrade(str, enum.Enum):
    A = "A"   # high confidence >= 0.70
    B = "B"   # medium confidence 0.55-0.69
    C = "C"   # low confidence < 0.55


class Pick(Base):
    __tablename__ = "picks"

    id = Column(Integer, primary_key=True, index=True)
    confidence = Column(Numeric(5, 4), nullable=False)  # 0.0 - 1.0
    grade = Column(SAEnum(PickGrade), nullable=False, default=PickGrade.B)
    result = Column(SAEnum(PickResult), default=PickResult.pending)
    reasoning = Column(Text, nullable=True)  # AI / scraper justification
    suggested_stake = Column(Numeric(10, 2), nullable=True)  # e.g. 25.00 MXN
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # FKs
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    odd_id = Column(Integer, ForeignKey("odds.id"), nullable=False)

    # Relationships
    match = relationship("Match", back_populates="picks")
    odd = relationship("Odd", back_populates="picks")
    parlay_picks = relationship("ParlayPick", back_populates="pick")

    def __repr__(self):
        return f"<Pick id={self.id} grade={self.grade} confidence={self.confidence} result={self.result}>"
