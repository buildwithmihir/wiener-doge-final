"""Markets service: read markets and charts, and admin create / pause / resume.

Market terms (asset, duration, target, times, payout, stake limits) are fixed after
creation by a database trigger. Money logic is NOT here (see ledger.py and the SQL
functions). Admin changes are written to market_config_versions (via wd.actor) and
to the audit log.

Settlement rule (shown to users): price >= target -> ABOVE wins, otherwise BELOW.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.providers.health import AUTO_PAUSE_PREFIX

DURATIONS = (86400, 172800, 604800, 2592000)   # 24h, 48h, 7d, 30d (same as the DB check)
CHART_RANGES = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
MAX_CHART_POINTS = 240
DEFAULT_BETTING_CUTOFF_SECONDS = 3600          # betting stops 1h before the market closes
MAX_PAGE_SIZE = 100
STATUSES = ("draft", "open", "paused", "closed", "settling", "settled", "voided")

_SELECT = """
select m.id, a.symbol, a.name as asset_name, m.duration_seconds, m.target_price,
       m.opens_at, m.betting_closes_at, m.closes_at, m.status, m.payout_bps,
       m.min_stake, m.max_stake, m.terms_version, m.pause_reason,
       case when m.status = 'open' and now() >= m.betting_closes_at then 'closed'
            else m.status end as effective_status,
       greatest(0, extract(epoch from (m.betting_closes_at - now())))::bigint as betting_closes_in_seconds,
       greatest(0, extract(epoch from (m.closes_at - now())))::bigint as closes_in_seconds,
       s.price as last_price, s.source as price_source, s.fetched_at as price_updated_at,
       (s.fetched_at is not null) as has_price,
       (s.fetched_at is not null and not s.is_stale and not s.is_anomalous
          and now() - s.fetched_at <= make_interval(secs => :stale)) as feed_ok,
       st.result as settlement_result, st.settle_price, st.created_at as settled_at
