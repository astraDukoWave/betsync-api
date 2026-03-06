"""Unit tests for pipeline predictor."""
import pytest
from app.worker.pipeline.predictor import evaluate
from app.models.pick import PickGrade


class TestPredictor:

    def test_positive_ev_gives_high_grade(self):
        result = evaluate(
            implied_probability=0.60,
            decimal_odd=2.50,
        )
        assert result["viable"] is True
        assert result["expected_value"] > 0
        assert result["grade"] in (PickGrade.A, PickGrade.B, PickGrade.C)

    def test_negative_ev_not_viable(self):
        result = evaluate(
            implied_probability=0.30,
            decimal_odd=1.60,
        )
        assert result["viable"] is False

    def test_odd_below_minimum_returns_low_grade(self):
        result = evaluate(
            implied_probability=0.80,
            decimal_odd=1.20,
        )
        assert result["viable"] is False
        assert result["expected_value"] is None

    def test_historical_win_rate_overrides_implied(self):
        result_a = evaluate(0.40, 2.00, historical_win_rate=0.65)
        result_b = evaluate(0.40, 2.00)
        assert result_a["expected_value"] > result_b["expected_value"]
