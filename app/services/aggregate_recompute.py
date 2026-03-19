"""Synchronous full-day recompute for agg_pick_daily / agg_pick_dimension_daily."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.aggregates import AggPickDaily, AggPickDimensionDaily
from app.models.pick import Pick, PickStatus
from app.services.pick_service import _settlement_for_status

COMPUTATION_VERSION = 1


def _dimension_key(sportsbook_id: UUID) -> str:
    return f"sb:{sportsbook_id}"


def pick_row_contribution(p: Pick) -> dict[str, Any]:
    stake_amt = p.stake if p.stake is not None else Decimal("0")
    profit = p.profit
    settled_return = p.settled_return
    if (
        profit is None
        and settled_return is None
        and p.status != PickStatus.pending
    ):
        settled_return, profit = _settlement_for_status(
            p.status, p.stake, p.odds_decimal
        )
    profit_contrib = profit if profit is not None else Decimal("0")
    return_contrib = settled_return if settled_return is not None else Decimal("0")
    return {
        "pick_count": 1,
        "total_stake": stake_amt,
        "total_profit": profit_contrib,
        "total_settled_return": return_contrib,
    }


def recompute_pick_aggregates_for_day_sync(session, run_date: date) -> None:
    """Replace aggregate rows for run_date from a full scan of picks that day (UPSERT)."""
    picks = list(
        session.execute(select(Pick).where(Pick.run_date == run_date)).scalars().all()
    )

    daily_totals: dict[str, Any] = {
        "pick_count": 0,
        "total_stake": Decimal("0"),
        "total_profit": Decimal("0"),
        "total_settled_return": Decimal("0"),
    }
    dim_totals: dict[tuple[date, str], dict[str, Any]] = defaultdict(
        lambda: {
            "pick_count": 0,
            "total_stake": Decimal("0"),
            "total_profit": Decimal("0"),
            "total_settled_return": Decimal("0"),
        }
    )

    for p in picks:
        c = pick_row_contribution(p)
        daily_totals["pick_count"] += c["pick_count"]
        daily_totals["total_stake"] += c["total_stake"]
        daily_totals["total_profit"] += c["total_profit"]
        daily_totals["total_settled_return"] += c["total_settled_return"]

        key = (run_date, _dimension_key(p.sportsbook_id))
        b = dim_totals[key]
        b["pick_count"] += c["pick_count"]
        b["total_stake"] += c["total_stake"]
        b["total_profit"] += c["total_profit"]
        b["total_settled_return"] += c["total_settled_return"]

    session.execute(
        delete(AggPickDimensionDaily).where(AggPickDimensionDaily.day == run_date)
    )

    daily_row = {
        "day": run_date,
        "pick_count": daily_totals["pick_count"],
        "total_stake": daily_totals["total_stake"],
        "total_profit": daily_totals["total_profit"],
        "total_settled_return": daily_totals["total_settled_return"],
        "computation_version": COMPUTATION_VERSION,
    }
    ins_d = insert(AggPickDaily).values(daily_row)
    ins_d = ins_d.on_conflict_do_update(
        index_elements=[AggPickDaily.day],
        set_={
            "pick_count": ins_d.excluded.pick_count,
            "total_stake": ins_d.excluded.total_stake,
            "total_profit": ins_d.excluded.total_profit,
            "total_settled_return": ins_d.excluded.total_settled_return,
            "computation_version": ins_d.excluded.computation_version,
            "updated_at": func.now(),
        },
    )
    session.execute(ins_d)

    for (day, dim), m in dim_totals.items():
        row = {
            "day": day,
            "dimension": dim,
            "pick_count": m["pick_count"],
            "total_stake": m["total_stake"],
            "total_profit": m["total_profit"],
            "total_settled_return": m["total_settled_return"],
            "computation_version": COMPUTATION_VERSION,
        }
        ins_dim = insert(AggPickDimensionDaily).values(row)
        ins_dim = ins_dim.on_conflict_do_update(
            index_elements=[
                AggPickDimensionDaily.day,
                AggPickDimensionDaily.dimension,
            ],
            set_={
                "pick_count": ins_dim.excluded.pick_count,
                "total_stake": ins_dim.excluded.total_stake,
                "total_profit": ins_dim.excluded.total_profit,
                "total_settled_return": ins_dim.excluded.total_settled_return,
                "computation_version": ins_dim.excluded.computation_version,
                "updated_at": func.now(),
            },
        )
        session.execute(ins_dim)
