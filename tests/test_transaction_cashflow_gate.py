"""Phase 6.2.4: drift gate on deposit/withdrawal and process_* user gate."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.exceptions import ConflictError, UnprocessableError
from app.models.balance import UserBalance
from app.models.competition import Competition
from app.models.ledger import LedgerEntry, LedgerEntryType
from app.models.match import Match, MatchStatus
from app.models.sport import Sport
from app.models.sportsbook import Sportsbook
from app.models.transaction import TransactionType
from app.schemas.transaction import TransactionCreate
from app.services import reconciliation_service, transaction_service


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


async def _seed_sb(db: AsyncSession) -> uuid.UUID:
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
    return sb.sportsbook_id


@pytest.mark.asyncio
async def test_summarize_financial_health_counts_critical(db_session: AsyncSession):
    bad_uid = uuid.uuid4()
    db_session.add(
        UserBalance(
            user_id=bad_uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        LedgerEntry(
            user_id=bad_uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("100.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    summary = await reconciliation_service.summarize_financial_health(db_session)
    assert summary.critical_users >= 1
    assert summary.total_users >= 1


@pytest.mark.asyncio
async def test_create_transaction_deposit_blocked_when_critical_exists(db_session: AsyncSession):
    sb_id = await _seed_sb(db_session)
    bad_uid = uuid.uuid4()
    db_session.add(
        UserBalance(
            user_id=bad_uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        LedgerEntry(
            user_id=bad_uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("100.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    payload = TransactionCreate(
        sportsbook_id=sb_id,
        type=TransactionType.deposit,
        amount=Decimal("10.00"),
        transaction_date=date(2026, 3, 1),
    )
    with pytest.raises(ConflictError) as ei:
        await transaction_service.create_transaction(db_session, payload)
    assert ei.value.code == "CASHFLOW_BLOCKED_CRITICAL_DRIFT"


@pytest.mark.asyncio
async def test_process_deposit_requires_matching_type(db_session: AsyncSession):
    sb_id = await _seed_sb(db_session)
    uid = uuid.uuid4()
    db_session.add(
        UserBalance(
            user_id=uid,
            available_balance=Decimal("100.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()

    payload = TransactionCreate(
        sportsbook_id=sb_id,
        type=TransactionType.bonus,
        amount=Decimal("10.00"),
        transaction_date=date(2026, 3, 1),
    )
    with pytest.raises(UnprocessableError) as ei:
        await transaction_service.process_deposit(db_session, uid, payload)
    assert ei.value.code == "CASHFLOW_TYPE_MISMATCH"


@pytest.mark.asyncio
async def test_process_deposit_blocked_on_user_critical(db_session: AsyncSession):
    sb_id = await _seed_sb(db_session)
    bad_uid = uuid.uuid4()
    db_session.add(
        UserBalance(
            user_id=bad_uid,
            available_balance=Decimal("1000.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()
    db_session.add(
        LedgerEntry(
            user_id=bad_uid,
            amount=Decimal("0.00"),
            type=LedgerEntryType.PICK_STAKE_LOCK,
            reference_id=None,
            balance_after=Decimal("100.00"),
            locked_after=Decimal("0.00"),
        )
    )
    await db_session.flush()

    ok_uid = uuid.uuid4()
    db_session.add(
        UserBalance(
            user_id=ok_uid,
            available_balance=Decimal("50.00"),
            locked_balance=Decimal("0.00"),
        )
    )
    await db_session.flush()

    payload = TransactionCreate(
        sportsbook_id=sb_id,
        type=TransactionType.deposit,
        amount=Decimal("10.00"),
        transaction_date=date(2026, 3, 1),
    )
    with pytest.raises(ConflictError) as ei:
        await transaction_service.process_deposit(db_session, ok_uid, payload)
    assert ei.value.code == "CASHFLOW_BLOCKED_CRITICAL_DRIFT"
