"""Tests for the mock price provider (dev/test only).

Run from the backend folder (no pytest needed):
    python -m tests.test_mock_provider
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

# Independent of backend/.env: env vars override the .env file.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.providers import mock_provider
from app.providers.base import (
    AssetRef,
    ProviderBadData,
    ProviderError,
    ProviderUnavailable,
    QuoteProblem,
    check_quote_freshness,
)
from app.providers.mock_provider import MockProvider

NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
SOL = AssetRef("SOL", "solana")
WIENER = AssetRef("WIENER", "some-mint")


def make(**prices):
    return MockProvider(prices or {"SOL": "119.40"}, now_fn=lambda: NOW)


def test_returns_only_configured_assets():
    quotes = make().fetch_prices([SOL, WIENER])
    assert [q.symbol for q in quotes] == ["SOL"]  # WIENER has no data => omitted, not invented
    assert quotes[0].price == Decimal("119.40")


def test_quotes_are_clearly_marked_as_mock():
    q = make().fetch_prices([SOL])[0]
    assert q.source == "mock" and q.raw == {"mock": True}
    assert MockProvider.is_simulated is True


def test_set_price_validates():
    provider = make()
    for bad in (0, -5, "abc", None, True):
        try:
            provider.set_price("SOL", bad)
        except ProviderBadData:
            continue
        raise AssertionError(f"accepted bad price {bad!r}")


def test_jump_moves_price_by_percent():
    provider = make(SOL="100")
    assert provider.jump("SOL", 10) == Decimal("110")
    assert provider.jump("SOL", -50) == Decimal("55")
    try:
        provider.jump("SOL", -100)
    except ProviderBadData:
        pass
    else:
        raise AssertionError("price must not reach zero")


def test_go_stale_is_detected_and_set_price_refreshes():
    provider = make()
    provider.go_stale("SOL", 600)
    q = provider.fetch_prices([SOL])[0]
    assert check_quote_freshness(q, NOW, 120) == QuoteProblem.STALE
    provider.set_price("SOL", "119.50")
    q = provider.fetch_prices([SOL])[0]
    assert check_quote_freshness(q, NOW, 120) == QuoteProblem.OK


def test_remove_simulates_missing_data():
    provider = make()
    provider.remove("SOL")
    assert provider.fetch_prices([SOL]) == []


def test_fail_next_raises_once():
    provider = make()
    provider.fail_next()
    try:
        provider.fetch_prices([SOL])
    except ProviderUnavailable:
        pass
    else:
        raise AssertionError("expected ProviderUnavailable")
    assert len(provider.fetch_prices([SOL])) == 1  # recovers on the next call


def test_unknown_asset_controls_raise_keyerror():
    provider = make()
    for action in (lambda: provider.jump("NOPE", 5), lambda: provider.go_stale("NOPE", 5)):
        try:
            action()
        except KeyError:
            continue
        raise AssertionError("expected KeyError")


def test_refuses_to_run_in_production():
    original = mock_provider.get_settings
    mock_provider.get_settings = lambda: SimpleNamespace(is_production=True)
    try:
        MockProvider({"SOL": "1"})
    except ProviderError:
        pass
    else:
        raise AssertionError("MockProvider must refuse production")
    finally:
        mock_provider.get_settings = original


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
