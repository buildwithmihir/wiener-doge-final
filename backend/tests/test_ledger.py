"""Pure tests for wallet helpers (no database needed).

Run from the backend folder (no pytest needed):
    python -m tests.test_ledger
"""
import os
import uuid
from decimal import Decimal

# Independent of backend/.env: env vars override the .env file.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.core.errors import AppError
from app.services.ledger import (
    MAX_ADJUSTMENT_UNITS,
    UNIT,
    adjust_demo_credits,
    explain_entry,
    format_demo,
    parse_demo,
)


def expect_error(code, func):
    try:
        func()
    except AppError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}"
        return
    raise AssertionError(f"expected AppError({code})")


def test_format_demo_is_exact():
    assert format_demo(0) == "0"
    assert format_demo(1_000_000_000) == "1000"
    assert format_demo(1_500_000) == "1.5"
    assert format_demo(1) == "0.000001"
    assert format_demo(12_345_678) == "12.345678"
    assert format_demo(-2_500_000) == "-2.5"
    assert format_demo(-1) == "-0.000001"


def test_parse_demo_accepts_valid_amounts():
    assert parse_demo("12.5") == 12_500_000
    assert parse_demo(12) == 12 * UNIT
    assert parse_demo(Decimal("0.000001")) == 1
    assert parse_demo(" 3 ") == 3 * UNIT
    assert parse_demo("-4.25") == -4_250_000
    assert parse_demo(0.1) == 100_000          # float goes through str(): 0.1, not 0.1000000000000000055
    assert parse_demo("1e3") == 1000 * UNIT


def test_parse_demo_rejects_bad_input():
    for bad in (None, True, "", "abc", "1.0000001", "nan", "inf", "-inf", 10**13, "1e999", [], {}):
        try:
            parse_demo(bad)
        except AppError as exc:
            assert exc.code == "invalid_amount", exc.code
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_parse_then_format_roundtrip():
    for text in ("0", "1", "0.5", "999.999999", "123456.1"):
        assert format_demo(parse_demo(text)) == text


def test_explanations():
    assert explain_entry("signup_grant") == "Welcome demo credits"
    assert explain_entry("loss_settle") == "Prediction lost: stake forfeited"
    assert explain_entry("something_new") == "Balance change"


def test_adjust_validation_happens_before_any_database_call():
    user, actor = uuid.uuid4(), uuid.uuid4()
    base = dict(db=None, user_id=user, actor_id=actor, reason="goodwill", idempotency_key="adjust-key-1")
    expect_error("invalid_amount", lambda: adjust_demo_credits(**{**base, "amount_units": 0}))
    expect_error("invalid_amount", lambda: adjust_demo_credits(**{**base, "amount_units": MAX_ADJUSTMENT_UNITS + 1}))
    expect_error("invalid_amount", lambda: adjust_demo_credits(**{**base, "amount_units": -MAX_ADJUSTMENT_UNITS - 1}))
    expect_error("invalid_amount", lambda: adjust_demo_credits(**{**base, "amount_units": 1.5}))
    expect_error("invalid_amount", lambda: adjust_demo_credits(**{**base, "amount_units": True}))
    expect_error("reason_required", lambda: adjust_demo_credits(**{**base, "amount_units": 5, "reason": "   "}))
    expect_error("reason_required", lambda: adjust_demo_credits(**{**base, "amount_units": 5, "reason": "x" * 501}))
    expect_error("invalid_key", lambda: adjust_demo_credits(**{**base, "amount_units": 5, "idempotency_key": "short"}))


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
