"""Pure tests for the worker's polling rule (no database needed).

Run from the backend folder:
    python -m tests.test_worker
"""
import os

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.services.worker import needs_poll


def test_never_checked_is_always_due():
    assert needs_poll(None, False, 600, 60)
    assert needs_poll(None, True, 600, 60)


def test_normal_interval():
    assert not needs_poll(30, False, 600, 60)
    assert not needs_poll(500, False, 600, 60)
    assert needs_poll(600, False, 600, 60)
    assert needs_poll(5000, False, 600, 60)


def test_near_close_polls_every_minute():
    assert not needs_poll(20, True, 600, 60)
    assert needs_poll(60, True, 600, 60)
    assert needs_poll(58, True, 600, 60)          # scheduler jitter tolerance (5s)


def test_tolerance_does_not_make_normal_polling_too_eager():
    assert not needs_poll(580, False, 600, 60)
    assert needs_poll(595, False, 600, 60)


def test_monthly_call_budget_is_inside_the_free_quota():
    # Claude's estimate, not a measurement: 10 min polling + 3 closing windows/day of 15 one-minute polls
    per_month = 30 * (24 * 6 + 3 * 15)
    assert per_month < 10_000, per_month


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
