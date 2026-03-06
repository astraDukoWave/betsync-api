"""Pure unit tests for calculator.py — no DB, no HTTP, no Redis."""
import pytest
from app.worker.pipeline.calculator import (
    american_to_decimal,
    calc_implied_prob,
    calc_clv,
    build_parlay_suggestions,
)


class TestAmericanToDecimal:

    def test_negative_favorite(self):
        result = american_to_decimal(-110)
        assert abs(result - 1.9091) < 0.001

    def test_positive_underdog(self):
        result = american_to_decimal(150)
        assert abs(result - 2.5000) < 0.001

    def test_plus_100(self):
        result = american_to_decimal(100)
        assert abs(result - 2.0000) < 0.001

    def test_minus_100(self):
        result = american_to_decimal(-100)
        assert abs(result - 2.0000) < 0.001

    def test_minus_143(self):
        result = american_to_decimal(-143)
        assert abs(result - 1.6993) < 0.001

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError):
            american_to_decimal(-50)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            american_to_decimal(0)


class TestCalcImpliedProb:

    def test_basic(self):
        assert abs(calc_implied_prob(2.5) - 0.4000) < 0.0001

    def test_even_money(self):
        assert abs(calc_implied_prob(2.0) - 0.5000) < 0.0001

    def test_heavy_favorite(self):
        assert abs(calc_implied_prob(1.25) - 0.8000) < 0.0001

    def test_precision(self):
        result = calc_implied_prob(1.6993)
        assert len(str(result).split(".")[1]) <= 4


class TestCalcCLV:

    def test_positive_clv(self):
        result = calc_clv(2.0, 1.80)
        assert abs(result - 11.11) < 0.01

    def test_zero_clv(self):
        result = calc_clv(2.0, 2.0)
        assert result == 0.0

    def test_negative_clv(self):
        result = calc_clv(1.70, 2.00)
        assert result < 0


class TestBuildParlaySuggestions:

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
        picks = [
            self._make_pick("p1", "m1", 2.0),
            self._make_pick("p2", "m1", 2.0),
            self._make_pick("p3", "m2", 2.0),
        ]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        for parlay in result:
            match_ids = [p["match_id"] for p in parlay["picks"]]
            assert len(match_ids) == len(set(match_ids))

    def test_below_min_odds_excluded(self):
        picks = [
            self._make_pick("p1", "m1", 1.10),
            self._make_pick("p2", "m2", 1.10),
        ]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        assert all(p["odds_total"] >= 1.80 for p in result)

    def test_single_pick_returns_empty(self):
        picks = [self._make_pick("p1", "m1", 2.0)]
        result = build_parlay_suggestions(picks, min_odds_total=1.80)
        assert result == []
