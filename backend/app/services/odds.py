"""Odds from distance to the current price (lognormal model). Shown to users as a SIMULATED multiplier.

p_above = P(price at close >= strike). payout = (1 - margin) / p, so the far side pays a lot
and the likely side pays little. Tune VOL / MARGIN to taste."""
from __future__ import annotations

from math import erf, log, sqrt

VOL = {"SOL": 0.65, "WIENER": 1.6}   # annualised volatility
DEFAULT_VOL = 0.8
MARGIN = 0.075                                    # at-the-money => (1-0.075)/0.5 = 1.85x
MIN_BPS, MAX_BPS = 10_500, 100_000                # 1.05x .. 10x (DB limit)
SECONDS_PER_YEAR = 31_536_000


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