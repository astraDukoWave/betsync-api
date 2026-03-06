"""OddsCalculator: converts odds formats and computes parlay multipliers."""
from decimal import Decimal, ROUND_HALF_UP
from typing import List


class OddsCalculator:
    """Utility class for odds conversion and parlay payout calculation."""

    @staticmethod
    def american_to_decimal(american_odds: int) -> Decimal:
        """Convert American odds to decimal format."""
        if american_odds > 0:
            return Decimal(american_odds) / Decimal(100) + Decimal(1)
        else:
            return Decimal(100) / Decimal(abs(american_odds)) + Decimal(1)

    @staticmethod
    def decimal_to_american(decimal_odds: Decimal) -> int:
        """Convert decimal odds to American format."""
        if decimal_odds >= 2:
            return int((decimal_odds - 1) * 100)
        else:
            return int(-100 / (decimal_odds - 1))

    @staticmethod
    def parlay_multiplier(odds_list: List[Decimal]) -> Decimal:
        """Compute the combined parlay multiplier from a list of decimal odds."""
        multiplier = Decimal(1)
        for odd in odds_list:
            multiplier *= odd
        return multiplier.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def parlay_payout(stake: Decimal, odds_list: List[Decimal]) -> Decimal:
        """Return the total payout for a parlay given stake and legs."""
        multiplier = OddsCalculator.parlay_multiplier(odds_list)
        return (stake * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def implied_probability(decimal_odds: Decimal) -> float:
        """Calculate implied win probability from decimal odds."""
        if decimal_odds <= 0:
            raise ValueError("Decimal odds must be positive")
        return float(Decimal(1) / decimal_odds * 100)
