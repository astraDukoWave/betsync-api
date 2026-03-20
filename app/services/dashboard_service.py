import hashlib
import json
import logging
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, case, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.aggregates import AggPickDaily
from app.models.pick import Pick, PickStatus
from app.schemas.dashboard import DashboardSummary, StreakInfo, SegmentResponse
from app.services.aggregate_read_gate import redis_blocks_aggregate_reads
from app.services.cache_service import get_cache, set_cache

logger = logging.getLogger(__name__)

# TODO: Cleanup - Raw queries retained for rollback safety. Removal only after 30 days of stability.

_RAW_DAY_PROFIT_SQL = """
    COALESCE(SUM(
        CASE
            WHEN profit IS NOT NULL THEN profit
            WHEN status::text = 'void' OR status::text = 'pending' THEN 0::numeric
            WHEN stake IS NULL THEN 0::numeric
            WHEN status::text = 'won' THEN stake * odds_decimal - stake
            WHEN status::text = 'lost' THEN -stake
            WHEN status::text = 'push' THEN 0::numeric
            ELSE 0::numeric
        END
    ), 0)
"""

AGG_STALENESS_MAX = timedelta(minutes=10)
DUAL_READ_SAMPLE_RATE = 0.01


def _days_inclusive(date_from: date, date_to: date) -> list[date]:
    out: list[date] = []
    d = date_from
    while d <= date_to:
        out.append(d)
        d += timedelta(days=1)
    return out


def _dashboard_summary_agg_tables_eligible(
    date_from: Optional[date],
    date_to: Optional[date],
    market: Optional[str],
    grade: Optional[str],
) -> bool:
    """agg_pick_daily is global per day; only safe when summary filters match that grain."""
    if date_from is None or date_to is None:
        return False
    if market is not None:
        return False
    if grade is not None:
        return False
    return True


def _trigger_agg_fallback(reason: str) -> None:
    if reason == "stale_data":
        logger.error(
            "agg_pick_daily data exceeded staleness SLA; using raw picks path"
        )
    logger.warning("[AGG_FALLBACK_TRIGGERED] reason:%s", reason)


def _validate_agg_pick_daily_rows(
    rows: list[AggPickDaily],
    expected_days: list[date],
) -> Optional[str]:
    """Return None if OK, else missing_days or stale_data."""
    expected_set = set(expected_days)
    got_days = {r.day for r in rows}
    if expected_set != got_days:
        return "missing_days"
    now = datetime.now(timezone.utc)
    max_u = max(rows, key=lambda r: r.updated_at).updated_at
    if max_u.tzinfo is None:
        max_u = max_u.replace(tzinfo=timezone.utc)
    if now - max_u > AGG_STALENESS_MAX:
        return "stale_data"
    return None


def _totals_dict_from_agg_rows(rows: list[AggPickDaily]) -> dict:
    total_picks = sum(int(r.pick_count) for r in rows)
    ts = sum(
        (r.total_stake if r.total_stake is not None else Decimal("0")) for r in rows
    )
    tr = sum(
        (r.total_settled_return if r.total_settled_return is not None else Decimal("0"))
        for r in rows
    )
    tpf = sum(
        (r.total_profit if r.total_profit is not None else Decimal("0")) for r in rows
    )
    roi = round(float(tpf / ts), 4) if ts > 0 else 0.0
    return {
        "total_picks": total_picks,
        "total_stake": float(ts),
        "total_return": float(tr),
        "roi": roi,
    }


