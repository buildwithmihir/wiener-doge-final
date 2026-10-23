"""Pure tests for prediction input rules (no database needed).

Run from the backend folder:
    python -m tests.test_predictions
"""
import os

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.core.errors import AppError
from app.services.predictions import estimate_payout, validate_prediction_input

KEY = "key-12345678"


def expect_error(code, func):
    try:
        func()
    except AppError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}"
        return
    raise AssertionError(f"expected AppError({code})")


def test_valid_input_is_normalised():
    assert validate_prediction_input(" ABOVE ", 5_000_000, KEY) == ("above", 5_000_000, KEY)
    assert validate_prediction_input("below", 1, "x" * 120)[0] == "below"


def test_bad_direction():
    for bad in (None, "", "up", "sideways", 1):
        expect_error("invalid_direction", lambda b=bad: validate_prediction_input(b, 1, KEY))


def test_bad_stake():
    for bad in (0, -5, 1.5, "10", None, True):
        expect_error("invalid_amount", lambda b=bad: validate_prediction_input("above", b, KEY))


def test_bad_key():
    for bad in (None, "", "short", "x" * 121, 12345678):
        expect_error("invalid_key", lambda b=bad: validate_prediction_input("above", 1, b))


def test_estimate_payout_matches_database_formula():
    assert estimate_payout(10_000_000, 18000) == 18_000_000
    assert estimate_payout(1, 18000) == 1            # integer division, never below the stake
    assert estimate_payout(1_000_000, 10001) == 1_000_100


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
