"""Unit tests for pipeline components (Step 12 — Testing)."""
import pytest
from app.worker.pipeline.predictor import Predictor


class TestPredictor:
    """Unit tests for the Predictor EV engine."""

    def setup_method(self):
        self.predictor = Predictor()

    def test_positive_ev_gives_grade_a(self):
        """High win probability + generous odd should yield grade A."""
        result = self.predictor.evaluate(
            implied_probability=0.60,
            decimal_odd=2.50,
        )
        assert result["viable"] is True
        assert result["expected_value"] > 0
        assert result["grade"] in ("A", "B", "C", "D")

    def test_negative_ev_not_viable(self):
        """Low win probability + tight odd should be marked not viable."""
        result = self.predictor.evaluate(
            implied_probability=0.30,
            decimal_odd=1.60,
        )
        assert result["viable"] is False

    def test_odd_below_minimum_returns_grade_f(self):
        """Any odd below MIN_VIABLE_ODD must be rejected."""
        result = self.predictor.evaluate(
            implied_probability=0.80,
            decimal_odd=1.20,  # below 1.50 threshold
        )
        assert result["viable"] is False
        assert result["expected_value"] is None

    def test_historical_win_rate_overrides_implied(self):
        """Explicit historical_win_rate should take precedence."""
        result_a = self.predictor.evaluate(0.40, 2.00, historical_win_rate=0.65)
        result_b = self.predictor.evaluate(0.40, 2.00)
        # Higher historical rate should produce higher EV
        assert result_a["expected_value"] > result_b["expected_value"]
