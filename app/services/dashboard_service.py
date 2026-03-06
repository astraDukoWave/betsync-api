import hashlib
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pick import Pick, PickStatus
from app.schemas.dashboard import DashboardSummary, StreakInfo, SegmentResponse
from app.services.cache_service import get_cache, set_cache

logger = logging.getLogger(__name__)


def _build_cache_key(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"dashboard:summary:{h}"


async def get_summary(
    db: AsyncSession,
    redis,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sport_id: Optional[UUID] = None,
    competition_id: Optional[UUID] = None,
    market: Optional[str] = None,
    sportsbook_id: Optional[UUID] = None,
    grade: Optional[str] = None,
    cache_ttl: int = 300,
) -> DashboardSummary:
    params = {
        "date_from": date_from, "date_to": date_to,
        "sport_id": sport_id, "competition_id": competition_id,
        "market": market, "sportsbook_id": sportsbook_id,
        "grade": grade,
    }
    cache_key = _build_cache_key(params)

    cached = await get_cache(redis, cache_key)
    if cached:
        return DashboardSummary(cache_hit=True, **cached)

    base = select(Pick)
    if date_from:
        base = base.where(Pick.run_date >= date_from)
    if date_to:
        base = base.where(Pick.run_date <= date_to)
    if market:
        base = base.where(Pick.market == market)
    if grade:
        base = base.where(Pick.grade == grade)

    total_picks = await db.scalar(
        select(func.count(Pick.pick_id)).where(base.whereclause) if base.whereclause is not None
        else select(func.count(Pick.pick_id))
    )
    total_picks = total_picks or 0

    won = await _count_status(db, base, PickStatus.won)
    lost = await _count_status(db, base, PickStatus.lost)
    push = await _count_status(db, base, PickStatus.push)
    resolved = won + lost + push

    hit_rate = round(won / (won + lost), 4) if (won + lost) > 0 else 0.0

    total_stake = await _sum_field(db, base, Pick.stake) or 0.0
    total_return = await _calc_total_return(db, base, won, lost, push)

    roi = round((total_return - total_stake) / total_stake, 4) if total_stake > 0 else 0.0

    streak = await _calc_streak(db, base)

    avg_odds_q = select(func.avg(Pick.odds_decimal))
    if base.whereclause is not None:
        avg_odds_q = avg_odds_q.where(base.whereclause)
    avg_odds = await db.scalar(avg_odds_q) or 0.0

    avg_clv_q = select(func.avg(Pick.clv)).where(Pick.clv.is_not(None))
    if base.whereclause is not None:
        avg_clv_q = avg_clv_q.where(base.whereclause)
    avg_clv = await db.scalar(avg_clv_q)

    data = {
        "total_picks": total_picks,
        "resolved_picks": resolved,
        "won": won,
        "lost": lost,
        "push": push,
        "hit_rate": hit_rate,
        "total_stake": float(total_stake),
        "total_return": float(total_return),
        "roi": roi,
        "current_streak": streak.model_dump(),
        "avg_odds_decimal": float(avg_odds),
        "avg_clv": float(avg_clv) if avg_clv is not None else None,
    }

    await set_cache(redis, cache_key, data, ttl=cache_ttl)
    return DashboardSummary(cache_hit=False, **data)


async def get_segments(
    db: AsyncSession,
    group_by: str = "selection",
) -> list[SegmentResponse]:
    group_col = getattr(Pick, group_by, Pick.selection)

    query = (
        select(
            group_col.label("segment"),
            func.count(Pick.pick_id).label("picks"),
            func.sum(case((Pick.status == PickStatus.won, 1), else_=0)).label("won"),
            func.sum(case((Pick.status == PickStatus.lost, 1), else_=0)).label("lost"),
            func.avg(Pick.odds_decimal).label("avg_odds"),
        )
        .where(Pick.status.in_([PickStatus.won, PickStatus.lost]))
        .group_by(group_col)
        .having(func.count(Pick.pick_id) >= 2)
        .order_by(desc("picks"))
        .limit(50)
    )

    result = await db.execute(query)
    segments = []
    for row in result.all():
        total = row.won + row.lost
        hit_rate = round(row.won / total, 4) if total > 0 else 0.0
        segments.append(SegmentResponse(
            segment=str(row.segment),
            picks=row.picks,
            hit_rate=hit_rate,
            roi=0.0,
            avg_odds=float(row.avg_odds or 0),
        ))
    return segments


async def _count_status(db: AsyncSession, base, status: PickStatus) -> int:
    q = select(func.count(Pick.pick_id)).where(Pick.status == status)
    if base.whereclause is not None:
        q = q.where(base.whereclause)
    return (await db.scalar(q)) or 0


async def _sum_field(db: AsyncSession, base, field):
    q = select(func.sum(field))
    if base.whereclause is not None:
        q = q.where(base.whereclause)
    return await db.scalar(q)


async def _calc_total_return(db, base, won, lost, push) -> float:
    q = select(func.sum(Pick.stake * Pick.odds_decimal)).where(Pick.status == PickStatus.won)
    if base.whereclause is not None:
        q = q.where(base.whereclause)
    won_returns = await db.scalar(q) or 0
    q2 = select(func.sum(Pick.stake)).where(Pick.status == PickStatus.push)
    if base.whereclause is not None:
        q2 = q2.where(base.whereclause)
    push_returns = await db.scalar(q2) or 0
    return float(won_returns + push_returns)


async def _calc_streak(db: AsyncSession, base) -> StreakInfo:
    q = (
        select(Pick.status)
        .where(Pick.status.in_([PickStatus.won, PickStatus.lost]))
        .order_by(Pick.resolved_at.desc().nulls_last())
        .limit(50)
    )
    if base.whereclause is not None:
        q = q.where(base.whereclause)
    result = await db.execute(q)
    statuses = [row[0] for row in result.all()]

    if not statuses:
        return StreakInfo(type="none", count=0)

    streak_type = statuses[0].value
    count = 0
    for s in statuses:
        if s.value == streak_type:
            count += 1
        else:
            break
    return StreakInfo(type=streak_type, count=count)
