import logging
from typing import Any, Optional

from app.models.pick import PickGrade

logger = logging.getLogger(__name__)

GRADE_THRESHOLDS = {
    "A": 0.15,
    "B": 0.08,
    "C": 0.03,
}

MIN_VIABLE_ODD = 1.50


def evaluate(
    implied_probability: float,
    decimal_odd: float,
    historical_win_rate: Optional[float] = None,
) -> dict[str, Any]:
    """Compute expected value and assign a grade."""
    win_prob = historical_win_rate if historical_win_rate is not None else implied_probability

    if decimal_odd < MIN_VIABLE_ODD:
        return {"expected_value": None, "grade": PickGrade.C, "viable": False}

    ev = (win_prob * (decimal_odd - 1)) - (1 - win_prob)
    grade = _assign_grade(ev)
    viable = ev >= 0

    logger.info(
        "Predictor: odd=%.2f | win_prob=%.3f | EV=%.4f | grade=%s",
        decimal_odd, win_prob, ev, grade,
    )

    return {"expected_value": round(ev, 6), "grade": grade, "viable": viable}


def _assign_grade(ev: float) -> PickGrade:
    if ev >= GRADE_THRESHOLDS["A"]:
        return PickGrade.A
    elif ev >= GRADE_THRESHOLDS["B"]:
        return PickGrade.B
    return PickGrade.C
