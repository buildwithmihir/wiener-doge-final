"""Strike ladders per timeframe.

SOL (and any asset in USD_SYMBOLS): fixed DOLLAR steps around the whole-dollar price.
Everything else (WIENER): percent bands based on volatility (about 1 sigma at the edge).
"""
from __future__ import annotations

from decimal import Decimal

USD_SYMBOLS = {"SOL"}
USD_STEPS = {
    86400:   (-3, -2, -1, 0, 1, 2, 3),          # 24h: max $3 away
    172800:  (-4, -2, -1, 0, 1, 2, 4),          # 48h: max $4 away
    604800:  (-10, -6, -3, 0, 3, 6, 10),        # 7d : max $10 away
    2592000: (-20, -12, -6, 0, 6, 12, 20),      # 30d
}
PCT_SPAN = {86400: 8, 172800: 12, 604800: 22, 2592000: 40}   # edge of the ladder, in percent
THIRDS = (-3, -2, -1, 0, 1, 2, 3)                              # steps are thirds of the span


def _round_sig(value: Decimal, digits: int = 5) -> Decimal:
    exp = value.adjusted() - (digits - 1)
    return value.quantize(Decimal(1).scaleb(exp)) if exp < 0 else value.quantize(Decimal(1))


def ladder_for(symbol: str, base, duration_seconds: int) -> list[Decimal]:
    """7 distinct ascending target prices around `base` for this asset and timeframe."""
    base = Decimal(base)
    if symbol.upper() in USD_SYMBOLS and duration_seconds in USD_STEPS:
        center = base.quantize(Decimal(1))
        out = {center + Decimal(s) for s in USD_STEPS[duration_seconds]}
    else:
        span = Decimal(PCT_SPAN.get(duration_seconds, 10)) / 100
        out = {_round_sig(base * (1 + span * Decimal(t) / 3)) for t in THIRDS}
    return sorted(t for t in out if t > 0)