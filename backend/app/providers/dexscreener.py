"""DexScreener price provider for on-chain Solana tokens such as WIENER (USD).

Endpoint used: GET {base}/token-pairs/v1/solana/{mint}  (public, no API key).
DexScreener documents the pair fields (baseToken, priceUsd as text, liquidity.usd) but its page
does not spell out the response wrapper, so the parser accepts either a bare list of pairs or
{"pairs": [...]}. Nothing here has been run against the live service from the build sandbox.

Safety rules (a thin on-chain market is easy to manipulate, so this provider is deliberately strict):
  * only pairs whose BASE token is exactly the mint are used (the price is the token's own price);
  * a pair needs at least `min_liquidity_usd` of liquidity, otherwise the asset is left out
    (-> "missing" -> markets pause) rather than trusting a thin pool;
  * the deepest qualifying pair is used, but if another qualifying pair disagrees by more than
    `max_divergence_bps` the asset is left out (conflicting sources are not averaged or guessed);
  * DexScreener gives no price timestamp, so freshness is judged by our fetch time.
These checks reduce bad data; they do NOT make an illiquid memecoin safe to settle on.
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
    ProviderUnavailable,
    move_bps,
    to_decimal,
)

CHAIN = "solana"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _pairs_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("pairs")
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ProviderBadData("DexScreener returned an unexpected response shape")
    return [p for p in payload if isinstance(p, dict)]


def _liquidity_usd(pair: dict[str, Any]) -> Decimal:
    liq = pair.get("liquidity")
    if not isinstance(liq, dict):
        return Decimal(0)
    try:
        return to_decimal(liq.get("usd"), "liquidity")
    except ProviderBadData:
        return Decimal(0)


class DexScreenerProvider(PriceProvider):
    key = "dexscreener"

    def __init__(
        self,
        base_url: str = "https://api.dexscreener.com",
        min_liquidity_usd: int = 20_000,
        max_divergence_bps: int = 1_000,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._min_liquidity = Decimal(min_liquidity_usd)
        self._max_divergence_bps = max_divergence_bps
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    @classmethod
    def from_settings(cls) -> "DexScreenerProvider":
        s = get_settings()
        return cls(s.dexscreener_base_url, s.dex_min_liquidity_usd, s.dex_max_divergence_bps)

    def fetch_prices(self, refs: Sequence[AssetRef]) -> list[PriceQuote]:
        quotes: list[PriceQuote] = []
        for ref in refs:
            mint = ref.provider_ref.strip()
            if not mint or not mint.isalnum() or not (32 <= len(mint) <= 44):
                continue  # not a plausible Solana mint: never put odd text into a URL
            quote = self._fetch_one(ref.symbol, mint)
            if quote is not None:
                quotes.append(quote)
        return quotes

    def _fetch_one(self, symbol: str, mint: str) -> PriceQuote | None:
        try:
            response = self._client.get(f"{self._base_url}/token-pairs/v1/{CHAIN}/{mint}")
        except httpx.HTTPError:
            raise ProviderUnavailable("DexScreener request failed (network or timeout)") from None
        status = response.status_code
        if status == 429:
            raise ProviderUnavailable("DexScreener rate limit reached")
        if status >= 500:
            raise ProviderUnavailable(f"DexScreener server error ({status})")
        if status == 404:
            return None
        if status != 200:
            raise ProviderBadData(f"DexScreener returned unexpected status {status}")
        fetched_at = self._now()
        try:
            payload = json.loads(response.text, parse_float=Decimal)
        except ValueError:
            raise ProviderBadData("DexScreener returned invalid JSON") from None

        candidates: list[tuple[Decimal, Decimal, dict[str, Any]]] = []   # (liquidity, price, pair)
        for pair in _pairs_from_payload(payload):
            base = pair.get("baseToken")
            if pair.get("chainId") != CHAIN or not isinstance(base, dict) or base.get("address") != mint:
                continue
            liquidity = _liquidity_usd(pair)
            if liquidity < self._min_liquidity:
                continue
            try:
                price = to_decimal(pair.get("priceUsd"), f"{symbol} price")
            except ProviderBadData:
                continue
            candidates.append((liquidity, price, pair))
        if not candidates:
            return None   # no deep-enough pool: leave it out, never guess

        candidates.sort(key=lambda c: c[0], reverse=True)
        liquidity, price, pair = candidates[0]
        if len(candidates) > 1 and move_bps(price, candidates[1][1]) > self._max_divergence_bps:
            return None   # the two deepest pools disagree: do not pick a side

        return PriceQuote(
            symbol=symbol.upper(), price=price, source=self.key, fetched_at=fetched_at,
            source_updated_at=None,
            raw={"mint": mint, "dex": pair.get("dexId"), "pair": pair.get("pairAddress"),
                 "liquidity_usd": str(liquidity), "pools_considered": len(candidates)},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
