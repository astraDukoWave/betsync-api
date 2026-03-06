import logging
from datetime import date
from decimal import Decimal
from functools import reduce
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, BadRequestError
from app.models.parlay import Parlay, ParlayStatus
from app.models.parlay_pick import ParlayPick
from app.models.pick import Pick, PickStatus
from app.schemas.parlay import ParlayCreate

logger = logging.getLogger(__name__)


async def create_parlay(db: AsyncSession, data: ParlayCreate) -> Parlay:
    result = await db.execute(
        select(Pick).where(Pick.pick_id.in_(data.pick_ids))
    )
    picks = list(result.scalars().all())

    if len(picks) != len(data.pick_ids):
        raise BadRequestError("PICKS_NOT_FOUND", "One or more pick_ids are invalid")

    match_ids = [p.match_id for p in picks]
    if len(match_ids) != len(set(match_ids)):
        raise BadRequestError(
            "PARLAY_DUPLICATE_MATCH",
            "A parlay cannot contain multiple picks from the same match",
        )

    for p in picks:
        if p.status != PickStatus.pending:
            raise BadRequestError(
                "PICK_NOT_PENDING",
                f"Pick {p.pick_id} is not in pending status",
            )

    odds_total = reduce(
        lambda acc, p: acc * p.odds_decimal, picks, Decimal("1")
    ).quantize(Decimal("0.0001"))
    potential_return = (data.stake * odds_total).quantize(Decimal("0.01"))

    parlay = Parlay(
        sportsbook_id=data.sportsbook_id,
        run_date=date.today(),
        type=data.type,
        stake=data.stake,
        odds_total=odds_total,
        potential_return=potential_return,
        status=ParlayStatus.pending,
    )
    db.add(parlay)
    await db.flush()

    for pick in picks:
        pp = ParlayPick(parlay_id=parlay.parlay_id, pick_id=pick.pick_id)
        db.add(pp)

    await db.flush()
    logger.info("Parlay created: %s | odds_total=%.4f", parlay.parlay_id, odds_total)
    return parlay


async def get_parlay(db: AsyncSession, parlay_id: UUID) -> Parlay:
    result = await db.execute(
        select(Parlay)
        .options(selectinload(Parlay.parlay_picks).selectinload(ParlayPick.pick))
        .where(Parlay.parlay_id == parlay_id)
    )
    parlay = result.scalar_one_or_none()
    if not parlay:
        raise NotFoundError("PARLAY_NOT_FOUND", f"Parlay {parlay_id} not found")
    return parlay


async def list_parlays(
    db: AsyncSession,
    status: Optional[ParlayStatus] = None,
    run_date: Optional[date] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Parlay]:
    query = select(Parlay).options(
        selectinload(Parlay.parlay_picks).selectinload(ParlayPick.pick)
    )
    if status:
        query = query.where(Parlay.status == status)
    if run_date:
        query = query.where(Parlay.run_date == run_date)

    result = await db.execute(
        query.order_by(Parlay.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def auto_resolve_parlays_for_pick(db: AsyncSession, pick_id: UUID):
    """Called after a pick is resolved; checks if any parlays can be auto-resolved."""
    result = await db.execute(
        select(ParlayPick.parlay_id).where(ParlayPick.pick_id == pick_id)
    )
    parlay_ids = [row[0] for row in result.all()]

    for pid in parlay_ids:
        parlay = await get_parlay(db, pid)
        if parlay.status != ParlayStatus.pending:
            continue

        pick_statuses = [pp.pick.status for pp in parlay.parlay_picks]
        if PickStatus.pending in pick_statuses:
            continue

        if all(s == PickStatus.won for s in pick_statuses):
            parlay.status = ParlayStatus.won
            parlay.actual_return = parlay.potential_return
        elif any(s == PickStatus.lost for s in pick_statuses):
            parlay.status = ParlayStatus.lost
            parlay.actual_return = Decimal("0.00")

        await db.flush()
        logger.info("Parlay auto-resolved: %s → %s", pid, parlay.status.value)
