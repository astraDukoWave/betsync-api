from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    country = Column(String(100), nullable=False)
    region = Column(String(50), nullable=False, default="global")  # global, europe, americas, asia
    tier = Column(Integer, default=1)  # 1=top, 2=second, 3=cup
    external_id = Column(String(100), unique=True, nullable=True)  # e.g. football-api league id
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # FK
    sport_id = Column(Integer, ForeignKey("sports.id"), nullable=False)

    # Relationships
    sport = relationship("Sport", back_populates="competitions")
    matches = relationship("Match", back_populates="competition", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Competition id={self.id} name={self.name} country={self.country}>"
