from typing import Optional

from pydantic import BaseModel


class StreakInfo(BaseModel):
    type: str
    count: int


class DashboardSummary(BaseModel):
    total_picks: int
    resolved_picks: int
    won: int
    lost: int
    push: int
    hit_rate: float
    total_stake: float
    total_return: float
    roi: float
    current_streak: StreakInfo
    avg_odds_decimal: float
    avg_clv: Optional[float] = None
    cache_hit: bool = False


class SegmentResponse(BaseModel):
    segment: str
    picks: int
    hit_rate: float
    roi: float
    avg_odds: float
