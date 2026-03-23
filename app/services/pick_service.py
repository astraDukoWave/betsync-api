import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import NotFoundError, ConflictError, BadRequestError, UnprocessableError
from app.models.pick import Pick, PickStatus, PickGrade, PickSource
from app.models.parlay_pick import ParlayPick
from app.schemas.pick import PickCreate, PickUpdate, PickResolve, PickConfirm
from app.worker.pipeline.calculator import american_to_decimal, calc_implied_prob, calc_clv
from app.worker.tasks import enqueue_recompute_aggregates_for_day

logger = logging.getLogger(__name__)

GRADE_THRESHOLDS = {"A": 0.55, "B": 0.50}

_TERMINAL_STATUSES = frozenset(
    {PickStatus.won, PickStatus.lost, PickStatus.push, PickStatus.void}
)
_ALLOWED_FROM_PENDING = frozenset(
    {PickStatus.won, PickStatus.lost, PickStatus.push, PickStatus.void}
)


@dataclass(frozen=True)
class PickPersistSnapshot:
    status: PickStatus
    stake: Optional[Decimal]
    odds_american: int
    odds_decimal: Decimal
    profit: Optional[Decimal]
    settled_return: Optional[Decimal]


def pick_persist_snapshot(pick: Pick) -> PickPersistSnapshot:
    return PickPersistSnapshot(
        status=pick.status,
        stake=pick.stake,
        odds_american=pick.odds_american,
        odds_decimal=pick.odds_decimal,
        profit=pick.profit,
        settled_return=pick.settled_return,
    )


class DomainValidator:
    """Enforces financial and lifecycle invariants before any Pick reaches the database."""

    @staticmethod
    def _expected_profit(
        status: PickStatus,
        stake: Optional[Decimal],
        odds_decimal: Decimal,
    ) -> Optional[Decimal]:
        if stake is None:
            return None
        if status == PickStatus.won:
            return stake * odds_decimal - stake
        if status == PickStatus.lost:
            return -stake
        if status == PickStatus.push:
            return Decimal("0")
        if status == PickStatus.void:
            return Decimal("0")
        return None

    @classmethod
    def validate(
        cls,
        pick: Pick,
        prior: Optional[PickPersistSnapshot],
        *,
        profit_tolerance: Decimal,
    ) -> None:
        if pick.stake is not None and pick.stake <= 0:
            raise UnprocessableError(
                "DOMAIN_STAKE_INVALID",
                "stake must be strictly greater than zero when provided",
                meta={"stake": str(pick.stake)},
            )

        if prior is not None:
            if prior.status in _TERMINAL_STATUSES:
                if pick.status != prior.status:
                    raise UnprocessableError(
                        "DOMAIN_STATUS_IMMUTABLE",
                        "Resolved picks cannot change status",
                        meta={
                            "from": prior.status.value,
                            "to": pick.status.value,
                        },
                    )
                if pick.stake != prior.stake:
                    raise UnprocessableError(
                        "DOMAIN_STAKE_IMMUTABLE",
                        "Cannot change stake after resolution",
                    )
                if pick.odds_american != prior.odds_american:
                    raise UnprocessableError(
                        "DOMAIN_ODDS_IMMUTABLE",
                        "Cannot change odds after resolution",
                    )
                if pick.odds_decimal != prior.odds_decimal:
                    raise UnprocessableError(
                        "DOMAIN_ODDS_IMMUTABLE",
                        "Cannot change odds_decimal after resolution",
                    )
            elif prior.status != pick.status:
                if prior.status != PickStatus.pending:
                    raise UnprocessableError(
                        "DOMAIN_INVALID_TRANSITION",
                        "Invalid pick status transition",
                        meta={
                            "from": prior.status.value,
                            "to": pick.status.value,
                        },
                    )
                if pick.status not in _ALLOWED_FROM_PENDING:
                    raise UnprocessableError(
                        "DOMAIN_INVALID_TRANSITION",
                        "Invalid transition from pending",
                        meta={"to": pick.status.value},
                    )

        if pick.status == PickStatus.pending:
            if pick.profit is not None:
                raise UnprocessableError(
                    "DOMAIN_PENDING_PROFIT",
                    "A pending pick cannot have a definitive profit",
                )
            if pick.settled_return is not None:
                raise UnprocessableError(
                    "DOMAIN_PENDING_SETTLEMENT",
                    "A pending pick cannot have settled_return",
                )

        if pick.status == PickStatus.void:
            if pick.profit != Decimal("0"):
                raise UnprocessableError(
                    "DOMAIN_VOID_PROFIT",
                    "Void picks must have profit exactly zero",
                    meta={"profit": str(pick.profit)},
                )

        if pick.status in (PickStatus.won, PickStatus.lost, PickStatus.push):
            if pick.stake is None or pick.stake <= 0:
                raise UnprocessableError(
                    "DOMAIN_RESOLVED_REQUIRES_STAKE",
                    "Won, lost, and push picks require a positive stake",
                )
            expected = cls._expected_profit(
                pick.status, pick.stake, pick.odds_decimal
            )
            if pick.profit is None or expected is None:
                raise UnprocessableError(
                    "DOMAIN_PROFIT_REQUIRED",
                    "Resolved pick must carry profit consistent with stake and odds",
                )
            if abs(pick.profit - expected) > profit_tolerance:
                raise UnprocessableError(
                    "DOMAIN_PROFIT_MISMATCH",
                    "profit is not consistent with stake and odds within tolerance",
                    meta={
                        "profit": str(pick.profit),
                        "expected": str(expected),
                        "tolerance": str(profit_tolerance),
                    },
                )


