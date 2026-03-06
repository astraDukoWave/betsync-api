from pydantic import BaseModel
from typing import Optional


class PickStats(BaseModel):
    won: int
    lost: int
    pending: int
    void: int
    push: int
    win_rate: float


class ParlayStats(BaseModel):
    total: int
    won: int
    lost: int
    pending: int
    win_rate: float


class ROIStats(BaseModel):
    total_staked: float
    total_returns: float
    roi_percent: float


class DashboardSummary(BaseModel):
    total_picks: int
    total_parlays: int
    pick_stats: PickStats
    parlay_stats: ParlayStats
    roi: Optional[ROIStats] = None

    class Config:
        from_attributes = True
