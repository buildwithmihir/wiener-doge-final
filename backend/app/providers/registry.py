"""Provider registry and the one-call "fetch everything" helper used by the worker.

assets.provider_key says which provider prices an asset and assets.provider_ref
is that provider's own identifier (CoinGecko coin id, token mint, ...). Assets
without both are simply not priced, which the market engine treats as "no
reliable price" and pauses new predictions.

fetch_all isolates failures: if one provider is down the others still deliver,
and the failure is reported per provider so feed health can be recorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.config import get_settings
from app.providers.base import AssetRef, PriceProvider, PriceQuote, ProviderError
from app.providers.coingecko import CoinGeckoProvider
from app.providers.dexscreener import DexScreenerProvider
from app.providers.mock_provider import MockProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, PriceProvider] = {}

    def register(self, provider: PriceProvider) -> None:
        if provider.key in self._providers:
            raise ValueError(f"provider '{provider.key}' is already registered")
        self._providers[provider.key] = provider

    def get(self, key: str) -> PriceProvider:
        try:
            return self._providers[key]
        except KeyError:
            raise ProviderError(f"unknown provider '{key}'") from None

    def keys(self) -> list[str]:
        return sorted(self._providers)

    def close_all(self) -> None:
        for provider in self._providers.values():
            provider.close()


def build_default_registry(settings: Any = None) -> ProviderRegistry:
    """CoinGecko and DexScreener always; the mock provider only outside production."""
    settings = settings or get_settings()
    registry = ProviderRegistry()
    registry.register(CoinGeckoProvider(settings.coingecko_base_url, settings.coingecko_api_key))
    registry.register(DexScreenerProvider(settings.dexscreener_base_url, settings.dex_min_liquidity_usd,
                                          settings.dex_max_divergence_bps))
    if not settings.is_production:
        registry.register(MockProvider())  # empty until you set prices in dev tools/tests
    return registry


def group_refs_by_provider(rows: Iterable[tuple[str, str | None, str | None]]) -> dict[str, list[AssetRef]]:
    """rows = (symbol, provider_key, provider_ref). Assets lacking a provider/ref are skipped."""
    grouped: dict[str, list[AssetRef]] = {}
    for symbol, provider_key, provider_ref in rows:
        if not provider_key or not provider_ref or not provider_ref.strip():
            continue
        grouped.setdefault(provider_key, []).append(AssetRef(symbol.upper(), provider_ref.strip()))
    return grouped


@dataclass
class FetchResult:
    quotes: list[PriceQuote] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # provider key -> safe error text


def fetch_all(registry: ProviderRegistry, grouped: dict[str, list[AssetRef]]) -> FetchResult:
    result = FetchResult()
    for provider_key, refs in grouped.items():
        try:
            provider = registry.get(provider_key)
            result.quotes.extend(provider.fetch_prices(refs))
        except ProviderError as exc:
            result.errors[provider_key] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - a buggy provider must not stop the others
            result.errors[provider_key] = f"{type(exc).__name__}: internal provider error"
    return result
