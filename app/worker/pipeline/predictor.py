from typing import Dict, Any, Optional
import logging

from app.models.pick import PickResult, PickGrade

logger = logging.getLogger(__name__)


class Predictor:
    """
    Step 8 — Prediction Engine.

    Applies rule-based heuristics to evaluate a pick's expected value (EV)
    and assigns a confidence grade. This is intentionally stateless so it
    can be swapped for an ML model without touching the caller.
    """

    # Minimum decimal odd to consider a pick worthwhile
    MIN_VIABLE_ODD: float = 1.50

    # Expected-value thresholds for grade assignment
    GRADE_THRESHOLDS: Dict[str, float] = {
        "A": 0.15,   # EV >= 15 %
        "B": 0.08,   # EV >= 8 %
        "C": 0.03,   # EV >= 3 %
        "D": 0.0,    # EV >= 0 %  (break-even)
        "F": -1.0,   # Everything below
    }

    def evaluate(
        self,
        implied_probability: float,
        decimal_odd: float,
        historical_win_rate: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute expected value and assign a grade.

        Args:
            implied_probability: Our estimated win probability (0-1).
            decimal_odd: The decimal odd offered by the sportsbook.
            historical_win_rate: Optional override from historical data.

        Returns:
            dict with keys: expected_value, grade, viable
        """
        win_prob = historical_win_rate if historical_win_rate is not None else implied_probability

        if decimal_odd < self.MIN_VIABLE_ODD:
            logger.debug("Odd %.2f below minimum threshold — skipping.", decimal_odd)
            return {"expected_value": None, "grade": PickGrade.F, "viable": False}

        # EV = (win_prob * (decimal_odd - 1)) - (1 - win_prob)
        ev = (win_prob * (decimal_odd - 1)) - (1 - win_prob)

        grade = self._assign_grade(ev)
        viable = ev >= 0

        logger.info(
            "Predictor result — odd: %.2f | win_prob: %.3f | EV: %.4f | grade: %s",
            decimal_odd, win_prob, ev, grade,
        )

        return {"expected_value": round(ev, 6), "grade": grade, "viable": viable}

    def _assign_grade(self, ev: float) -> str:
        """Map expected-value float to a letter grade."""
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if ev >= threshold:
                return grade
        return PickGrade.F


# Module-level singleton for use inside Celery tasks
predictor = Predictor()
