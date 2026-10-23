"""The price worker: ONE function, tick(), run about once a minute by an external scheduler.

Each tick:
  1. takes a database lock (two overlapping ticks never run at once)
  2. decides which assets need a fresh price (adaptive polling, to stay inside the free
     CoinGecko quota: slow when nothing is about to close, fast around close time)
  3. fetches prices, stores real snapshots, records feed health
  4. pauses open markets whose feed is unhealthy; reopens ones the SYSTEM paused after
     enough consecutive healthy checks (admin pauses are never reopened here)
  5. closes and settles due markets (settlement.settle_due_markets)

It never invents a price: no quote means no snapshot and the market pauses.
The caller owns the transaction (run_tick() commits; tests roll back).

Run by hand:   python -m app.services.worker
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.base import AssetRef, PriceQuote
from app.providers.health import (
    FeedHealth,
    HealthPolicy,
    MarketAction,
    auto_pause_reason,
    count_consecutive_healthy,
    decide_market_action,
    evaluate_feed,
)
from app.providers.registry import ProviderRegistry, build_default_registry, fetch_all, group_refs_by_provider
from app.services.notifications import Sender, run_notifications
from app.services.settlement import settle_due_markets

log = logging.getLogger("wienerdoge.worker")

TICK_LOCK_ID = 727_001
DEFAULT_POLL_SECONDS = 600           # nothing closing soon
DEFAULT_NEAR_CLOSE_POLL_SECONDS = 60
DEFAULT_NEAR_CLOSE_WINDOW_SECONDS = 900
POLL_TOLERANCE_SECONDS = 5           # scheduler jitter
HEALTH_LOOKBACK = 10


def needs_poll(seconds_since_last_check: float | None, near_close: bool, normal_interval: int, near_interval: int) -> bool:
    """True when an asset is due for a fresh price."""
    if seconds_since_last_check is None:
        return True
    interval = near_interval if near_close else normal_interval
    return seconds_since_last_check >= interval - POLL_TOLERANCE_SECONDS


@dataclass
class _Asset:
    id: Any
    symbol: str
    provider_key: str | None
    provider_ref: str | None
    near_close: bool
    age: float | None


def load_settings(db: Session) -> dict[str, Any]:
    return {k: v for k, v in db.execute(text("select key, value from application_settings")).all()}


def _int_setting(values: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(values.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def tick(db: Session, registry: ProviderRegistry, now: datetime | None = None,
         notifier: Sender | None = None) -> dict[str, Any]:
    """One worker pass. `now` is for tests; normally the database clock is used."""
    locked = db.execute(text("select pg_try_advisory_xact_lock(:id)"), {"id": TICK_LOCK_ID}).scalar_one()
    if not locked:
        return {"skipped": "another tick is running"}
    now = now or db.execute(text("select now()")).scalar_one()

    values = load_settings(db)
    policy = HealthPolicy.from_settings(values)
    normal = _int_setting(values, "price.poll_seconds", DEFAULT_POLL_SECONDS)
    near = _int_setting(values, "price.near_close_poll_seconds", DEFAULT_NEAR_CLOSE_POLL_SECONDS)
    window = _int_setting(values, "price.near_close_window_seconds", DEFAULT_NEAR_CLOSE_WINDOW_SECONDS)

    rows = db.execute(
        text(
            """select a.id, a.symbol, a.provider_key, a.provider_ref,
                      exists (select 1 from markets m
                              where m.asset_id = a.id and m.status in ('open','paused','closed','settling')
                                and m.closes_at <= cast(:now as timestamptz) + make_interval(secs => :w)) as near_close,
                      (select extract(epoch from (cast(:now as timestamptz) - max(h.checked_at)))
                       from provider_health_history h where h.asset_id = a.id) as age
               from assets a where a.is_prediction_asset and a.is_active order by a.symbol"""
        ),
        {"now": now, "w": window},
    ).mappings().all()
    assets = [_Asset(r["id"], r["symbol"], r["provider_key"], r["provider_ref"], bool(r["near_close"]),
                     float(r["age"]) if r["age"] is not None else None) for r in rows]

    due = [a for a in assets if needs_poll(a.age, a.near_close, normal, near)]
    summary: dict[str, Any] = {"polled": [a.symbol for a in due], "snapshots": 0, "paused": 0,
                               "reopened": 0, "feed": {}, "provider_errors": {}}

    if due:
        # one provider call covers all of that provider's assets, so fetch the whole group
        due_providers = {a.provider_key for a in due if a.provider_key}
        grouped = group_refs_by_provider(
            (a.symbol, a.provider_key, a.provider_ref) for a in assets if a.provider_key in due_providers
        )
        fetched = fetch_all(registry, grouped)
        summary["provider_errors"] = fetched.errors
        quotes: dict[str, PriceQuote] = {q.symbol.upper(): q for q in fetched.quotes}

        for asset in due:
            quote = quotes.get(asset.symbol.upper())
            health = _record_feed(db, asset, quote, fetched.errors.get(asset.provider_key or ""), now, policy)
            summary["feed"][asset.symbol] = health.status.value
            if health.store_snapshot and quote is not None:
                summary["snapshots"] += 1
            paused, reopened = _apply_market_actions(db, asset, health, now, policy)
            summary["paused"] += paused
            summary["reopened"] += reopened

    summary["settlement"] = settle_due_markets(db)
    try:
        with db.begin_nested():
            summary["referrals_rewarded"] = int(db.execute(text("select process_referral_rewards()")).scalar_one())
    except Exception:   # noqa: BLE001 - referral payouts must never break settlement
        log.exception("referral reward processing failed")
        summary["referrals_rewarded"] = 0
    summary["notifications"] = run_notifications(db, notifier)   # last: never delays or breaks settlement
    return summary


def _record_feed(db: Session, asset: _Asset, quote: PriceQuote | None, provider_error: str | None,
                 now: datetime, policy: HealthPolicy) -> FeedHealth:
    previous = db.execute(
        text("select price from market_price_snapshots where asset_id = :a order by fetched_at desc limit 1"),
        {"a": asset.id},
    ).scalar_one_or_none()
    health = evaluate_feed(asset.symbol, quote, now, policy, previous_price=previous,
                           liquidity_usd=None, provider_error=provider_error)

    if health.store_snapshot and quote is not None:
        db.execute(
            text(
                """insert into market_price_snapshots(asset_id, price, source, fetched_at, is_stale, is_anomalous, raw)
                   values (:a, :p, :s, :f, :stale, :anom, cast(:raw as jsonb))
                   on conflict (asset_id, source, fetched_at) do nothing"""
            ),
            {"a": asset.id, "p": quote.price, "s": quote.source, "f": quote.fetched_at,
             "stale": health.is_stale, "anom": health.is_anomalous,
             "raw": json.dumps(quote.raw, default=str) if quote.raw is not None else None},
        )
    db.execute(
        text(
            """insert into provider_health_history(provider_key, asset_id, status, last_price_at, detail, checked_at)
               values (:pk, :a, :st, :lp, :d, :now)"""
        ),
        {"pk": asset.provider_key or "none", "a": asset.id, "st": health.status.value,
         "lp": (quote.source_updated_at or quote.fetched_at) if quote else None,
         "d": f"{health.reason}: {health.detail}"[:300], "now": now},
    )
    return health


def _apply_market_actions(db: Session, asset: _Asset, health: FeedHealth, now: datetime,
                          policy: HealthPolicy) -> tuple[int, int]:
    recent = db.execute(
        text("select status from provider_health_history where asset_id = :a order by checked_at desc, id desc limit :n"),
        {"a": asset.id, "n": HEALTH_LOOKBACK},
    ).scalars().all()
    healthy_run = count_consecutive_healthy(list(recent))

    markets = db.execute(
        text(
            """select id, status, pause_reason, betting_closes_at > cast(:now as timestamptz) as betting_open
               from markets where asset_id = :a and status in ('open','paused')
                 and (status = 'paused' or betting_closes_at > cast(:now as timestamptz))"""
        ),
        {"a": asset.id, "now": now},
    ).mappings().all()

    paused = reopened = 0
    for m in markets:
        action = decide_market_action(m["status"], m["pause_reason"], health.status, healthy_run,
                                      bool(m["betting_open"]), policy)
        if action == MarketAction.NONE:
            continue
        try:
            with db.begin_nested():
                if action == MarketAction.PAUSE:
                    reason = auto_pause_reason(health)
                    changed = db.execute(
                        text("update markets set status = 'paused', pause_reason = :r where id = :id and status = 'open'"),
                        {"r": reason, "id": m["id"]},
                    ).rowcount
                    event, detail = "market.auto_pause", {"reason": reason, "feed": health.detail}
                else:
                    changed = db.execute(
                        text("update markets set status = 'open', pause_reason = null "
                             "where id = :id and status = 'paused' and pause_reason like 'auto:%'"),
                        {"id": m["id"]},
                    ).rowcount
                    event, detail = "market.auto_reopen", {"healthy_checks": healthy_run}
                if changed:
                    db.execute(
                        text("select wd_audit(null, 'system', :ev, 'market', :id, null, cast(:d as jsonb), null)"),
                        {"ev": event, "id": str(m["id"]), "d": json.dumps(detail)},
                    )
                    if action == MarketAction.PAUSE:
                        paused += 1
                    else:
                        reopened += 1
        except Exception:  # noqa: BLE001 (one market must not stop the others)
            log.exception("could not apply %s to market %s", action, m["id"])
    return paused, reopened


def run_tick(registry: ProviderRegistry | None = None, notifier: Sender | None = None) -> dict[str, Any]:
    """Open a transaction, run one tick, commit. Used by the scheduler endpoint / CLI."""
    from app.database import session_scope

    own = registry is None
    registry = registry or build_default_registry()
    try:
        with session_scope() as db:
            return tick(db, registry, notifier=notifier)
    finally:
        if own:
            registry.close_all()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.core.logging_safety import quiet_http_loggers

    quiet_http_loggers()
    print(json.dumps(run_tick(), indent=2, default=str))
