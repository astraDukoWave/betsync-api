"""
High-throughput backfill for agg_pick_daily and agg_pick_dimension_daily.

- Truncates aggregate tables by default so a full re-run is idempotent.
- Processes picks in batches of 1_000 ordered by pick_id (keyset pagination).
- Upserts with PostgreSQL ON CONFLICT ... DO UPDATE (additive merge per key).

Env: DATABASE_URL_SYNC (postgresql+psycopg2://...) or default from app settings.
"""
from __future__ import annotations

import argparse
import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SyncSessionLocal
from app.models.aggregates import AggPickDaily, AggPickDimensionDaily
from app.models.pick import Pick, PickStatus
from app.services.pick_service import _settlement_for_status

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
COMPUTATION_VERSION = 1

_STATUS_COUNT_KEYS = (
    "won_count",
    "lost_count",
    "push_count",
    "pending_count",
    "void_count",
)
_STATUS_TO_COUNT_KEY = {
    PickStatus.won: "won_count",
    PickStatus.lost: "lost_count",
    PickStatus.push: "push_count",
    PickStatus.pending: "pending_count",
    PickStatus.void: "void_count",
}


def _dimension_key(sportsbook_id: UUID) -> str:
    return f"sb:{sportsbook_id}"


def _pick_row_contribution(p: Pick) -> dict[str, Any]:
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
    sk = _STATUS_TO_COUNT_KEY[p.status]
    row = {
        "pick_count": 1,
        "total_stake": stake_amt,
        "total_profit": profit_contrib,
        "total_settled_return": return_contrib,
    }
    for k in _STATUS_COUNT_KEYS:
        row[k] = 1 if k == sk else 0
    return row


def _merge(
    target: dict[Any, dict[str, Any]], key: Any, contrib: dict[str, Any]
) -> None:
    if key not in target:
        target[key] = {
            "pick_count": 0,
            "total_stake": Decimal("0"),
            "total_profit": Decimal("0"),
            "total_settled_return": Decimal("0"),
            **{k: 0 for k in _STATUS_COUNT_KEYS},
        }
    b = target[key]
    b["pick_count"] += contrib["pick_count"]
    b["total_stake"] += contrib["total_stake"]
    b["total_profit"] += contrib["total_profit"]
    b["total_settled_return"] += contrib["total_settled_return"]
    for k in _STATUS_COUNT_KEYS:
        b[k] += contrib[k]


def _flush_daily(session, rows: dict[Any, dict[str, Any]]) -> None:
    if not rows:
        return
    values = [
        {
            "day": day,
            "pick_count": m["pick_count"],
            "total_stake": m["total_stake"],
            "total_profit": m["total_profit"],
            "total_settled_return": m["total_settled_return"],
            "computation_version": COMPUTATION_VERSION,
            **{k: m[k] for k in _STATUS_COUNT_KEYS},
        }
        for day, m in rows.items()
    ]
    ins = insert(AggPickDaily).values(values)
    ins = ins.on_conflict_do_update(
        index_elements=[AggPickDaily.day],
        set_={
            "pick_count": AggPickDaily.pick_count + ins.excluded.pick_count,
            "total_stake": AggPickDaily.total_stake + ins.excluded.total_stake,
            "total_profit": AggPickDaily.total_profit + ins.excluded.total_profit,
            "total_settled_return": AggPickDaily.total_settled_return
            + ins.excluded.total_settled_return,
            "computation_version": ins.excluded.computation_version,
            "updated_at": func.now(),
            "won_count": AggPickDaily.won_count + ins.excluded.won_count,
            "lost_count": AggPickDaily.lost_count + ins.excluded.lost_count,
            "push_count": AggPickDaily.push_count + ins.excluded.push_count,
            "pending_count": AggPickDaily.pending_count + ins.excluded.pending_count,
            "void_count": AggPickDaily.void_count + ins.excluded.void_count,
        },
    )
    session.execute(ins)


