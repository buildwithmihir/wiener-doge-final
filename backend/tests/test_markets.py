"""Pure tests for market helpers (no database needed).

Run from the backend folder (no pytest needed):
    python -m tests.test_markets
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.core.errors import AppError
from app.services.markets import compute_schedule, parse_target_price, validate_pause_reason

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def expect_error(code, func):
    try:
        func()
    except AppError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}"
        return
    raise AssertionError(f"expected AppError({code})")


def test_target_price_parsing():
    assert parse_target_price("119.40") == Decimal("119.40")
    assert parse_target_price(0.1) == Decimal("0.1")
    assert parse_target_price("0.000000000001") == Decimal("0.000000000001")
    for bad in (None, True, "", "abc", "0", "-1", "nan", "inf", "1.0000000000001", "1e30", []):
        expect_error("invalid_target_price", lambda b=bad: parse_target_price(b))


def test_schedule_math():
    s = compute_schedule(T0, 86400, 3600)
    assert s.opens_at == T0
    assert s.closes_at == T0 + timedelta(days=1)
    assert s.betting_closes_at == T0 + timedelta(hours=23)
    assert compute_schedule(T0, 604800, 0).betting_closes_at == T0 + timedelta(days=7)


def test_schedule_rejects_bad_input():
    expect_error("invalid_duration", lambda: compute_schedule(T0, 3600, 600))
    expect_error("invalid_time", lambda: compute_schedule(T0.replace(tzinfo=None), 86400, 600))
    expect_error("invalid_time", lambda: compute_schedule(T0, 86400, 86400))
    expect_error("invalid_time", lambda: compute_schedule(T0, 86400, -1))


def test_pause_reason_rules():
    assert validate_pause_reason("  maintenance ") == "maintenance"
    for bad in (None, "", "   ", "x" * 301, "auto:stale_price", "AUTO:fake"):
        try:
            validate_pause_reason(bad)
        except AppError:
            continue
        raise AssertionError(f"accepted {bad!r}")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
