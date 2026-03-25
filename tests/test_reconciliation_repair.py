"""Phase 6.2.3 v2: drift classification, repair gate, and settlement drift gate.

Requires PostgreSQL. Example:

  docker compose run --rm api sh -c "alembic upgrade head && pytest tests/test_reconciliation_repair.py -q"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.exceptions import ConflictError
from app.models.balance import UserBalance
from app.models.competition import Competition
from app.models.ledger import LedgerEntry, LedgerEntryType
from app.models.match import Match, MatchStatus
from app.models.pick import Pick, PickGrade, PickSource, PickStatus
from app.models.sport import Sport
from app.models.sportsbook import Sportsbook
from app.schemas.pick import PickCreate
from app.services import pick_service, reconciliation_service
from app.services.settlement_engine import execute_settlement


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


async def _seed_wallet_graph(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
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
    return sb.sportsbook_id, match.match_id, uid


@pytest.mark.asyncio
async def test_classify_drift_none(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    assert await reconciliation_service.classify_drift(db_session, uid) == reconciliation_service.DriftType.NONE


@pytest.mark.asyncio
async def test_classify_drift_escrow_mismatch_ledger_ok(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("950.00"),
            locked_balance=Decimal("50.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        Pick(
            user_id=uid,
            match_id=match_id,
            sportsbook_id=sb_id,
            run_date=datetime(2026, 3, 1, tzinfo=timezone.utc).date(),
            market="ml",
            selection="home",
            odds_american=-110,
            odds_decimal=Decimal("1.91"),
            implied_prob=Decimal("0.5240"),
            grade=PickGrade.A,
            stake=Decimal("100.00"),
            status=PickStatus.pending,
            source=PickSource.manual,
        )
    )
    db_session.add(
        LedgerEntry(
            user_id=uid,
            amount=Decimal("-100.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("900.00"),
            locked_after=Decimal("100.00"),
        )
    )
    await db_session.flush()

    drift = await reconciliation_service.classify_drift(db_session, uid)
    assert drift == reconciliation_service.DriftType.ESCROW_MISMATCH


@pytest.mark.asyncio
async def test_classify_drift_ledger_mismatch(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        LedgerEntry(
            user_id=uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("500.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    drift = await reconciliation_service.classify_drift(db_session, uid)
    assert drift == reconciliation_service.DriftType.LEDGER_MISMATCH


@pytest.mark.asyncio
async def test_fix_user_balance_repairs_escrow_only(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("950.00"),
            locked_balance=Decimal("50.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        Pick(
            user_id=uid,
            match_id=match_id,
            sportsbook_id=sb_id,
            run_date=datetime(2026, 3, 1, tzinfo=timezone.utc).date(),
            market="ml",
            selection="home",
            odds_american=-110,
            odds_decimal=Decimal("1.91"),
            implied_prob=Decimal("0.5240"),
            grade=PickGrade.A,
            stake=Decimal("100.00"),
            status=PickStatus.pending,
            source=PickSource.manual,
        )
    )
    db_session.add(
        LedgerEntry(
            user_id=uid,
            amount=Decimal("-100.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("900.00"),
            locked_after=Decimal("100.00"),
        )
    )
    await db_session.flush()

    out = await reconciliation_service.fix_user_balance(db_session, uid)
    assert out.repaired is True
    assert out.new_locked == Decimal("100.00")
    assert out.new_available == Decimal("900.00")

    bal = (
        await db_session.execute(select(UserBalance).where(UserBalance.user_id == uid))
    ).scalar_one()
    assert bal.locked_balance == Decimal("100.00")
    assert bal.available_balance == Decimal("900.00")


@pytest.mark.asyncio
async def test_fix_user_balance_aborts_on_ledger_mismatch(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        LedgerEntry(
            user_id=uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("100.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    with pytest.raises(ConflictError) as ei:
        await reconciliation_service.fix_user_balance(db_session, uid)
    assert ei.value.code == "REPAIR_UNSAFE_STATE"


@pytest.mark.asyncio
async def test_assert_financial_health_blocks_settlement_on_critical(db_session: AsyncSession):
    sb_id, match_id, uid = await _seed_wallet_graph(db_session)
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    pick = await pick_service.create_pick(
        db_session,
        PickCreate(
            user_id=uid,
            match_id=match_id,
            sportsbook_id=sb_id,
            market="h2h",
            selection="Home",
            odds_american=-110,
            stake=Decimal("50.00"),
            source=PickSource.manual,
        ),
    )
    db_session.add(
        LedgerEntry(
            user_id=uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("100.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    with pytest.raises(ConflictError) as ei:
        await execute_settlement(db_session, pick.pick_id, PickStatus.won)
    assert ei.value.code == "FINANCIAL_STATE_CORRUPTED"
