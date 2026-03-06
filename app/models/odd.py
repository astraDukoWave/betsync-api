from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Numeric, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class OddType(str, enum.Enum):
    moneyline = "moneyline"   # 1X2
    handicap = "handicap"     # Asian/European handicap
    over_under = "over_under" # totals
    btts = "btts"             # both teams to score
    correct_score = "correct_score"


class Odd(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True, index=True)
    odd_type = Column(SAEnum(OddType), nullable=False)
    label = Column(String(50), nullable=False)  # e.g. "home", "draw", "away", "over 2.5"
    value = Column(Numeric(6, 3), nullable=False)  # decimal odds e.g. 1.850
    bookmaker = Column(String(100), default="Betmaster")
    market_line = Column(Numeric(5, 2), nullable=True)  # e.g. 2.5 for over/under
    is_open = Column(Integer, default=1)  # 1=open, 0=suspended
    fetched_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # FK
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)

    # Relationships
    match = relationship("Match", back_populates="odds")
    picks = relationship("Pick", back_populates="odd")

    def __repr__(self):
        return f"<Odd id={self.id} type={self.odd_type} label={self.label} value={self.value}>"
