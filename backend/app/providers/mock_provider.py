"""Mock price provider for LOCAL DEVELOPMENT AND TESTS ONLY.

It returns prices you set by hand and can simulate the failures the market
engine must survive: stale prices, missing prices, jumps and outages.

Safety:
  * It refuses to start when APP_ENV=production.
  * Every quote is labelled source="mock" with raw={"mock": True}, so simulated
    data can never be presented as verified live market data.
  * It has no built-in default prices: you must set each one explicitly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Mapping, Sequence

from app.config import get_settings
from app.providers.base import (
    AssetRef,
    PriceProvider,
    PriceQuote,
    ProviderError,
    ProviderUnavailable,
    to_decimal,
)


class MockProvider(PriceProvider):
    key = "mock"
    is_simulated = True

    def __init__(
        self,
        prices: Mapping[str, object] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        if get_settings().is_production:
            raise ProviderError("MockProvider is disabled in production")
        self._prices: dict[str, Decimal] = {}
        self._stale_seconds: dict[str, int] = {}
        self._fail_with: ProviderError | None = None
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        for symbol, price in (prices or {}).items():
            self.set_price(symbol, price)

    # ---- controls used by tests / dev tools --------------------------------
    def set_price(self, symbol: str, price: object) -> None:
        key = symbol.upper()
        self._prices[key] = to_decimal(price, f"{key} price")
        self._stale_seconds.pop(key, None)  # a freshly set price is fresh

    def jump(self, symbol: str, percent: object) -> Decimal:
        """Move the price by `percent` (e.g. 10 = +10%, -25 = -25%). Returns the new price."""
        key = symbol.upper()
        current = self._require(key)
        factor = Decimal(1) + Decimal(str(percent)) / Decimal(100)
        new_price = to_decimal(current * factor, f"{key} price")
        self._prices[key] = new_price
        return new_price

    def go_stale(self, symbol: str, seconds: int) -> None:
        """Make this asset's price look `seconds` old (source timestamp in the past)."""
        key = symbol.upper()
        self._require(key)
        self._stale_seconds[key] = seconds

    def remove(self, symbol: str) -> None:
        """Simulate missing data: the asset disappears from results."""
        self._prices.pop(symbol.upper(), None)
        self._stale_seconds.pop(symbol.upper(), None)

    def fail_next(self, error: ProviderError | None = None) -> None:
        """Make the next fetch_prices call raise (default: ProviderUnavailable)."""
        self._fail_with = error or ProviderUnavailable("mock outage")

    def _require(self, key: str) -> Decimal:
        if key not in self._prices:
            raise KeyError(f"no mock price set for {key}")
        return self._prices[key]

    # ---- PriceProvider -----------------------------------------------------
    def fetch_prices(self, refs: Sequence[AssetRef]) -> list[PriceQuote]:
        if self._fail_with is not None:
            error, self._fail_with = self._fail_with, None
            raise error

        now = self._now()
        quotes: list[PriceQuote] = []
        for ref in refs:
            key = ref.symbol.upper()
            price = self._prices.get(key)
            if price is None:
                continue  # no data => leave it out, never invent
            age = self._stale_seconds.get(key, 0)
            quotes.append(
                PriceQuote(
                    symbol=key,
                    price=price,
                    source=self.key,
                    fetched_at=now,
                    source_updated_at=now - timedelta(seconds=age),
                    raw={"mock": True},
                )
            )
        return quotes
