"""Strike ladders, the way real prediction markets do it.

A ladder is a grid of target prices (strikes) centred on the live price. The grid spacing comes from
the volatility of the timeframe (the same VOL numbers odds.py uses for the odds), rounded to a "nice"
step (1, 2, 2.5, 5 x 10^n), so strikes are clean numbers and the odds at each strike are consistent
with how far it is from the live price.

  step      = nice(live price x horizon sigma x STEP_SIGMA)
  strikes   = centre + step x (-3 .. +3)          (7 strikes)
  near_pct  = how far from the live price a strike may be to still be shown (NEAR_SIGMA x sigma)

Tune STEP_SIGMA: smaller = tighter strikes (odds closer to 2x), bigger = wider (more far / high-odds strikes).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import ceil, log, sqrt

from app.services.odds import DEFAULT_VOL, SECONDS_PER_YEAR, VOL

STEP_SIGMA = 0.15    # gap between strikes, as a fraction of the timeframe's 1-sigma move
NEAR_SIGMA = 0.75    # strikes further than this (in sigma) are hidden in the app
STEPS = (-3, -2, -1, 0, 1, 2, 3)
_NICE = (1.0, 2.0, 2.5, 5.0, 10.0)


def horizon_sigma(symbol: str, duration_seconds: int) -> float:
    """1-sigma price move over the timeframe, as a fraction (0.034 = 3.4%)."""
    return VOL.get(symbol.upper(), DEFAULT_VOL) * sqrt(duration_seconds / SECONDS_PER_YEAR)


def near_pct(symbol: str, duration_seconds: int) -> int:
    """Max distance from the live price (in whole percent) at which a strike is still shown.
    The frontend has the same numbers in frontend/src/lib/ladder.ts."""
    return int(ceil(NEAR_SIGMA * horizon_sigma(symbol, duration_seconds) * 100 - 1e-9))


def nice_step(raw: Decimal) -> Decimal:
    """Round a positive step to the nearest of 1, 2, 2.5, 5, 10 x 10^n (nearest on a log scale)."""
    exp = raw.adjusted()
    mantissa = float(raw.scaleb(-exp))
    best = min(_NICE, key=lambda n: abs(log(n) - log(mantissa)))
    return Decimal(str(best)).scaleb(exp)


def ladder_for(symbol: str, base, duration_seconds: int) -> list[Decimal]:
    """7 distinct ascending target prices around `base` for this asset and timeframe."""
    base = Decimal(base)
    sigma = Decimal(str(round(horizon_sigma(symbol, duration_seconds) * STEP_SIGMA, 8)))
    step = nice_step(base * sigma)
    center = (base / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    return sorted(t for t in {center + step * i for i in STEPS} if t > 0)