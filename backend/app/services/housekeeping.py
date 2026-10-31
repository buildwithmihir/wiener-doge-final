"""Jobs the price worker runs every tick, after settlement.

ensure_auto_markets : keeps every active prediction asset supplied with bettable market rounds, so the
                      admin never has to create markets by hand. A "round" is a ladder of 7 target prices
                      around the live price for one timeframe. A new round is made whenever a timeframe has
                      no market left that can still take bets (with a 10 minute margin).
refresh_vip_recent  : wager now counts only SETTLED bets, so VIP tiers are re-checked for users whose bets
                      were just settled.

Needs at least one user with the admin role (markets are created in their name, with the reason
"auto: scheduled round" in the audit log). Settings (application_settings):
  markets.auto_enabled   true / false
  markets.auto_durations [86400, 172800, 604800]   (30d only runs if markets.monthly_enabled is true)
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services.growth import refresh_vip
from app.services.markets import DURATIONS, create_market, ladder_targets, latest_good_price

log = logging.getLogger("wienerdoge.housekeeping")

DEFAULT_AUTO_DURATIONS = [86400, 172800, 604800]
BETTING_MARGIN_MINUTES = 10


def _auto_durations(db: Session) -> list[int]:
    raw = db.execute(text("select value from application_settings where key = 'markets.auto_durations'")).scalar_one_or_none()
    try:
        values = [int(v) for v in (raw if isinstance(raw, list) else DEFAULT_AUTO_DURATIONS)]
    except (TypeError, ValueError):
        values = DEFAULT_AUTO_DURATIONS
    monthly = bool(db.execute(text("select wd_setting_bool('markets.monthly_enabled', false)")).scalar_one())
    return [v for v in values if v in DURATIONS and (v != 2592000 or monthly)]


def _has_bettable_market(db: Session, symbol: str, duration: int) -> bool:
    return db.execute(
        text("""select 1 from markets m join assets a on a.id = m.asset_id
                where a.symbol = :s and m.duration_seconds = :d and m.status in ('open','paused')
                  and m.betting_closes_at > now() + make_interval(mins => :m) limit 1"""),
        {"s": symbol, "d": duration, "m": BETTING_MARGIN_MINUTES},
    ).first() is not None


def ensure_auto_markets(db: Session) -> dict[str, Any]:
    if not db.execute(text("select wd_setting_bool('markets.auto_enabled', true)")).scalar_one():
        return {"created": 0, "off": True}
    actor = db.execute(text("select user_id from user_roles where role = 'admin' order by created_at limit 1")).scalar_one_or_none()
    if actor is None:
        return {"created": 0, "no_admin_user": True}

    durations = _auto_durations(db)
    symbols = [r[0] for r in db.execute(
        text("select symbol from assets where is_prediction_asset and is_active order by symbol")).all()]
    created = 0
    for symbol in symbols:
        try:
            targets = ladder_targets(latest_good_price(db, symbol))
        except AppError:
            continue                                    # no fresh price: no new markets for this asset
        for duration in durations:
            if _has_bettable_market(db, symbol, duration):
                continue
            try:
                with db.begin_nested():
                    for target in targets:
                        create_market(db, actor_id=actor, symbol=symbol, duration_seconds=duration,
                                      target_price=target, reason="auto: scheduled round")
                created += len(targets)
            except Exception:  # noqa: BLE001 - one asset / timeframe must not stop the others
                log.exception("auto market round failed for %s %ss", symbol, duration)
    return {"created": created}


def refresh_vip_recent(db: Session, minutes: int = 15) -> int:
    users = [r[0] for r in db.execute(
        text("""select distinct user_id from predictions
                where status in ('won','lost') and settled_at > now() - make_interval(mins => :m) limit 200"""),
        {"m": minutes}).all()]
    return sum(refresh_vip(db, u) for u in users)