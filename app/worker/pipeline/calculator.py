from itertools import combinations


def american_to_decimal(odds_american: int) -> float:
    """Convert American odds to decimal format.

    Raises ValueError for values in the invalid range (-100, 100) exclusive.
    """
    if -100 < odds_american < 100:
        raise ValueError(
            f"odds_american {odds_american} invalid: must be <= -100 or >= 100"
        )
    if odds_american > 0:
        return round(odds_american / 100 + 1, 4)
    else:
        return round(100 / abs(odds_american) + 1, 4)


def calc_implied_prob(odds_decimal: float) -> float:
    """Calculate implied win probability from decimal odds: 1 / decimal."""
    if odds_decimal <= 0:
        raise ValueError("Decimal odds must be positive")
    return round(1 / odds_decimal, 4)


def calc_clv(bet_odds: float, closing_odds: float) -> float:
    """Closing Line Value: (bet_odds / closing_odds - 1) * 100."""
    if closing_odds <= 0:
        raise ValueError("Closing odds must be positive")
    return round((bet_odds / closing_odds - 1) * 100, 2)


def build_parlay_suggestions(
    picks: list[dict],
    min_odds_total: float = 1.80,
    max_legs: int = 4,
) -> list[dict]:
    """Generate parlay combinations from a list of picks.

    Each pick dict must have: pick_id, match_id, odds_decimal, grade.
    Excludes combos with duplicate matches and those below min_odds_total.
    """
    if len(picks) < 2:
        return []

    suggestions = []
    for size in range(2, min(len(picks), max_legs) + 1):
        for combo in combinations(picks, size):
            match_ids = [p["match_id"] for p in combo]
            if len(match_ids) != len(set(match_ids)):
                continue

            odds_total = 1.0
            for p in combo:
                odds_total *= p["odds_decimal"]
            odds_total = round(odds_total, 4)

            if odds_total >= min_odds_total:
                suggestions.append({
                    "picks": list(combo),
                    "odds_total": odds_total,
                    "pick_ids": [p["pick_id"] for p in combo],
                })

    suggestions.sort(key=lambda x: x["odds_total"], reverse=True)
    return suggestions
