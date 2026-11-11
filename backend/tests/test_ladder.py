"""Pure tests for strike ladders. Run from the backend folder:  python -m tests.test_ladder"""
from decimal import Decimal

from app.services.ladder import NEAR_SIGMA, horizon_sigma, ladder_for, near_pct
from app.services.odds import odds_bps

DURATIONS = (86400, 172800, 604800, 2592000)


def test_seven_sorted_distinct_strikes_for_any_price():
    for symbol, base in (("SOL", "119.4"), ("SOL", "88.7"), ("SOL", "63.2"), ("WIENER", "0.00001234"), ("WIENER", "0.0000041")):
        for d in DURATIONS:
            t = ladder_for(symbol, Decimal(base), d)
            assert len(t) == 7 and t == sorted(t) and len(set(t)) == 7, (symbol, base, d, t)


def test_strikes_stay_inside_the_near_band():
    for symbol, base in (("SOL", "88.7"), ("SOL", "119.4"), ("WIENER", "0.00001234")):
        for d in DURATIONS:
            b = Decimal(base)
            t = ladder_for(symbol, b, d)
            edge = max(abs(x - b) for x in t)
            assert edge <= b * Decimal(str(NEAR_SIGMA * horizon_sigma(symbol, d))), (symbol, base, d, edge)
            assert edge * 100 / b <= near_pct(symbol, d), (symbol, base, d)


def test_sol_near_pct_matches_the_frontend_table():
    assert [near_pct("SOL", d) for d in DURATIONS] == [3, 4, 7, 14]
    assert [near_pct("WIENER", d) for d in DURATIONS] == [7, 9, 17, 35]


def test_sol_24h_at_88_has_no_85_strike():
    t = ladder_for("SOL", Decimal("88"), 86400)
    assert min(t) >= Decimal("86") and max(t) <= Decimal("90"), t


def test_odds_follow_the_distance():
    t = ladder_for("SOL", Decimal("88"), 86400)
    above = [odds_bps("SOL", Decimal("88"), k, 86400)[0] for k in t]
    assert above == sorted(above), above          # higher strike => ABOVE pays more
    assert all(10_500 < a < 40_000 for a in above), above


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")