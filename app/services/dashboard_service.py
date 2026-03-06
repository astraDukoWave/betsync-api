from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.pick import Pick, PickResult
from app.models.parlay import Parlay
from app.schemas.dashboard import PickStats, ParlayStats, ROIStats, DashboardSummary


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pick_stats(self) -> PickStats:
        """Aggregate pick results from DB."""
        results = {}
        for result in ["won", "lost", "pending", "void", "push"]:
            count = await self.db.scalar(
                select(func.count(Pick.id)).where(Pick.result == result)
            )
            results[result] = count or 0

        total = results["won"] + results["lost"]
        win_rate = round(results["won"] / total * 100, 2) if total > 0 else 0.0
        return PickStats(win_rate=win_rate, **results)

    async def get_parlay_stats(self) -> ParlayStats:
        """Aggregate parlay results from DB."""
        total = await self.db.scalar(select(func.count(Parlay.id))) or 0
        won = await self.db.scalar(
            select(func.count(Parlay.id)).where(Parlay.result == "won")
        ) or 0
        lost = await self.db.scalar(
            select(func.count(Parlay.id)).where(Parlay.result == "lost")
        ) or 0
        pending = await self.db.scalar(
            select(func.count(Parlay.id)).where(Parlay.result == "pending")
        ) or 0
        settled = won + lost
        win_rate = round(won / settled * 100, 2) if settled > 0 else 0.0
        return ParlayStats(total=total, won=won, lost=lost, pending=pending, win_rate=win_rate)

    async def get_summary(self) -> DashboardSummary:
        """Build full dashboard summary."""
        total_picks = await self.db.scalar(select(func.count(Pick.id))) or 0
        total_parlays = await self.db.scalar(select(func.count(Parlay.id))) or 0
        pick_stats = await self.get_pick_stats()
        parlay_stats = await self.get_parlay_stats()
        return DashboardSummary(
            total_picks=total_picks,
            total_parlays=total_parlays,
            pick_stats=pick_stats,
            parlay_stats=parlay_stats,
        )
