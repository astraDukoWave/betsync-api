"""Settlement engine race and idempotency scenarios.

Requires PostgreSQL (same schema as app). Run in Docker:

  docker compose run --rm api sh -c "alembic upgrade head && pytest tests/test_settlement_race_conditions.py -q"

If the DB is unreachable, tests are skipped.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.models.balance import UserBalance
from app.models.competition import Competition
from app.models.match import Match, MatchStatus
from app.models.pick import Pick, PickGrade, PickSource, PickStatus
from app.models.sport import Sport
from app.models.sportsbook import Sportsbook
from app.schemas.pick import PickCreate
from app.services import pick_service
from app.services.settlement_engine import execute_settlement, _is_unique_violation


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    conn = await engine.connect()
    trans = await conn.begin()
    session_factory = async_sessionmaker(
        bind=conn,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _check_db(db_session: AsyncSession):
    try:
        await db_session.execute(select(1))
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")


async def _seed_graph(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    uid = uuid.uuid4()
    suffix = str(uid)[:8]
    sport = Sport(name=f"Sport-{suffix}", slug=f"sport-{suffix}")
    db.add(sport)
    await db.flush()
    comp = Competition(
        sport_id=sport.sport_id,
        name=f"Comp-{suffix}",
        country="US",
    )
    db.add(comp)
    await db.flush()
    match = Match(
        competition_id=comp.competition_id,
        home_team="H",
        away_team="A",
        kickoff_at=datetime(2026, 3, 1, 18, 0, 0, tzinfo=timezone.utc),
        status=MatchStatus.scheduled,
    )
    db.add(match)
    await db.flush()
    sb = Sportsbook(name=f"Book-{suffix}")
    db.add(sb)
    await db.flush()
    db.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0"),
        )
    )
    await db.flush()
    return sb.sportsbook_id, match.match_id, uid


@pytest.mark.asyncio
async def test_settlement_idempotent_same_status(db_session: AsyncSession):
    """(1) Calling execute_settlement with the same terminal target twice is a NO-OP."""
    sportsbook_id, match_id, user_id = await _seed_graph(db_session)
    pick = await pick_service.create_pick(
        db_session,
        PickCreate(
            user_id=user_id,
            match_id=match_id,
            sportsbook_id=sportsbook_id,
            market="h2h",
            selection="Home",
            odds_american=-110,
            stake=Decimal("25.00"),
            source=PickSource.manual,
        ),
    )
    first = await execute_settlement(db_session, pick.pick_id, PickStatus.won)
    assert first.status == PickStatus.won
    second = await execute_settlement(db_session, pick.pick_id, PickStatus.won)
    assert second.status == PickStatus.won
    assert second.pick_id == pick.pick_id


@pytest.mark.asyncio
async def test_void_vs_resolve_race_terminal_conflict(db_session: AsyncSession):
    """(2) After resolve (won), void is rejected with TERMINAL_STATE_CONFLICT."""
    sportsbook_id, match_id, user_id = await _seed_graph(db_session)
    pick = await pick_service.create_pick(
        db_session,
        PickCreate(
            user_id=user_id,
            match_id=match_id,
            sportsbook_id=sportsbook_id,
            market="h2h",
            selection="Home",
            odds_american=-110,
            stake=Decimal("25.00"),
            source=PickSource.manual,
        ),
    )
    await execute_settlement(db_session, pick.pick_id, PickStatus.won)
    with pytest.raises(ConflictError) as ei:
        await execute_settlement(db_session, pick.pick_id, PickStatus.void)
    assert ei.value.code == "TERMINAL_STATE_CONFLICT"


@pytest.mark.asyncio
async def test_double_void_idempotent(db_session: AsyncSession):
    """(3) Two void requests: first transitions; second is idempotent NO-OP."""
    sportsbook_id, match_id, _user_id = await _seed_graph(db_session)
    pick = Pick(
        pick_id=uuid.uuid4(),
        user_id=None,
        match_id=match_id,
        sportsbook_id=sportsbook_id,
        run_date=date.today(),
        market="h2h",
        selection="Home",
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        implied_prob=Decimal("0.5240"),
        grade=PickGrade.B,
        stake=None,
        status=PickStatus.pending,
        source=PickSource.manual,
    )
    db_session.add(pick)
    await db_session.flush()

    first = await execute_settlement(db_session, pick.pick_id, PickStatus.void)
    assert first.status == PickStatus.void
    second = await execute_settlement(db_session, pick.pick_id, PickStatus.void)
    assert second.status == PickStatus.void


def test_unique_violation_detection_for_integrity_error():
    class _Orig:
        sqlstate = "23505"

    exc = IntegrityError("stmt", {}, _Orig())  # type: ignore[arg-type]
    assert _is_unique_violation(exc) is True
