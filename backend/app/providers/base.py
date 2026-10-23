"""Price-provider interface and safety helpers.

Rules every provider must follow:
  * Return ONLY real data from the source. If an asset has no data, leave it out
    of the result. Never guess, interpolate or invent a price.
  * Raise ProviderUnavailable when the whole call fails (network, HTTP error,
    rate limit) and ProviderBadData when the source returns malformed data.
  * Prices are exact Decimals, never floats.

The worker stores accepted quotes in market_price_snapshots and pauses new
predictions when the feed is stale, missing or abnormal. Abnormal-move checks
are a safety net against bad data, NOT a guarantee against manipulation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from enum import Enum
from typing import Any, Sequence


class ProviderError(Exception):
    """Base class for all price-provider failures."""


class ProviderUnavailable(ProviderError):
    """The source could not be reached or refused the request (timeout, 5xx, 429...)."""


class ProviderBadData(ProviderError):
    """The source answered, but the data is missing, malformed or not trustworthy."""


@dataclass(frozen=True)
class AssetRef:
    """What a provider needs to look an asset up (e.g. a CoinGecko id or a token mint)."""

    symbol: str
    provider_ref: str


@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    price: Decimal
    source: str
    fetched_at: datetime                     # when WE received it (UTC, tz-aware)
    source_updated_at: datetime | None = None  # when the SOURCE says the price was updated
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.symbol or not self.source:
            raise ProviderBadData("quote needs a symbol and a source")
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price <= 0:
            raise ProviderBadData("quote price must be a positive finite Decimal")
        for name in ("fetched_at", "source_updated_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ProviderBadData(f"{name} must be timezone-aware")


class QuoteProblem(str, Enum):
    OK = "ok"
    STALE = "stale"
    FUTURE = "future_timestamp"


def to_decimal(value: Any, field_name: str = "price") -> Decimal:
    """Convert a JSON number/string to an exact positive Decimal, or raise ProviderBadData."""
    if value is None or isinstance(value, bool):
        raise ProviderBadData(f"{field_name} is missing or not a number")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ProviderBadData(f"{field_name} is not a valid number") from None
    if not number.is_finite() or number <= 0:
        raise ProviderBadData(f"{field_name} must be a positive finite number")
    return number


def check_quote_freshness(
    quote: PriceQuote,
    now: datetime,
    stale_after_seconds: int,
    max_future_skew_seconds: int = 30,
) -> QuoteProblem:
    """Policy: judge age by the source's own timestamp when it gives one, else by our fetch time."""
    reference = quote.source_updated_at or quote.fetched_at
    if reference > now + timedelta(seconds=max_future_skew_seconds):
        return QuoteProblem.FUTURE
    if (now - reference).total_seconds() > stale_after_seconds:
        return QuoteProblem.STALE
    return QuoteProblem.OK


def move_bps(previous: Decimal, current: Decimal) -> int:
    """Absolute price move between two quotes in basis points (1 bp = 0.01%), rounded up."""
    if previous <= 0 or current <= 0:
        raise ValueError("prices must be positive")
    change = abs(current - previous) * Decimal(10000) / previous
    return int(change.to_integral_value(rounding=ROUND_CEILING))


def is_abnormal_move(previous: Decimal, current: Decimal, max_move_bps: int) -> bool:
    return move_bps(previous, current) > max_move_bps


class PriceProvider(ABC):
    """A replaceable source of prices. Implementations are synchronous and stateless."""

    key: str  # stable identifier stored with every snapshot, e.g. "coingecko"

    @abstractmethod
    def fetch_prices(self, refs: Sequence[AssetRef]) -> list[PriceQuote]:
        """Return real quotes for the assets it has data for; omit the rest."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release network resources (override if needed)."""
