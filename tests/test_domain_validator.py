"""Unit tests for pick domain invariants (no database).

Run in Docker (recommended): docker compose run --rm api pytest tests/test_domain_validator.py -q
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import UnprocessableError
from app.models.pick import Pick, PickGrade, PickSource, PickStatus
from app.services.pick_service import DomainValidator, PickPersistSnapshot


def _pending_pick(**kwargs) -> Pick:
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
    )
    defaults.update(kwargs)
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
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, None, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_PROFIT_MISMATCH"


def test_terminal_odds_immutable():
    prior = PickPersistSnapshot(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
    )
    p = _pending_pick(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=150,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
    )
    with pytest.raises(UnprocessableError) as ei:
        DomainValidator.validate(p, prior, profit_tolerance=Decimal("0.02"))
    assert ei.value.code == "DOMAIN_ODDS_IMMUTABLE"


def test_invalid_transition_won_to_pending():
    prior = PickPersistSnapshot(
        status=PickStatus.won,
        stake=Decimal("10"),
        odds_american=-110,
        odds_decimal=Decimal("1.9091"),
        profit=Decimal("9.09"),
        settled_return=Decimal("19.09"),
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