from markets m
join assets a on a.id = m.asset_id
left join lateral (
    select price, source, fetched_at, is_stale, is_anomalous
    from market_price_snapshots where asset_id = m.asset_id
    order by fetched_at desc limit 1
) s on true
left join settlements st on st.market_id = m.id
"""


def _stale_seconds(db: Session) -> int:
    return int(db.execute(text("select wd_setting_int('price.stale_after_seconds', 120)")).scalar_one())


# ---- schedule / validation (pure) -----------------------------------------------
@dataclass(frozen=True)
class Schedule:
    opens_at: datetime
    betting_closes_at: datetime
    closes_at: datetime


def parse_target_price(value: Any) -> Decimal:
    """Positive price with at most 12 decimals (matches numeric(38,12))."""
    if value is None or isinstance(value, bool):
        raise AppError("invalid_target_price", "Enter a valid target price.", 422)
    try:
        price = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except InvalidOperation:
        raise AppError("invalid_target_price", "Enter a valid target price.", 422) from None
    if not price.is_finite() or price <= 0 or price >= Decimal(10) ** 20:
        raise AppError("invalid_target_price", "Target price must be greater than zero.", 422)
    if price != price.quantize(Decimal(1).scaleb(-12)):
        raise AppError("invalid_target_price", "Use at most 12 decimal places.", 422)
    return price


def compute_schedule(opens_at: datetime, duration_seconds: int, cutoff_seconds: int) -> Schedule:
    if duration_seconds not in DURATIONS:
        raise AppError("invalid_duration", "Duration must be 24h, 48h, 7d or 30d.", 422)
    if opens_at.tzinfo is None:
        raise AppError("invalid_time", "Times must include a timezone.", 422)
    if not (0 <= cutoff_seconds < duration_seconds):
        raise AppError("invalid_time", "Betting cutoff must be shorter than the market.", 422)
    closes_at = opens_at + timedelta(seconds=duration_seconds)
    return Schedule(opens_at, closes_at - timedelta(seconds=cutoff_seconds), closes_at)


def validate_pause_reason(reason: str | None) -> str:
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    if reason.lower().startswith(AUTO_PAUSE_PREFIX):
        raise AppError("invalid_reason", "That reason prefix is reserved for the system.", 422)
    return reason


# ---- reads ------------------------------------------------------------------------
def list_markets(
    db: Session,
    *,
    symbol: str | None = None,
    duration_seconds: int | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_drafts: bool = False,
) -> list[dict]:
    if status is not None and status not in STATUSES:
        raise AppError("invalid_status", "Unknown market status.", 422)
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))
    rows = db.execute(
        text(
            _SELECT
            + """ where (cast(:sym as text) is null or a.symbol = :sym)
                    and (cast(:dur as int) is null or m.duration_seconds = :dur)
                    and (cast(:st as text) is null or m.status = :st)
                    and (:drafts or m.status <> 'draft')
                    and a.is_prediction_asset and a.is_active
                  order by m.closes_at asc, m.target_price asc, m.id asc
                  limit :lim offset :off"""
        ),
        {"sym": symbol.upper() if symbol else None, "dur": duration_seconds, "st": status,
         "drafts": include_drafts, "lim": limit, "off": offset, "stale": _stale_seconds(db)},
    ).mappings().all()
    return [dict(r) for r in rows]


def get_market(db: Session, market_id: uuid.UUID, include_drafts: bool = False) -> dict:
    row = db.execute(
        text(_SELECT + " where m.id = :id and (:drafts or m.status <> 'draft')"),
        {"id": market_id, "drafts": include_drafts, "stale": _stale_seconds(db)},
    ).mappings().first()
    if row is None:
        raise NotFound("Market not found.", "market_not_found")
    return dict(row)


def price_chart(db: Session, symbol: str, range_key: str) -> dict:
    """Real provider snapshots only (stale and anomalous ones are left out)."""
    if range_key not in CHART_RANGES:
        raise AppError("invalid_range", f"Range must be one of: {', '.join(CHART_RANGES)}.", 422)
    rows = db.execute(
        text(
            """select s.fetched_at, s.price, s.source
               from market_price_snapshots s join assets a on a.id = s.asset_id
               where a.symbol = :sym and s.fetched_at >= now() - make_interval(secs => :secs)
                 and not s.is_stale and not s.is_anomalous
               order by s.fetched_at asc"""
        ),
        {"sym": symbol.upper(), "secs": CHART_RANGES[range_key]},
    ).all()
    points = list(rows)
    if len(points) > MAX_CHART_POINTS:
        step = math.ceil(len(points) / MAX_CHART_POINTS)
        sampled = points[::step]
        if sampled[-1] is not points[-1]:
            sampled.append(points[-1])
        points = sampled
    change = None
    if len(rows) >= 2 and rows[0].price:
        first, last = Decimal(rows[0].price), Decimal(rows[-1].price)
        change = {"abs": str(last - first),
                  "pct": str(((last - first) / first * 100).quantize(Decimal("0.001")))}
    return {
        "symbol": symbol.upper(),
        "range": range_key,
        "points": [{"t": p.fetched_at.isoformat(), "price": str(p.price)} for p in points],
        "change": change,
        "source": rows[-1].source if rows else None,
    }


# ---- admin writes -----------------------------------------------------------------
def _mark_actor(db: Session, actor_id: uuid.UUID, reason: str) -> None:
    """Tell the version trigger who changed the market and why (this transaction only)."""
    db.execute(text("select set_config('wd.actor', :a, true), set_config('wd.reason', :r, true)"),
               {"a": str(actor_id), "r": reason})


def create_market(
    db: Session,
    *,
    actor_id: uuid.UUID,
    symbol: str,
    duration_seconds: int,
    target_price: Any,
    reason: str,
    opens_at: datetime | None = None,
    publish: bool = True,
    payout_bps: int | None = None,
    min_stake: int | None = None,
    max_stake: int | None = None,
) -> dict:
    """Create a market (open for predictions when publish=True, otherwise a draft)."""
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    price = parse_target_price(target_price)
    cutoff = int(db.execute(text("select wd_setting_int('market.betting_cutoff_seconds', :d)"),
                            {"d": DEFAULT_BETTING_CUTOFF_SECONDS}).scalar_one())
    # default to the DATABASE clock (not this server's), so opens_at can never be 'in the future' for the DB
    start = opens_at or db.execute(text("select now()")).scalar_one()
    schedule = compute_schedule(start, duration_seconds, cutoff)

    asset_id = db.execute(
        text("select id from assets where symbol = :s and is_prediction_asset and is_active"),
        {"s": symbol.upper()},
    ).scalar_one_or_none()
    if asset_id is None:
        raise AppError("asset_not_supported", "This asset is not available for predictions.", 422)

    extra = {k: v for k, v in (("payout_bps", payout_bps), ("min_stake", min_stake), ("max_stake", max_stake))
             if v is not None}
    for key, value in extra.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError("invalid_value", f"{key} must be a whole number.", 422)
    cols = ", ".join(["asset_id", "duration_seconds", "target_price", "opens_at", "betting_closes_at",
                      "closes_at", "status", "created_by", *extra])
    vals = ", ".join([":asset", ":dur", ":price", ":o", ":b", ":c", ":status", ":actor",
                      *[f":{k}" for k in extra]])

    _mark_actor(db, actor_id, reason)
    market_id = db.execute(
        text(f"insert into markets({cols}) values ({vals}) returning id"),
        {"asset": asset_id, "dur": duration_seconds, "price": price, "o": schedule.opens_at,
         "b": schedule.betting_closes_at, "c": schedule.closes_at,
         "status": "open" if publish else "draft", "actor": actor_id, **extra},
    ).scalar_one()
    created = get_market(db, market_id, include_drafts=True)
    db.execute(
        text("select wd_audit(:a, 'admin', 'market.create', 'market', :id, null, cast(:after as jsonb), :r)"),
        {"a": actor_id, "id": str(market_id), "after": json.dumps(_audit_view(created)), "r": reason},
    )
    return created


def pause_market(db: Session, *, actor_id: uuid.UUID, market_id: uuid.UUID, reason: str) -> dict:
    """Admin pause. Such a pause is never reopened automatically by the price worker."""
    reason = validate_pause_reason(reason)
    before = get_market(db, market_id, include_drafts=True)
    if before["status"] != "open":
        raise AppError("illegal_market_transition", "Only an open market can be paused.", 409)
    _mark_actor(db, actor_id, reason)
    db.execute(text("update markets set status = 'paused', pause_reason = :r where id = :id"),
               {"r": reason, "id": market_id})
    after = get_market(db, market_id, include_drafts=True)
    _audit_change(db, actor_id, "market.pause", market_id, before, after, reason)
    return after


def resume_market(db: Session, *, actor_id: uuid.UUID, market_id: uuid.UUID, reason: str) -> dict:
    """Admin resume. Works for admin pauses and for automatic (feed) pauses."""
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    before = get_market(db, market_id, include_drafts=True)
    if before["status"] != "paused":
        raise AppError("illegal_market_transition", "Only a paused market can be resumed.", 409)
    _mark_actor(db, actor_id, reason)
    # the DB refuses this once the betting window has ended (cannot_open_after_betting_closes)
    db.execute(text("update markets set status = 'open', pause_reason = null where id = :id"),
               {"id": market_id})
    after = get_market(db, market_id, include_drafts=True)
    _audit_change(db, actor_id, "market.resume", market_id, before, after, reason)
    return after


def _audit_view(market: dict) -> dict:
    keys = ("symbol", "duration_seconds", "target_price", "opens_at", "betting_closes_at",
            "closes_at", "status", "payout_bps", "min_stake", "max_stake", "pause_reason")
    return {k: (v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, Decimal) else v)
            for k, v in ((k, market.get(k)) for k in keys)}


def _audit_change(db: Session, actor_id, action: str, market_id, before: dict, after: dict, reason: str) -> None:
    db.execute(
        text("select wd_audit(:a, 'admin', :act, 'market', :id, cast(:b as jsonb), cast(:af as jsonb), :r)"),
        {"a": actor_id, "act": action, "id": str(market_id), "r": reason,
         "b": json.dumps(_audit_view(before)), "af": json.dumps(_audit_view(after))},
    )
