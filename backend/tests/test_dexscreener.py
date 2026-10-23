"""DexScreener provider tests with a fake HTTP transport (no internet needed)."""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

os.environ.setdefault("JWT_SECRET", "t" * 48)
os.environ.setdefault("APP_ENV", "development")

import httpx
import pytest

from app.providers.base import AssetRef, ProviderBadData, ProviderUnavailable
from app.providers.dexscreener import DexScreenerProvider

NOW = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
MINT = "CceCXFy4UeXheTpf8sn1bpECxMQeH5BTyxQK4BdRMf2T"
REF = AssetRef("WIENER", MINT)


def pair(price="0.00001234", liq=50_000, base=MINT, chain="solana", dex="raydium", addr="P1"):
    return {"chainId": chain, "dexId": dex, "pairAddress": addr, "baseToken": {"address": base, "symbol": "WIENER"},
            "quoteToken": {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL"},
            "priceUsd": price, "liquidity": {"usd": liq, "base": 1, "quote": 1}}


def make(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DexScreenerProvider("https://dex.test", client=client, now_fn=lambda: NOW, **kw)


def ok(body, status=200):
    return httpx.Response(status, text=json.dumps(body), headers={"content-type": "application/json"})


def test_picks_deepest_pool_exact_decimal_and_calls_documented_path():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return ok([pair("0.00001230", 30_000, addr="P1"), pair("0.00001234", 90_000, addr="P2")])

    q = make(handler).fetch_prices([REF])
    assert seen == [f"https://dex.test/token-pairs/v1/solana/{MINT}"]
    assert len(q) == 1 and q[0].symbol == "WIENER" and q[0].source == "dexscreener"
    assert q[0].price == Decimal("0.00001234") and q[0].fetched_at == NOW and q[0].source_updated_at is None
    assert q[0].raw["pair"] == "P2" and q[0].raw["pools_considered"] == 2


def test_accepts_wrapped_pairs_shape():
    assert make(lambda r: ok({"pairs": [pair()]})).fetch_prices([REF])[0].price == Decimal("0.00001234")


def test_thin_pool_is_left_out():
    assert make(lambda r: ok([pair(liq=5_000)])).fetch_prices([REF]) == []


def test_wrong_base_token_or_chain_is_ignored():
    assert make(lambda r: ok([pair(base="Other" * 8)])).fetch_prices([REF]) == []
    assert make(lambda r: ok([pair(chain="ethereum")])).fetch_prices([REF]) == []


def test_conflicting_deep_pools_give_no_price():
    body = [pair("0.00001000", 90_000, addr="A"), pair("0.00002000", 80_000, addr="B")]   # 100% apart
    assert make(lambda r: ok(body)).fetch_prices([REF]) == []
    close = [pair("0.00001000", 90_000, addr="A"), pair("0.00001050", 80_000, addr="B")]  # 5% apart
    assert make(lambda r: ok(close)).fetch_prices([REF])[0].raw["pair"] == "A"


def test_bad_prices_are_skipped():
    for bad in (None, "0", "-1", "abc", True):
        assert make(lambda r, b=bad: ok([pair(price=b)])).fetch_prices([REF]) == []


def test_implausible_mint_makes_no_request():
    def handler(req):
        raise AssertionError("no request should be made")

    p = make(handler)
    assert p.fetch_prices([AssetRef("X", ""), AssetRef("X", "../etc"), AssetRef("X", "short")]) == []


def test_errors_map_to_provider_errors():
    with pytest.raises(ProviderUnavailable):
        make(lambda r: httpx.Response(429)).fetch_prices([REF])
    with pytest.raises(ProviderUnavailable):
        make(lambda r: httpx.Response(503)).fetch_prices([REF])
    with pytest.raises(ProviderBadData):
        make(lambda r: httpx.Response(200, text="<html>")).fetch_prices([REF])
    with pytest.raises(ProviderBadData):
        make(lambda r: ok({"pairs": "nope"})).fetch_prices([REF])
    assert make(lambda r: httpx.Response(404)).fetch_prices([REF]) == []

    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderUnavailable):
        make(boom).fetch_prices([REF])