def _flush_dimension(session, rows: dict[Any, dict[str, Any]]) -> None:
    if not rows:
        return
    values = [
        {
            "day": day,
            "dimension": dim,
            "pick_count": m["pick_count"],
            "total_stake": m["total_stake"],
            "total_profit": m["total_profit"],
            "total_settled_return": m["total_settled_return"],
            "computation_version": COMPUTATION_VERSION,
        }
        for (day, dim), m in rows.items()
    ]
    ins = insert(AggPickDimensionDaily).values(values)
    ins = ins.on_conflict_do_update(
        index_elements=[AggPickDimensionDaily.day, AggPickDimensionDaily.dimension],
        set_={
            "pick_count": AggPickDimensionDaily.pick_count + ins.excluded.pick_count,
            "total_stake": AggPickDimensionDaily.total_stake
            + ins.excluded.total_stake,
            "total_profit": AggPickDimensionDaily.total_profit
            + ins.excluded.total_profit,
            "total_settled_return": AggPickDimensionDaily.total_settled_return
            + ins.excluded.total_settled_return,
            "computation_version": ins.excluded.computation_version,
            "updated_at": func.now(),
        },
    )
    session.execute(ins)


def _effective_profit_sql() -> str:
    """Expression aligned with _pick_row_contribution for validation."""
    return """
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


def run_validation(session) -> None:
    total_picks_picks = session.scalar(select(func.count(Pick.pick_id))) or 0
    total_picks_agg = session.scalar(
        select(func.coalesce(func.sum(AggPickDaily.pick_count), 0))
    )
    total_picks_agg = int(total_picks_agg or 0)

    picks_profit = session.scalar(text(f"SELECT {_effective_profit_sql()} FROM picks"))
    picks_profit = picks_profit if picks_profit is not None else Decimal("0")

    agg_profit = session.scalar(
        select(func.coalesce(func.sum(AggPickDaily.total_profit), 0))
    )
    agg_profit = agg_profit if agg_profit is not None else Decimal("0")

    delta_picks = total_picks_picks - total_picks_agg
    delta_profit = picks_profit - agg_profit

    logger.info("metric: total_profit | tolerance: ±0.01")
    logger.info(
        "  picks_sum=%s agg_sum=%s delta=%s %s",
        picks_profit,
        agg_profit,
        delta_profit,
        "OK" if abs(delta_profit) <= Decimal("0.01") else "FAIL",
    )
    logger.info("metric: total_picks  | tolerance: 0")
    logger.info(
        "  picks_count=%s agg_sum_pick_count=%s delta=%s %s",
        total_picks_picks,
        total_picks_agg,
        delta_picks,
        "OK" if delta_picks == 0 else "FAIL",
    )

    if abs(delta_profit) > Decimal("0.01") or delta_picks != 0:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill shadow aggregate tables.")
    parser.add_argument(
        "--skip-truncate",
        action="store_true",
        help="Do not truncate agg_* before run (only safe if tables are empty).",
    )
    args = parser.parse_args()

    session = SyncSessionLocal()
    try:
        if not args.skip_truncate:
            session.execute(text("TRUNCATE agg_pick_dimension_daily, agg_pick_daily"))
            session.commit()

        last_id: UUID | None = None
        batch_idx = 0
        while True:
            t0 = time.perf_counter()
            q = select(Pick).order_by(Pick.pick_id).limit(BATCH_SIZE)
            if last_id is not None:
                q = q.where(Pick.pick_id > last_id)
            picks = list(session.execute(q).scalars().all())

            if not picks:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "batch=%s done duration_ms=%s rows=0 (end)",
                    batch_idx,
                    duration_ms,
                )
                break

            daily: dict[Any, dict[str, Any]] = {}
            dim: dict[Any, dict[str, Any]] = {}
            for p in picks:
                c = _pick_row_contribution(p)
                _merge(daily, p.run_date, c)
                _merge(dim, (p.run_date, _dimension_key(p.sportsbook_id)), c)

            _flush_daily(session, daily)
            _flush_dimension(session, dim)
            session.commit()

            duration_ms = int((time.perf_counter() - t0) * 1000)
            last_id = picks[-1].pick_id
            logger.info(
                "batch=%s duration_ms=%s rows=%s last_pick_id=%s",
                batch_idx,
                duration_ms,
                len(picks),
                last_id,
            )
            batch_idx += 1

        run_validation(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
