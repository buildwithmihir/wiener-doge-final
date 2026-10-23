"""Tests for the price-provider base: number parsing, freshness, abnormal moves.

Run from the backend folder (no pytest needed):
    python -m tests.test_price_feeds
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.providers.base import (
    AssetRef,
    PriceProvider,
    PriceQuote,
    ProviderBadData,
    QuoteProblem,
    check_quote_freshness,
    is_abnormal_move,
    move_bps,
    to_decimal,
)

NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)


def quote(price="119.41", fetched=NOW, updated=None):
    return PriceQuote("SOL", Decimal(price), "test", fetched, updated)


def expect_bad(func):
    try:
        func()
    except ProviderBadData:
        return
    raise AssertionError("expected ProviderBadData")


def test_to_decimal_is_exact():
    assert to_decimal(119.41) == Decimal("119.41")
    assert to_decimal("0.00000123") == Decimal("0.00000123")
    assert to_decimal(5) == Decimal("5")
    assert to_decimal(1e-7) == Decimal("1E-7")


def test_to_decimal_rejects_garbage():
    for bad in (None, True, False, 0, -1, "0", "-5", "abc", "", "nan", "inf", float("inf"), float("nan")):
        expect_bad(lambda b=bad: to_decimal(b))


def test_quote_requires_positive_decimal_and_aware_times():
    expect_bad(lambda: PriceQuote("SOL", Decimal("0"), "test", NOW))
    expect_bad(lambda: PriceQuote("SOL", Decimal("-1"), "test", NOW))
    expect_bad(lambda: PriceQuote("SOL", 119.41, "test", NOW))  # float, not Decimal
    expect_bad(lambda: PriceQuote("SOL", Decimal("1"), "test", datetime(2026, 1, 1)))  # naive time
    expect_bad(lambda: PriceQuote("SOL", Decimal("1"), "", NOW))
    expect_bad(lambda: PriceQuote("", Decimal("1"), "test", NOW))


def test_fresh_quote_ok():
    assert check_quote_freshness(quote(fetched=NOW), NOW, 120) == QuoteProblem.OK


def test_stale_quote_detected():
    old = NOW - timedelta(seconds=300)
    assert check_quote_freshness(quote(fetched=old), NOW, 120) == QuoteProblem.STALE


def test_source_timestamp_wins_over_fetch_time():
    # We fetched just now, but the source's own price is 10 minutes old => stale.
    q = quote(fetched=NOW, updated=NOW - timedelta(minutes=10))
    assert check_quote_freshness(q, NOW, 120) == QuoteProblem.STALE


def test_future_timestamp_detected():
    q = quote(fetched=NOW, updated=NOW + timedelta(minutes=5))
    assert check_quote_freshness(q, NOW, 120) == QuoteProblem.FUTURE


def test_move_bps_and_abnormal():
    assert move_bps(Decimal("100"), Decimal("101")) == 100
    assert move_bps(Decimal("100"), Decimal("90")) == 1000
    assert move_bps(Decimal("100"), Decimal("100")) == 0
    assert move_bps(Decimal("3"), Decimal("3.0001")) == 1  # 0.33 bps rounds UP, never hides a move
    assert is_abnormal_move(Decimal("100"), Decimal("120"), 1500) is True    # 2000 bps
    assert is_abnormal_move(Decimal("100"), Decimal("114"), 1500) is False   # 1400 bps
    assert is_abnormal_move(Decimal("100"), Decimal("115"), 1500) is False   # exactly 1500
    try:
        move_bps(Decimal("0"), Decimal("1"))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for zero previous price")


def test_provider_interface():
    try:
        PriceProvider()  # abstract: cannot be created directly
    except TypeError:
        pass
    else:
        raise AssertionError("PriceProvider should be abstract")

    class Fake(PriceProvider):
        key = "fake"

        def fetch_prices(self, refs):
            return [quote()] if refs else []

    provider = Fake()
    assert provider.fetch_prices([AssetRef("SOL", "solana")])[0].price == Decimal("119.41")
    assert provider.fetch_prices([]) == []
    provider.close()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
