"""Feed-health rules and the market pause / reopen decision.

Pure logic with no database or network access, so it is easy to test. The worker
(later) feeds it quotes and stored history, then applies the result.

Statuses match provider_health_history.status in the database:
  healthy | stale | missing | anomalous | error

Policy summary
  * No quote + provider error  -> error      (new predictions pause)
  * No quote, no error         -> missing    (new predictions pause)
  * Price older than limit     -> stale      (snapshot stored, flagged is_stale)
  * Timestamp in the future    -> anomalous  (snapshot stored, flagged)
  * Move vs previous check too big -> anomalous (snapshot stored, flagged)
  * Asset has a minimum liquidity and the pool is below it, or liquidity is
    unknown -> anomalous (low_liquidity / liquidity_unknown)
  * Otherwise                  -> healthy

Moves are measured against the previous OBSERVED price, so a genuine re-price is
flagged once and then recovers; a market only reopens after several consecutive
healthy checks (no flapping). Markets paused by an admin (no "auto:" prefix in
pause_reason) are never reopened automatically.

These checks catch bad data and thin liquidity. They are NOT a guarantee against
price manipulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from app.providers.base import PriceQuote, QuoteProblem, check_quote_freshness, move_bps

AUTO_PAUSE_PREFIX = "auto:"
LIQUIDITY_KEY_PREFIX = "price.min_liquidity_usd."


class FeedStatus(str, Enum):
    HEALTHY = "healthy"
    STALE = "stale"
    MISSING = "missing"
    ANOMALOUS = "anomalous"
    ERROR = "error"


class MarketAction(str, Enum):
    NONE = "none"
    PAUSE = "pause"
    REOPEN = "reopen"


@dataclass(frozen=True)
class HealthPolicy:
    stale_after_seconds: int = 120
    max_move_bps: int = 1500
    required_healthy_checks: int = 3
    # Per-asset minimum pool liquidity in USD, e.g. {"WIENER": Decimal("5000")}.
    min_liquidity_usd: dict[str, Decimal] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, values: Mapping[str, Any]) -> "HealthPolicy":
        """Build from application_settings rows ({key: json value}). Raises ValueError if invalid."""
        stale = int(values.get("price.stale_after_seconds", 120))
        move = int(values.get("price.max_move_bps_per_check", 1500))
        required = int(values.get("price.reopen_after_healthy_checks", 3))
        if stale <= 0 or move <= 0 or required < 1:
            raise ValueError("health settings must be positive (reopen checks >= 1)")

        minimums: dict[str, Decimal] = {}
        for key, raw in values.items():
            if key.startswith(LIQUIDITY_KEY_PREFIX):
                symbol = key[len(LIQUIDITY_KEY_PREFIX):].upper()
                amount = Decimal(str(raw))
                if not symbol or not amount.is_finite() or amount < 0:
                    raise ValueError(f"invalid liquidity setting {key}")
                minimums[symbol] = amount
        return cls(stale, move, required, minimums)


@dataclass(frozen=True)
class FeedHealth:
    symbol: str
    status: FeedStatus
    reason: str
    detail: str
    price: Decimal | None = None

    @property
    def healthy(self) -> bool:
        return self.status == FeedStatus.HEALTHY

    @property
    def store_snapshot(self) -> bool:
        """Real data worth recording (flagged if needed). Nothing to store without a quote."""
        return self.status in (FeedStatus.HEALTHY, FeedStatus.STALE, FeedStatus.ANOMALOUS)

    @property
    def is_stale(self) -> bool:
        return self.status == FeedStatus.STALE

    @property
    def is_anomalous(self) -> bool:
        return self.status == FeedStatus.ANOMALOUS


def evaluate_feed(
    symbol: str,
    quote: PriceQuote | None,
    now: datetime,
    policy: HealthPolicy,
    previous_price: Decimal | None = None,
    liquidity_usd: Decimal | None = None,
    provider_error: str | None = None,
) -> FeedHealth:
    symbol = symbol.upper()

    if quote is None:
        if provider_error:
            return FeedHealth(symbol, FeedStatus.ERROR, "provider_error", provider_error)
        return FeedHealth(symbol, FeedStatus.MISSING, "no_data", "provider returned no price for this asset")

    freshness = check_quote_freshness(quote, now, policy.stale_after_seconds)
    if freshness == QuoteProblem.FUTURE:
        return FeedHealth(symbol, FeedStatus.ANOMALOUS, "future_timestamp", "price timestamp is in the future", quote.price)
    if freshness == QuoteProblem.STALE:
        return FeedHealth(
            symbol, FeedStatus.STALE, "stale_price",
            f"price older than {policy.stale_after_seconds}s", quote.price,
        )

    if previous_price is not None:
        bps = move_bps(previous_price, quote.price)
        if bps > policy.max_move_bps:
            return FeedHealth(
                symbol, FeedStatus.ANOMALOUS, "abnormal_move",
                f"moved {bps} bps since last check (limit {policy.max_move_bps})", quote.price,
            )

    minimum = policy.min_liquidity_usd.get(symbol)
    if minimum is not None:
        if liquidity_usd is None:
            return FeedHealth(symbol, FeedStatus.ANOMALOUS, "liquidity_unknown",
                              f"liquidity unknown but minimum {minimum} USD is required", quote.price)
        if liquidity_usd < minimum:
            return FeedHealth(symbol, FeedStatus.ANOMALOUS, "low_liquidity",
                              f"liquidity {liquidity_usd} USD below minimum {minimum} USD", quote.price)

    return FeedHealth(symbol, FeedStatus.HEALTHY, "ok", "price is fresh and within limits", quote.price)


def auto_pause_reason(health: FeedHealth) -> str:
    """Value for markets.pause_reason when the system (not an admin) pauses a market."""
    return f"{AUTO_PAUSE_PREFIX}{health.reason}"


def count_consecutive_healthy(statuses_newest_first: Sequence[str]) -> int:
    count = 0
    for status in statuses_newest_first:
        if status != FeedStatus.HEALTHY.value:
            break
        count += 1
    return count


def decide_market_action(
    market_status: str,
    pause_reason: str | None,
    feed_status: FeedStatus,
    consecutive_healthy: int,
    betting_open: bool,
    policy: HealthPolicy,
) -> MarketAction:
    healthy = feed_status == FeedStatus.HEALTHY

    if market_status == "open":
        return MarketAction.NONE if healthy else MarketAction.PAUSE

    if market_status == "paused":
        paused_by_system = bool(pause_reason) and pause_reason.startswith(AUTO_PAUSE_PREFIX)
        if (
            paused_by_system
            and healthy
            and betting_open
            and consecutive_healthy >= policy.required_healthy_checks
        ):
            return MarketAction.REOPEN
        return MarketAction.NONE

    return MarketAction.NONE
