"""Tests for feed-health rules and market pause/reopen decisions.

Run from the backend folder (no pytest needed):
    python -m tests.test_health
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.providers.base import PriceQuote
from app.providers.health import (
    AUTO_PAUSE_PREFIX,
    FeedStatus,
    HealthPolicy,
    MarketAction,
    auto_pause_reason,
    count_consecutive_healthy,
    decide_market_action,
    evaluate_feed,
)

NOW = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
POLICY = HealthPolicy(
    stale_after_seconds=120,
    max_move_bps=1500,
    required_healthy_checks=3,
    min_liquidity_usd={"WIENER": Decimal("5000")},
)


def quote(price="119.40", fetched=NOW, updated=None, symbol="SOL"):
    return PriceQuote(symbol, Decimal(price), "test", fetched, updated)


def check(q, symbol="SOL", **kwargs):
    return evaluate_feed(symbol, q, NOW, POLICY, **kwargs)


def test_healthy_when_fresh_and_within_limits():
    h = check(quote(), previous_price=Decimal("119.00"))
    assert h.status == FeedStatus.HEALTHY and h.healthy and h.reason == "ok"
    assert h.store_snapshot and not h.is_stale and not h.is_anomalous
    assert h.price == Decimal("119.40")


def test_no_previous_price_is_fine():
    assert check(quote()).healthy


def test_missing_and_error_have_nothing_to_store():
    missing = check(None)
    assert missing.status == FeedStatus.MISSING and missing.reason == "no_data" and not missing.store_snapshot
    error = check(None, provider_error="ProviderUnavailable: rate limited")
    assert error.status == FeedStatus.ERROR and "rate limited" in error.detail and not error.store_snapshot


def test_stale_price_is_stored_but_flagged():
    h = check(quote(fetched=NOW, updated=NOW - timedelta(seconds=600)))
    assert h.status == FeedStatus.STALE and h.is_stale and h.store_snapshot and not h.healthy


def test_future_timestamp_is_anomalous():
    h = check(quote(updated=NOW + timedelta(minutes=10)))
    assert h.status == FeedStatus.ANOMALOUS and h.reason == "future_timestamp" and h.is_anomalous


def test_abnormal_move_flagged_and_boundary_ok():
    big = check(quote("120"), previous_price=Decimal("100"))      # 2000 bps
    assert big.status == FeedStatus.ANOMALOUS and big.reason == "abnormal_move" and big.store_snapshot
    edge = check(quote("115"), previous_price=Decimal("100"))     # exactly 1500 bps
    assert edge.healthy


def test_genuine_repricing_recovers_next_check():
    first = check(quote("130"), previous_price=Decimal("100"))    # jump flagged once
    assert first.status == FeedStatus.ANOMALOUS
    second = check(quote("130.5"), previous_price=Decimal("130")) # stable at the new level
    assert second.healthy


def test_stale_takes_precedence_over_move():
    h = check(quote("200", updated=NOW - timedelta(seconds=900)), previous_price=Decimal("100"))
    assert h.status == FeedStatus.STALE


def test_liquidity_gate_only_applies_to_configured_assets():
    low = check(quote("0.08", symbol="WIENER"), symbol="WIENER", liquidity_usd=Decimal("1000"))
    assert low.status == FeedStatus.ANOMALOUS and low.reason == "low_liquidity"
    unknown = check(quote("0.08", symbol="WIENER"), symbol="WIENER", liquidity_usd=None)
    assert unknown.reason == "liquidity_unknown" and not unknown.healthy
    enough = check(quote("0.08", symbol="WIENER"), symbol="WIENER", liquidity_usd=Decimal("5000"))
    assert enough.healthy
    sol = check(quote(), symbol="SOL", liquidity_usd=None)   # no gate configured for SOL
    assert sol.healthy


def test_symbol_is_normalised_to_upper_case():
    assert check(quote(), symbol="sol").symbol == "SOL"


def test_policy_defaults_and_custom_settings():
    default = HealthPolicy.from_settings({})
    assert (default.stale_after_seconds, default.max_move_bps, default.required_healthy_checks) == (120, 1500, 3)
    assert default.min_liquidity_usd == {}

    custom = HealthPolicy.from_settings(
        {
            "price.stale_after_seconds": 300,
            "price.max_move_bps_per_check": 2000,
            "price.reopen_after_healthy_checks": 5,
            "price.min_liquidity_usd.wiener": 7500,
            "wallet.signup_grant": 1000000000,  # unrelated keys are ignored
        }
    )
    assert (custom.stale_after_seconds, custom.max_move_bps, custom.required_healthy_checks) == (300, 2000, 5)
    assert custom.min_liquidity_usd == {"WIENER": Decimal("7500")}


def test_policy_rejects_invalid_settings():
    for bad in (
        {"price.stale_after_seconds": 0},
        {"price.max_move_bps_per_check": -5},
        {"price.reopen_after_healthy_checks": 0},
        {"price.stale_after_seconds": "abc"},
        {"price.min_liquidity_usd.wiener": -1},
        {"price.min_liquidity_usd.": 10},
    ):
        try:
            HealthPolicy.from_settings(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid settings {bad}")


def test_auto_pause_reason_prefix():
    h = check(None)
    assert auto_pause_reason(h) == AUTO_PAUSE_PREFIX + "no_data" == "auto:no_data"


def test_count_consecutive_healthy():
    assert count_consecutive_healthy([]) == 0
    assert count_consecutive_healthy(["healthy", "healthy", "stale", "healthy"]) == 2
    assert count_consecutive_healthy(["stale", "healthy", "healthy"]) == 0
    assert count_consecutive_healthy(["healthy"] * 5) == 5


def act(status, reason, feed, healthy_n, betting_open=True):
    return decide_market_action(status, reason, feed, healthy_n, betting_open, POLICY)


def test_open_market_pauses_on_unhealthy_feed_only():
    for feed in (FeedStatus.STALE, FeedStatus.MISSING, FeedStatus.ANOMALOUS, FeedStatus.ERROR):
        assert act("open", None, feed, 0) == MarketAction.PAUSE
    assert act("open", None, FeedStatus.HEALTHY, 10) == MarketAction.NONE


def test_auto_paused_market_reopens_only_after_enough_healthy_checks():
    assert act("paused", "auto:stale_price", FeedStatus.HEALTHY, 2) == MarketAction.NONE
    assert act("paused", "auto:stale_price", FeedStatus.HEALTHY, 3) == MarketAction.REOPEN
    assert act("paused", "auto:stale_price", FeedStatus.STALE, 9) == MarketAction.NONE


def test_admin_paused_market_never_reopens_automatically():
    assert act("paused", "maintenance by admin", FeedStatus.HEALTHY, 99) == MarketAction.NONE
    assert act("paused", None, FeedStatus.HEALTHY, 99) == MarketAction.NONE
    assert act("paused", "", FeedStatus.HEALTHY, 99) == MarketAction.NONE


def test_no_reopen_after_betting_window_ended():
    assert act("paused", "auto:no_data", FeedStatus.HEALTHY, 99, betting_open=False) == MarketAction.NONE


def test_other_statuses_are_left_alone():
    for status in ("draft", "closed", "settling", "settled", "voided"):
        assert act(status, None, FeedStatus.ERROR, 0) == MarketAction.NONE


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
