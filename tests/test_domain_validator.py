"""Unit tests for pick domain invariants (no database).

Run in Docker (recommended): docker compose run --rm api pytest tests/test_domain_validator.py -q
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import UnprocessableError
from app.models.pick import Pick, PickGrade, PickSource, PickStatus
from app.services.pick_service import DomainValidator, PickPersistSnapshot


_TERMINAL = frozenset(
    {
        PickStatus.won,
        PickStatus.lost,
        PickStatus.push,
        PickStatus.void,
    }
)


def _pending_pick(**kwargs) -> Pick:
    created_at = kwargs.get("created_at") or datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    defaults = dict(
        match_id=uuid4(),
        sportsbook_id=uuid4(),
        run_date=date.today(),
        market="h2h",
        selection="Home",
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        implied_prob=Decimal("0.5240"),
        grade=PickGrade.B,
        stake=Decimal("10.00"),
        status=PickStatus.pending,
        source=PickSource.manual,
        created_at=created_at,
        resolved_at=None,
    )
    defaults.update(kwargs)
    if defaults["status"] in _TERMINAL and defaults.get("resolved_at") is None:
        defaults["resolved_at"] = defaults["created_at"]
    return Pick(**defaults)


def test_create_pending_valid():
    p = _pending_pick()
    DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))


def test_stake_must_be_positive_when_set():
    p = _pending_pick(stake=Decimal("0"))
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_STAKE_INVALID"


def test_pending_cannot_have_profit():
    p = _pending_pick(profit=Decimal("1.00"))
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_PENDING_PROFIT"


def test_void_requires_zero_profit():
    p = _pending_pick(
        status=PickStatus.void,
        profit=Decimal("1"),
        settled_return=Decimal("10"),
        resolved_at=datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_VOID_PROFIT"


def test_won_profit_within_tolerance():
    stake = Decimal("10.00")
    odds = Decimal("2.00")
    p = _pending_pick(
        status=PickStatus.won,
        stake=stake,
        odds_decimal=odds,
        profit=stake * odds - stake,
        settled_return=stake * odds,
        resolved_at=datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
    )
    DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))


def test_won_profit_outside_tolerance():
    stake = Decimal("10.00")
    odds = Decimal("2.00")
    p = _pending_pick(
        status=PickStatus.won,
        stake=stake,
        odds_decimal=odds,
        profit=Decimal("50.00"),
        settled_return=Decimal("60.00"),
        resolved_at=datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_PROFIT_MISMATCH"


def test_terminal_odds_immutable():
    r = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    prior = PickPersistSnapshot(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
        resolved_at=r,
        market="h2h",
    )
    p = _pending_pick(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=150,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
        resolved_at=r,
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, prior, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_ODDS_IMMUTABLE"


def test_invalid_transition_won_to_pending():
    r = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
    prior = PickPersistSnapshot(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
        resolved_at=r,
        market="h2h",
    )
    p = _pending_pick(
        status=PickStatus.pending,
        stake=Decimal("10"),
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        profit=None,
        settled_return=None,
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, prior, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_STATUS_IMMUTABLE"
