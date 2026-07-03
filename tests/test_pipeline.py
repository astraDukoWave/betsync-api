"""Unit tests for pipeline predictor."""
import pytest
from app.worker.pipeline.runner import PipelineRunner
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


class TestFindBestOdds:
    """Unit tests for PipelineRunner._find_best_odds — Sprint 1b coverage."""

    def _make_runner(self):
        return object.__new__(PipelineRunner)

    def _make_bookmakers(self):
        return [
            {
                "key": "draftkings",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "TeamA", "price": -127},
                    {"name": "TeamB", "price": 110},
                ]}],
            },
            {
                "key": "fanduel",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "TeamA", "price": -130},
                    {"name": "TeamB", "price": 112},
                ]}],
            },
            {
                "key": "betmgm",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "TeamA", "price": -122},
                    {"name": "TeamC", "price": 150},
                ]}],
            },
        ]

    def test_price_is_best_american_odds(self):
        runner = self._make_runner()
        result = runner._find_best_odds(self._make_bookmakers())
        team_a = next(o for o in result["h2h"] if o["name"] == "TeamA")
        assert team_a["price"] == -122

    def test_book_prices_has_entry_for_each_bookmaker(self):
        runner = self._make_runner()
        result = runner._find_best_odds(self._make_bookmakers())
        team_a = next(o for o in result["h2h"] if o["name"] == "TeamA")
        assert len(team_a["book_prices"]) == 3

    def test_book_prices_correct_keys_and_prices(self):
        runner = self._make_runner()
        result = runner._find_best_odds(self._make_bookmakers())
        team_a = next(o for o in result["h2h"] if o["name"] == "TeamA")
        bk_map = {e["bookmaker"]: e["price"] for e in team_a["book_prices"]}
        assert bk_map == {"draftkings": -127, "fanduel": -130, "betmgm": -122}

    def test_single_bookmaker_outcome_has_one_book_price(self):
        runner = self._make_runner()
        result = runner._find_best_odds(self._make_bookmakers())
        team_c = next(o for o in result["h2h"] if o["name"] == "TeamC")
        assert len(team_c["book_prices"]) == 1
        assert team_c["book_prices"][0]["bookmaker"] == "betmgm"

    def test_missing_bookmaker_key_falls_back_to_unknown(self):
        runner = self._make_runner()
        bookmakers = [{"markets": [{"key": "h2h", "outcomes": [
            {"name": "TeamX", "price": -110}
        ]}]}]
        result = runner._find_best_odds(bookmakers)
        assert result["h2h"][0]["book_prices"][0]["bookmaker"] == "unknown"

    def test_price_field_unchanged_for_backward_compat(self):
        runner = self._make_runner()
        result = runner._find_best_odds(self._make_bookmakers())
        for outcome in result["h2h"]:
            assert "price" in outcome

    def test_empty_bookmakers_returns_empty_dict(self):
        runner = self._make_runner()
        assert runner._find_best_odds([]) == {}

    def test_multiple_markets_segregated_correctly(self):
        runner = self._make_runner()
        bookmakers = [{"key": "dk", "markets": [
            {"key": "h2h", "outcomes": [{"name": "TeamA", "price": -110}]},
            {"key": "spreads", "outcomes": [{"name": "TeamA", "price": -115}]},
        ]}]
        result = runner._find_best_odds(bookmakers)
        assert "h2h" in result and "spreads" in result
        assert result["h2h"][0]["price"] == -110
        assert result["spreads"][0]["price"] == -115
