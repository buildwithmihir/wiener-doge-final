"""Pure tests for strike ladders. Run from the backend folder:  python -m tests.test_ladder"""
from decimal import Decimal

from app.services.ladder import ladder_for


def test_sol_margins_in_dollars():
    base = Decimal("119.4")
    for duration, limit in ((86400, 3), (172800, 4), (604800, 10)):
        t = ladder_for("SOL", base, duration)
        assert len(t) == 7 and t == sorted(t), (duration, t)
        assert max(abs(x - Decimal("119")) for x in t) <= limit, (duration, t)


def test_other_assets_use_percent_bands():
    base = Decimal("0.00001234")
    t = ladder_for("WIENER", base, 86400)
    assert len(t) == 7 and t == sorted(t)
    assert all(abs(x - base) / base <= Decimal("0.0801") for x in t), t


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")