"""Tests for the CoinGecko provider using a fake HTTP transport (no internet needed).

Run from the backend folder (no pytest needed):
    python -m tests.test_coingecko
"""
import os
from datetime import datetime, timezone
from decimal import Decimal

# Independent of backend/.env: env vars override the .env file.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"
os.environ["COINGECKO_API_KEY"] = "demo-key-123"

import httpx

from app.providers.base import AssetRef, ProviderBadData, ProviderUnavailable
from app.providers.coingecko import CoinGeckoProvider

NOW = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)
DEMO_URL = "https://api.coingecko.com/api/v3"
PRO_URL = "https://pro-api.coingecko.com/api/v3"
SOL = AssetRef("SOL", "solana")
WIENER = AssetRef("WIENER", "wiener-doge")


def make(handler, base_url=DEMO_URL, api_key="demo-key-123"):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CoinGeckoProvider(base_url, api_key, client=client, now_fn=lambda: NOW)


def json_response(text, status=200):
    return httpx.Response(status, text=text, headers={"content-type": "application/json"})


def expect(exc_type, func):
    try:
        func()
    except exc_type:
        return
    raise AssertionError(f"expected {exc_type.__name__}")


def test_happy_path_request_and_quote():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response('{"solana": {"usd": 119.41, "last_updated_at": 1792000000}}')

    quotes = make(handler).fetch_prices([SOL])
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/api/v3/simple/price"
    params = dict(request.url.params)
    assert params["ids"] == "solana" and params["vs_currencies"] == "usd"
    assert params["include_last_updated_at"] == "true"
    assert request.headers["x-cg-demo-api-key"] == "demo-key-123"

    q = quotes[0]
    assert q.symbol == "SOL" and q.source == "coingecko"
    assert q.price == Decimal("119.41")
    assert q.fetched_at == NOW
    assert q.source_updated_at == datetime.fromtimestamp(1792000000, tz=timezone.utc)


def test_pro_url_uses_pro_header():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response('{"solana": {"usd": 1}}')

    make(handler, base_url=PRO_URL, api_key="pro-key").fetch_prices([SOL])
    assert seen[0].headers["x-cg-pro-api-key"] == "pro-key"
    assert "x-cg-demo-api-key" not in seen[0].headers


def test_no_key_sends_no_auth_header():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response('{"solana": {"usd": 1}}')

    make(handler, api_key="").fetch_prices([SOL])
    assert "x-cg-demo-api-key" not in seen[0].headers and "x-cg-pro-api-key" not in seen[0].headers


def test_price_keeps_full_precision():
    quotes = make(lambda r: json_response('{"solana": {"usd": 0.000012345678901}}')).fetch_prices([SOL])
    assert quotes[0].price == Decimal("0.000012345678901")


def test_one_request_for_many_assets_and_deduped_ids():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response('{"solana": {"usd": 119.4}, "wiener-doge": {"usd": 0.001}}')

    quotes = make(handler).fetch_prices([SOL, WIENER, AssetRef("SOL2", "solana")])
    assert len(seen) == 1
    assert dict(seen[0].url.params)["ids"] == "solana,wiener-doge"
    assert [q.symbol for q in quotes] == ["SOL", "WIENER", "SOL2"]


def test_missing_asset_is_omitted_not_invented():
    quotes = make(lambda r: json_response('{"solana": {"usd": 119.4}}')).fetch_prices([SOL, WIENER])
    assert [q.symbol for q in quotes] == ["SOL"]


def test_invalid_prices_are_omitted():
    for body in (
        '{"solana": {"usd": null}}',
        '{"solana": {"usd": 0}}',
        '{"solana": {"usd": -3}}',
        '{"solana": {"usd": "abc"}}',
        '{"solana": {"usd": true}}',
        '{"solana": {}}',
        '{"solana": 5}',
        "{}",
    ):
        assert make(lambda r, b=body: json_response(b)).fetch_prices([SOL]) == [], body


def test_missing_timestamp_gives_none():
    q = make(lambda r: json_response('{"solana": {"usd": 119.4}}')).fetch_prices([SOL])[0]
    assert q.source_updated_at is None


def test_http_errors_map_to_provider_errors():
    for status in (429, 500, 503, 401, 403):
        expect(ProviderUnavailable, lambda s=status: make(lambda r: httpx.Response(s)).fetch_prices([SOL]))
    expect(ProviderBadData, lambda: make(lambda r: httpx.Response(400)).fetch_prices([SOL]))


def test_bad_json_and_wrong_shape():
    expect(ProviderBadData, lambda: make(lambda r: json_response("not json")).fetch_prices([SOL]))
    expect(ProviderBadData, lambda: make(lambda r: json_response("[1, 2]")).fetch_prices([SOL]))


def test_network_failure_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("boom")

    expect(ProviderUnavailable, lambda: make(handler).fetch_prices([SOL]))


def test_no_refs_makes_no_request():
    def handler(request):
        raise AssertionError("no request should be made")

    assert make(handler).fetch_prices([]) == []
    assert make(handler).fetch_prices([AssetRef("SOL", "  ")]) == []


def test_from_settings_uses_configured_key():
    provider = CoinGeckoProvider.from_settings()
    assert provider._headers == {"x-cg-demo-api-key": "demo-key-123"}
    provider.close()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
