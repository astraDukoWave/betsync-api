import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ConflictError, BadRequestError
from app.models.pick import Pick, PickStatus, PickGrade, PickSource
from app.models.parlay_pick import ParlayPick
from app.schemas.pick import PickCreate, PickUpdate, PickResolve, PickConfirm
from app.worker.pipeline.calculator import american_to_decimal, calc_implied_prob, calc_clv

logger = logging.getLogger(__name__)

GRADE_THRESHOLDS = {"A": 0.55, "B": 0.50}


def classify_grade(implied_prob: float) -> PickGrade:
    if implied_prob >= GRADE_THRESHOLDS["A"]:
        return PickGrade.A
    elif implied_prob >= GRADE_THRESHOLDS["B"]:
        return PickGrade.B
    return PickGrade.C


async def create_pick(db: AsyncSession, data: PickCreate) -> Pick:
    odds_dec = american_to_decimal(data.odds_american)
    imp_prob = calc_implied_prob(odds_dec)
    grade = data.grade if data.grade is not None else classify_grade(imp_prob)

    pick = Pick(
        match_id=data.match_id,
        sportsbook_id=data.sportsbook_id,
        run_date=date.today(),
        market=data.market,
        selection=data.selection,
        odds_american=data.odds_american,
        odds_decimal=Decimal(str(odds_dec)),
        implied_prob=Decimal(str(imp_prob)),
        grade=grade,
        stake=data.stake,
        status=PickStatus.pending,
        source=data.source,
    )
    db.add(pick)
    await db.flush()
    logger.info("Pick created: %s | %s @ %s", pick.pick_id, data.selection, odds_dec)
    return pick


async def get_pick(db: AsyncSession, pick_id: UUID) -> Pick:
    pick = await db.get(Pick, pick_id)
    if not pick:
        raise NotFoundError("PICK_NOT_FOUND", f"Pick {pick_id} not found")
    return pick


async def list_picks(
    db: AsyncSession,
    run_date: Optional[date] = None,
    status: Optional[PickStatus] = None,
    sport_id: Optional[UUID] = None,
    competition_id: Optional[UUID] = None,
    market: Optional[str] = None,
    grade: Optional[PickGrade] = None,
    source: Optional[PickSource] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Pick], int]:
    query = select(Pick)
    count_query = select(func.count(Pick.pick_id))

    if run_date:
        query = query.where(Pick.run_date == run_date)
        count_query = count_query.where(Pick.run_date == run_date)
    if status:
        query = query.where(Pick.status == status)
        count_query = count_query.where(Pick.status == status)
    if market:
        query = query.where(Pick.market == market)
        count_query = count_query.where(Pick.market == market)
    if grade:
        query = query.where(Pick.grade == grade)
        count_query = count_query.where(Pick.grade == grade)
    if source:
        query = query.where(Pick.source == source)
        count_query = count_query.where(Pick.source == source)

    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(Pick.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), total


async def update_pick(db: AsyncSession, pick_id: UUID, data: PickUpdate) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.status != PickStatus.pending:
        raise ConflictError(
            "PICK_ALREADY_RESOLVED",
            "Cannot edit a resolved pick",
            meta={"current_status": pick.status.value},
        )

    update_data = data.model_dump(exclude_unset=True)
    if "odds_american" in update_data:
        odds_dec = american_to_decimal(update_data["odds_american"])
        imp_prob = calc_implied_prob(odds_dec)
        pick.odds_american = update_data["odds_american"]
        pick.odds_decimal = Decimal(str(odds_dec))
        pick.implied_prob = Decimal(str(imp_prob))
        if "grade" not in update_data:
            pick.grade = classify_grade(imp_prob)

    for field, value in update_data.items():
        if field != "odds_american":
            setattr(pick, field, value)

    await db.flush()
    return pick


async def resolve_pick(db: AsyncSession, pick_id: UUID, data: PickResolve) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.status != PickStatus.pending:
        raise ConflictError(
            "PICK_ALREADY_RESOLVED",
            "Pick already has a final status",
            meta={"current_status": pick.status.value, "pick_id": str(pick_id)},
        )

    pick.status = data.status
    pick.resolved_at = datetime.utcnow()

    if data.closing_odds_decimal is not None:
        pick.closing_odds_decimal = data.closing_odds_decimal
        pick.clv = Decimal(
            str(calc_clv(float(pick.odds_decimal), float(data.closing_odds_decimal)))
        )

    await db.flush()
    logger.info("Pick resolved: %s → %s", pick_id, data.status.value)
    return pick


async def delete_pick(db: AsyncSession, pick_id: UUID) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.status != PickStatus.pending:
        raise ConflictError(
            "PICK_NOT_PENDING",
            "Cannot delete a resolved pick",
            meta={"current_status": pick.status.value},
        )

    parlay_link = await db.scalar(
        select(ParlayPick.parlay_pick_id).where(ParlayPick.pick_id == pick_id).limit(1)
    )
    if parlay_link:
        raise ConflictError(
            "PICK_IN_PARLAY",
            "Cannot delete a pick that belongs to a parlay",
        )

    pick.status = PickStatus.void
    await db.flush()
    return pick


async def confirm_pick(db: AsyncSession, pick_id: UUID, data: PickConfirm) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.source != PickSource.pipeline:
        raise BadRequestError(
            "PICK_NOT_FROM_PIPELINE",
            "Only pipeline-sourced picks can be confirmed",
        )

    if data.confirmed:
        pick.confirmed_at = datetime.utcnow()
    else:
        pick.status = PickStatus.void

    await db.flush()
    return pick
