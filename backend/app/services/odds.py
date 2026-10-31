"""Odds from distance to the current price (lognormal model). Shown to users as a multiplier.

p_above = P(price at close >= strike). payout = (1 - margin) / p, so the far side pays a lot
and the likely side pays little. Tune VOL / MARGIN to taste.

Cashout uses the SAME model with the time that is left: a bet that is winning right now is worth
more than its stake, a bet that is losing is worth less."""
from __future__ import annotations

from decimal import Decimal
from math import erf, log, sqrt

VOL = {"SOL": 0.65, "WIENER": 1.6}   # annualised volatility
DEFAULT_VOL = 0.8
MARGIN = 0.075                                    # at-the-money => (1-0.075)/0.5 = 1.85x
MIN_BPS, MAX_BPS = 10_500, 100_000                # 1.05x .. 10x (DB limit)
SECONDS_PER_YEAR = 31_536_000

CASHOUT_MARGIN = 0.06                             # the house keeps 6% of the fair cashout value
MIN_SECONDS_FOR_MODEL = 60                        # never model less than a minute of remaining time


def _cdf(z: float) -> float:
    return 0.5 * (1 + erf(z / sqrt(2)))


def odds_bps(symbol: str, spot, strike, duration_seconds: int) -> tuple[int, int]:
    """(above_bps, below_bps), rounded to 0.01x."""
    s, k = float(spot), float(strike)
    sigma = VOL.get(symbol.upper(), DEFAULT_VOL) * sqrt(duration_seconds / SECONDS_PER_YEAR)
    p_above = 1 - _cdf(log(k / s) / sigma)
    p_above = min(max(p_above, 0.01), 0.99)

    def to_bps(p: float) -> int:
        return int(min(MAX_BPS, max(MIN_BPS, round((1 - MARGIN) / p * 100) * 100)))

    return to_bps(p_above), to_bps(1 - p_above)


def win_probability(symbol: str, spot, strike, direction: str, seconds_left: float) -> float:
    """Chance (0..1) that this prediction wins if the market closed `seconds_left` from now."""
    s, k = float(spot), float(strike)
    sigma = VOL.get(symbol.upper(), DEFAULT_VOL) * sqrt(max(seconds_left, MIN_SECONDS_FOR_MODEL) / SECONDS_PER_YEAR)
    p_above = 1 - _cdf(log(k / s) / sigma)
    p = p_above if direction == "above" else 1 - p_above
    return min(max(p, 0.005), 0.995)


def cashout_units(potential_payout: int, probability: float) -> int:
    """Cashout value in base units: potential payout x win chance x (1 - margin). Never below 1 unit."""
    value = Decimal(int(potential_payout)) * Decimal(str(round(probability, 6))) * Decimal(str(1 - CASHOUT_MARGIN))
    return max(1, min(int(value), int(potential_payout)))