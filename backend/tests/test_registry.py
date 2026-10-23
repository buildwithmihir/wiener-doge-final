"""Tests for the provider registry and fetch_all.

Run from the backend folder (no pytest needed):
    python -m tests.test_registry
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

# Independent of backend/.env: env vars override the .env file.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from app.providers.base import (
    AssetRef,
    PriceProvider,
    PriceQuote,
    ProviderBadData,
    ProviderError,
    ProviderUnavailable,
)
from app.providers.registry import (
    ProviderRegistry,
    build_default_registry,
    fetch_all,
    group_refs_by_provider,
)

NOW = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)


class Fake(PriceProvider):
    def __init__(self, key, behavior):
        self.key = key
        self._behavior = behavior
        self.calls = []

    def fetch_prices(self, refs):
        self.calls.append(list(refs))
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return [PriceQuote(r.symbol, Decimal("1.5"), self.key, NOW) for r in refs]


def settings(is_production):
    return SimpleNamespace(
        is_production=is_production,
        coingecko_base_url="https://api.coingecko.com/api/v3",
        coingecko_api_key="",
        dexscreener_base_url="https://api.dexscreener.com",
        dex_min_liquidity_usd=20000,
        dex_max_divergence_bps=1000,
    )


def test_register_get_and_duplicates():
    registry = ProviderRegistry()
    registry.register(Fake("a", None))
    assert registry.get("a").key == "a" and registry.keys() == ["a"]
    try:
        registry.register(Fake("a", None))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate registration must fail")
    try:
        registry.get("nope")
    except ProviderError:
        pass
    else:
        raise AssertionError("unknown provider must fail")


def test_default_registry_dev_has_mock_prod_does_not():
    dev = build_default_registry(settings(False))
    prod = build_default_registry(settings(True))
    assert dev.keys() == ["coingecko", "dexscreener", "mock"]
    assert prod.keys() == ["coingecko", "dexscreener"]
    dev.close_all()
    prod.close_all()


def test_group_refs_skips_unpriced_assets():
    grouped = group_refs_by_provider(
        [
            ("sol", "coingecko", "solana"),
            ("USDC", "coingecko", "usd-coin"),
            ("WIENER", None, None),        # no provider yet
            ("OTHER", "coingecko", "  "),  # blank ref
            ("X", "mock", "x"),
        ]
    )
    assert grouped == {
        "coingecko": [AssetRef("SOL", "solana"), AssetRef("USDC", "usd-coin")],
        "mock": [AssetRef("X", "x")],
    }


def test_fetch_all_collects_quotes_from_every_provider():
    registry = ProviderRegistry()
    a, b = Fake("a", None), Fake("b", None)
    registry.register(a)
    registry.register(b)
    result = fetch_all(registry, {"a": [AssetRef("SOL", "s")], "b": [AssetRef("WIENER", "w")]})
    assert sorted(q.symbol for q in result.quotes) == ["SOL", "WIENER"]
    assert result.errors == {}


def test_one_failing_provider_does_not_block_others():
    registry = ProviderRegistry()
    registry.register(Fake("good", None))
    registry.register(Fake("down", ProviderUnavailable("rate limited")))
    registry.register(Fake("bad", ProviderBadData("garbled")))
    registry.register(Fake("buggy", RuntimeError("secret internal detail")))
    grouped = {k: [AssetRef(k.upper(), k)] for k in ("good", "down", "bad", "buggy")}
    result = fetch_all(registry, grouped)

    assert [q.symbol for q in result.quotes] == ["GOOD"]
    assert result.errors["down"] == "ProviderUnavailable: rate limited"
    assert result.errors["bad"] == "ProviderBadData: garbled"
    assert result.errors["buggy"] == "RuntimeError: internal provider error"  # no internal detail leaked
    assert set(result.errors) == {"down", "bad", "buggy"}


def test_unknown_provider_key_is_reported_not_raised():
    result = fetch_all(ProviderRegistry(), {"ghost": [AssetRef("X", "x")]})
    assert result.quotes == []
    assert result.errors["ghost"].startswith("ProviderError: unknown provider")


def test_providers_only_receive_their_own_assets():
    registry = ProviderRegistry()
    a = Fake("a", None)
    registry.register(a)
    fetch_all(registry, {"a": [AssetRef("SOL", "solana")]})
    assert a.calls == [[AssetRef("SOL", "solana")]]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
