from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.core.database import Base


class MatchStatus(str, enum.Enum):
    scheduled = "scheduled"
    live = "live"
    finished = "finished"
    postponed = "postponed"
    cancelled = "cancelled"


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(100), unique=True, nullable=True)
    home_team = Column(String(200), nullable=False)
    away_team = Column(String(200), nullable=False)
    match_date = Column(DateTime, nullable=False)
    status = Column(SAEnum(MatchStatus), default=MatchStatus.scheduled)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # FK
    competition_id = Column(Integer, ForeignKey("competitions.id"), nullable=False)

    # Relationships
    competition = relationship("Competition", back_populates="matches")
    odds = relationship("Odd", back_populates="match", cascade="all, delete-orphan")
    picks = relationship("Pick", back_populates="match", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Match id={self.id} {self.home_team} vs {self.away_team} {self.match_date}>"
