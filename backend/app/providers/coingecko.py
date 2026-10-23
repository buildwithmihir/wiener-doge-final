"""CoinGecko price provider (REST /simple/price, USD).

Docs checked: https://docs.coingecko.com/reference/simple-price
  * Demo (free) plan : base https://api.coingecko.com/api/v3   header x-cg-demo-api-key
  * Pro (paid) plan  : base https://pro-api.coingecko.com/api/v3  header x-cg-pro-api-key
  * Response         : {"<coin id>": {"usd": <number>, "last_updated_at": <unix seconds>}}

One HTTP call fetches every requested asset, so polling stays inside free-tier
limits. Numbers are parsed straight into Decimal (no float rounding). An asset
whose price is missing or invalid is simply left out of the result.

WIENER is an on-chain Solana token; it is not handled here yet (needs the mint
address and a DEX/on-chain source). Use provider_ref = CoinGecko coin id, e.g.
"solana" for SOL.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Sequence

import httpx

from app.config import get_settings
from app.providers.base import (
    AssetRef,
    PriceProvider,
    PriceQuote,
    ProviderBadData,
    ProviderError,
    ProviderUnavailable,
    to_decimal,
)

DEFAULT_TIMEOUT_SECONDS = 10.0


def _auth_headers(base_url: str, api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    header = "x-cg-pro-api-key" if "pro-api.coingecko.com" in base_url else "x-cg-demo-api-key"
    return {header: api_key}


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        seconds = float(value)
        if seconds <= 0:
            return None
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


class CoinGeckoProvider(PriceProvider):
    key = "coingecko"

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = _auth_headers(self._base_url, api_key)
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_settings(cls) -> "CoinGeckoProvider":
        settings = get_settings()
        return cls(settings.coingecko_base_url, settings.coingecko_api_key)

    def fetch_prices(self, refs: Sequence[AssetRef]) -> list[PriceQuote]:
        ids = list(dict.fromkeys(r.provider_ref.strip() for r in refs if r.provider_ref.strip()))
        if not ids:
            return []

        try:
            response = self._client.get(
                f"{self._base_url}/simple/price",
                params={
                    "ids": ",".join(ids),
                    "vs_currencies": "usd",
                    "include_last_updated_at": "true",
                    "precision": "full",
                },
                headers=self._headers,
            )
        except httpx.HTTPError:
            raise ProviderUnavailable("CoinGecko request failed (network or timeout)") from None

        status = response.status_code
        if status == 429:
            raise ProviderUnavailable("CoinGecko rate limit reached")
        if status in (401, 403):
            raise ProviderUnavailable("CoinGecko rejected the API key")
        if status >= 500:
            raise ProviderUnavailable(f"CoinGecko server error ({status})")
        if status != 200:
            raise ProviderBadData(f"CoinGecko returned unexpected status {status}")

        fetched_at = self._now()
        try:
            payload = json.loads(response.text, parse_float=Decimal)
        except ValueError:
            raise ProviderBadData("CoinGecko returned invalid JSON") from None
        if not isinstance(payload, dict):
            raise ProviderBadData("CoinGecko returned an unexpected response shape")

        quotes: list[PriceQuote] = []
        for ref in refs:
            entry = payload.get(ref.provider_ref.strip())
            if not isinstance(entry, dict):
                continue  # no data for this asset: leave it out, never invent
            try:
                price = to_decimal(entry.get("usd"), f"{ref.symbol} price")
            except ProviderBadData:
                continue  # invalid value: treat as missing
            updated_at = _parse_timestamp(entry.get("last_updated_at"))
            quotes.append(
                PriceQuote(
                    symbol=ref.symbol.upper(),
                    price=price,
                    source=self.key,
                    fetched_at=fetched_at,
                    source_updated_at=updated_at,
                    raw={
                        "coin_id": ref.provider_ref.strip(),
                        "last_updated_at": int(updated_at.timestamp()) if updated_at else None,
                    },
                )
            )
        return quotes

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


__all__ = ["CoinGeckoProvider", "ProviderError"]
