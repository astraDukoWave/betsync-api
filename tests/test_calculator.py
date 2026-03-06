"""Pure unit tests for calculator.py — no DB, no HTTP, no Redis.

Step 12 — Testing & Quality Assurance.
These tests are the fastest in the suite because calculator functions
are pure (no side-effects). They should run in < 1 ms each.
"""
import pytest
from app.worker.pipeline.calculator import (
    american_to_decimal,
    calc_implied_prob,
    calc_clv,
    build_parlay_suggestions,
)


class TestAmericanToDecimal:
    """FR-06: odds conversion from American to Decimal format."""

    def test_positive_favorite(self):
        """Negative American odds (favorite) — e.g. -110 → 1.9091."""
        result = american_to_decimal(-110)
        assert abs(result - 1.9091) < 0.001

    def test_positive_underdog(self):
        """+150 → 2.5000."""
        result = american_to_decimal(150)
        assert abs(result - 2.5000) < 0.001

    def test_plus_100(self):
        """+100 → 2.0000."""
        result = american_to_decimal(100)
        assert abs(result - 2.0000) < 0.001

    def test_minus_143(self):
        """-143 → 1.6993 (typical favorite)."""
        result = american_to_decimal(-143)
        assert abs(result - 1.6993) < 0.001

    def test_invalid_range_raises(self):
        """Values in (-100, 100) are not valid American odds."""
        with pytest.raises(ValueError):
            american_to_decimal(-50)  # -99 < x < 100 is invalid


class TestCalcImpliedProb:
    """FR-06: implied probability = 1 / decimal_odds."""

    def test_basic(self):
        assert abs(calc_implied_prob(2.5) - 0.4000) < 0.0001

    def test_even_money(self):
        assert abs(calc_implied_prob(2.0) - 0.5000) < 0.0001

    def test_heavy_favorite(self):
        assert abs(calc_implied_prob(1.25) - 0.8000) < 0.0001

    def test_precision(self):
        """Result is rounded to 4 decimal places per spec."""
        result = calc_implied_prob(1.6993)
        assert len(str(result).split(".")[1]) <= 4


class TestCalcCLV:
    """FR-13: Closing Line Value = (bet_odds / closing_odds - 1) * 100."""

    def test_positive_clv(self):
        """Got 2.0, closing was 1.80 — positive CLV."""
        result = calc_clv(2.0, 1.80)
        assert abs(result - 11.11) < 0.01

    def test_zero_clv(self):
        """Bet at same line as closing — CLV = 0."""
        result = calc_clv(2.0, 2.0)
        assert result == 0.0

    def test_negative_clv(self):
        """Got worse than closing line — negative CLV."""
        result = calc_clv(1.70, 2.00)
        assert result < 0


class TestBuildParlaySuggestions:
    """FR-17: parlay suggestions from grade-A picks."""

    def _make_pick(self, pick_id: str, match_id: str, odds: float) -> dict:
        return {"pick_id": pick_id, "match_id": match_id, "odds_decimal": odds, "grade": "A"}

    def test_two_picks_generates_one_parlay(self):
        picks = [
            self._make_pick("p1", "m1", 2.0),
            self._make_pick("p2", "m2", 2.0),
        ]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        assert len(result) >= 1
        assert result[0]["odds_total"] == pytest.approx(4.0, rel=0.01)

    def test_same_match_excluded(self):
        """Two picks from the same match must not appear in the same parlay."""
        picks = [
            self._make_pick("p1", "m1", 2.0),
            self._make_pick("p2", "m1", 2.0),  # same match!
            self._make_pick("p3", "m2", 2.0),
        ]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        for parlay in result:
            match_ids = [p["match_id"] for p in parlay["picks"]]
            assert len(match_ids) == len(set(match_ids)), "Duplicate match in parlay!"

    def test_below_min_odds_excluded(self):
        """Parlays below min_odds_total are filtered out."""
        picks = [
            self._make_pick("p1", "m1", 1.10),
            self._make_pick("p2", "m2", 1.10),
        ]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        # 1.10 * 1.10 = 1.21 < 1.80, should be excluded
        assert all(p["odds_total"] >= 1.80 for p in result)