async def _fetch_agg_pick_daily_for_range(
    db: AsyncSession,
    date_from: date,
    date_to: date,
) -> list[AggPickDaily]:
    stmt = (
        select(AggPickDaily)
        .where(AggPickDaily.day >= date_from, AggPickDaily.day <= date_to)
        .order_by(AggPickDaily.day)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _maybe_log_agg_pick_daily_mismatch(
    db: AsyncSession,
    day: date,
) -> None:
    """Sampled validation: compare unfiltered single-day raw rollups vs agg_pick_daily."""
    raw_stmt = text(
        f"SELECT COUNT(*)::int AS cnt, {_RAW_DAY_PROFIT_SQL} AS profit_sum "
        "FROM picks WHERE run_date = :day"
    )
    row = (await db.execute(raw_stmt, {"day": day})).one()
    raw_cnt = int(row.cnt)
    raw_profit = row.profit_sum if row.profit_sum is not None else Decimal("0")
    if not isinstance(raw_profit, Decimal):
        raw_profit = Decimal(str(raw_profit))

    agg_row = await db.get(AggPickDaily, day)
    agg_cnt = int(agg_row.pick_count) if agg_row else 0
    if agg_row is not None and agg_row.total_profit is not None:
        agg_profit = agg_row.total_profit
    else:
        agg_profit = Decimal("0")
    if not isinstance(agg_profit, Decimal):
        agg_profit = Decimal(str(agg_profit))

    profit_delta = raw_profit - agg_profit
    count_delta = raw_cnt - agg_cnt
    if abs(profit_delta) > Decimal("0.01") or count_delta != 0:
        logger.warning(
            "[DUAL_READ_MISMATCH] day:%s raw:%s agg:%s delta:%s",
            day.isoformat(),
            {"pick_count": raw_cnt, "total_profit": str(raw_profit)},
            {"pick_count": agg_cnt, "total_profit": str(agg_profit)},
            {
                "pick_count": count_delta,
                "total_profit": str(profit_delta),
            },
        )


def _build_cache_key(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"dashboard:summary:{h}"


def _pick_base_for_summary(
    date_from: Optional[date],
    date_to: Optional[date],
    market: Optional[str],
    grade: Optional[str],
):
    base = select(Pick)
    if date_from:
        base = base.where(Pick.run_date >= date_from)
    if date_to:
        base = base.where(Pick.run_date <= date_to)
    if market:
        base = base.where(Pick.market == market)
    if grade:
        base = base.where(Pick.grade == grade)
    return base


async def _compute_raw_summary_data(db: AsyncSession, base) -> dict:
    # TODO: Cleanup - Raw queries retained for rollback safety. Removal only after 30 days of stability.
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

    roi = round((float(total_return) - float(total_stake)) / float(total_stake), 4) if total_stake > 0 else 0.0

    streak = await _calc_streak(db, base)

    avg_odds_q = select(func.avg(Pick.odds_decimal))
    if base.whereclause is not None:
        avg_odds_q = avg_odds_q.where(base.whereclause)
    avg_odds = await db.scalar(avg_odds_q) or 0.0

    avg_clv_q = select(func.avg(Pick.clv)).where(Pick.clv.is_not(None))
    if base.whereclause is not None:
        avg_clv_q = avg_clv_q.where(base.whereclause)
    avg_clv = await db.scalar(avg_clv_q)

    return {
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

    sample_dual_read = random.random() < DUAL_READ_SAMPLE_RATE

    base = _pick_base_for_summary(date_from, date_to, market, grade)

    env_agg = settings.use_aggregates_for_dashboard
    redis_blocked = await redis_blocks_aggregate_reads(redis)
    if env_agg and redis_blocked:
        logger.warning("[AGG_FALLBACK_TRIGGERED] reason:runtime_toggle")
    use_agg_reads = env_agg and not redis_blocked

    agg_eligible = _dashboard_summary_agg_tables_eligible(
        date_from, date_to, market, grade,
    )

    if (
        agg_eligible
        and use_agg_reads
        and date_from is not None
        and date_to is not None
    ):
        expected_days = _days_inclusive(date_from, date_to)
        rows = await _fetch_agg_pick_daily_for_range(db, date_from, date_to)
        vreason = _validate_agg_pick_daily_rows(rows, expected_days)
        if vreason is None:
            data = await _compute_raw_summary_data(db, base)
            data.update(_totals_dict_from_agg_rows(rows))
            resolved = data["won"] + data["lost"] + data["push"]
            data["resolved_picks"] = resolved
            if (
                sample_dual_read
                and date_from == date_to
                and market is None
                and grade is None
            ):
                await _maybe_log_agg_pick_daily_mismatch(db, date_from)
            await set_cache(redis, cache_key, data, ttl=cache_ttl)
            return DashboardSummary(cache_hit=False, **data)
        _trigger_agg_fallback(vreason)

    data = await _compute_raw_summary_data(db, base)

    if sample_dual_read and (
        date_from is not None
        and date_to is not None
        and date_from == date_to
        and market is None
        and grade is None
    ):
        await _maybe_log_agg_pick_daily_mismatch(db, date_from)

    await set_cache(redis, cache_key, data, ttl=cache_ttl)
    return DashboardSummary(cache_hit=False, **data)


async def get_segments(
    db: AsyncSession,
    group_by: str = "selection",
) -> list[SegmentResponse]:
    # TODO: Cleanup - Raw queries retained for rollback safety. Removal only after 30 days of stability.
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