def _settlement_for_status(
    status: PickStatus,
    stake: Optional[Decimal],
    odds_decimal: Decimal,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Return (settled_return, profit) for a resolved status."""
    if stake is None:
        if status == PickStatus.void:
            return None, Decimal("0")
        return None, None
    if status == PickStatus.won:
        gross = stake * odds_decimal
        return gross, gross - stake
    if status == PickStatus.lost:
        return Decimal("0"), -stake
    if status == PickStatus.push:
        return stake, Decimal("0")
    if status == PickStatus.void:
        return stake, Decimal("0")
    return None, None


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
    DomainValidator.validate(pick, None, profit_tolerance=settings.pick_profit_tolerance)
    db.add(pick)
    await db.flush()
    await db.refresh(pick)
    logger.info("Pick created: %s | %s @ %s", pick.pick_id, data.selection, odds_dec)
    enqueue_recompute_aggregates_for_day(pick.run_date)
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

    prior = pick_persist_snapshot(pick)

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

    DomainValidator.validate(
        pick, prior, profit_tolerance=settings.pick_profit_tolerance
    )

    await db.flush()
    await db.refresh(pick)
    enqueue_recompute_aggregates_for_day(pick.run_date)
    return pick


async def resolve_pick(db: AsyncSession, pick_id: UUID, data: PickResolve) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.status != PickStatus.pending:
        raise ConflictError(
            "PICK_ALREADY_RESOLVED",
            "Pick already has a final status",
            meta={"current_status": pick.status.value, "pick_id": str(pick_id)},
        )

    prior = pick_persist_snapshot(pick)

    pick.status = data.status
    pick.resolved_at = datetime.utcnow()
    pick.settled_return, pick.profit = _settlement_for_status(
        data.status, pick.stake, pick.odds_decimal
    )

    if data.closing_odds_decimal is not None:
        pick.closing_odds_decimal = data.closing_odds_decimal
        pick.clv = Decimal(
            str(calc_clv(float(pick.odds_decimal), float(data.closing_odds_decimal)))
        )

    DomainValidator.validate(
        pick, prior, profit_tolerance=settings.pick_profit_tolerance
    )

    await db.flush()
    await db.refresh(pick)
    logger.info("Pick resolved: %s → %s", pick_id, data.status.value)
    enqueue_recompute_aggregates_for_day(pick.run_date)
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

    prior = pick_persist_snapshot(pick)
    pick.status = PickStatus.void
    pick.resolved_at = datetime.utcnow()
    pick.settled_return, pick.profit = _settlement_for_status(
        PickStatus.void, pick.stake, pick.odds_decimal
    )

    DomainValidator.validate(
        pick, prior, profit_tolerance=settings.pick_profit_tolerance
    )

    await db.flush()
    await db.refresh(pick)
    enqueue_recompute_aggregates_for_day(pick.run_date)
    return pick


async def confirm_pick(db: AsyncSession, pick_id: UUID, data: PickConfirm) -> Pick:
    pick = await get_pick(db, pick_id)
    if pick.source != PickSource.pipeline:
        raise BadRequestError(
            "PICK_NOT_FROM_PIPELINE",
            "Only pipeline-sourced picks can be confirmed",
        )

    prior = pick_persist_snapshot(pick)

    if data.confirmed:
        pick.confirmed_at = datetime.utcnow()
    else:
        pick.status = PickStatus.void
        pick.resolved_at = datetime.utcnow()
        pick.settled_return, pick.profit = _settlement_for_status(
            PickStatus.void, pick.stake, pick.odds_decimal
        )

    DomainValidator.validate(
        pick, prior, profit_tolerance=settings.pick_profit_tolerance
    )

    await db.flush()
    await db.refresh(pick)
    return pick
