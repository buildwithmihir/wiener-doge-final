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
from app.services.odds import odds_bps   # top imports
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.providers.health import AUTO_PAUSE_PREFIX
BETTING_WINDOW_SECONDS = {86400: 2 * 3600, 172800: 3 * 3600, 604800: 6 * 3600, 2592000: 12 * 3600}
DURATIONS = (86400, 172800, 604800, 2592000)   # 24h, 48h, 7d, 30d (same as the DB check)
CHART_RANGES = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
MAX_CHART_POINTS = 240
DEFAULT_BETTING_CUTOFF_SECONDS = 3600          # betting stops 1h before the market closes
MAX_PAGE_SIZE = 100
# Strike ladder: offsets from the current price in basis points (100 bps = 1%).
LADDER_STEPS_BPS = (-1000, -500, -200, 0, 200, 500, 1000)
# Default per-timeframe odds (demo values, editable per request). 18000 = 1.80x.
DEFAULT_PAYOUT_BPS = {86400: 18000, 172800: 18000, 604800: 18500, 2592000: 19000}
STATUSES = ("draft", "open", "paused", "closed", "settling", "settled", "voided")

_SELECT = """
select m.id, a.symbol, a.name as asset_name, m.duration_seconds, m.target_price,
       m.opens_at, m.betting_closes_at, m.closes_at, m.status, m.payout_bps,
              coalesce(m.payout_above_bps, m.payout_bps) as payout_above_bps,
       coalesce(m.payout_below_bps, m.payout_bps) as payout_below_bps,
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


def round_sig(value: Decimal, digits: int = 5) -> Decimal:
    """Round to `digits` significant digits (keeps tiny prices like 0.00000123 readable)."""
    value = Decimal(value)
    if value <= 0:
        raise AppError("invalid_target_price", "Price must be greater than zero.", 422)
    exp = value.adjusted() - (digits - 1)
    return value.quantize(Decimal(1).scaleb(exp)) if exp < 0 else value.quantize(Decimal(1))


def ladder_targets(base: Decimal, steps_bps: tuple[int, ...] = LADDER_STEPS_BPS) -> list[Decimal]:
    """Distinct, ascending strike prices around `base`."""
    out = {round_sig(Decimal(base) * (Decimal(10000 + s) / Decimal(10000))) for s in steps_bps}
    return sorted(t for t in out if t > 0)


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
    payout_above_bps: int | None = None, payout_below_bps: int | None = None,
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
    window = BETTING_WINDOW_SECONDS.get(duration_seconds, 7200)
    schedule = Schedule(schedule.opens_at, schedule.opens_at + timedelta(seconds=window), schedule.closes_at)

    asset_id = db.execute(
        text("select id from assets where symbol = :s and is_prediction_asset and is_active"),
        {"s": symbol.upper()},
    ).scalar_one_or_none()
    if asset_id is None:
        raise AppError("asset_not_supported", "This asset is not available for predictions.", 422)


    if payout_above_bps is None and payout_below_bps is None:
        if payout_bps is not None:
            payout_above_bps = payout_below_bps = payout_bps
        else:
            try:   # auto odds from the live price
                payout_above_bps, payout_below_bps = odds_bps(symbol, latest_good_price(db, symbol), price, duration_seconds)
            except AppError:
                payout_above_bps = payout_below_bps = 18000
    payout_bps = payout_above_bps
    extra = {k: v for k, v in (("payout_bps", payout_bps), ("payout_above_bps", payout_above_bps),
                               ("payout_below_bps", payout_below_bps),
                               ("min_stake", min_stake), ("max_stake", max_stake)) if v is not None}
     
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


# ---- price ladder (many strikes x timeframes in one go) ------------------------------
def latest_good_price(db: Session, symbol: str) -> Decimal:
    row = db.execute(
        text("""select s.price, s.is_stale, s.is_anomalous,
                       (now() - s.fetched_at <= make_interval(secs => :stale)) as fresh
                from market_price_snapshots s join assets a on a.id = s.asset_id
                where a.symbol = :sym order by s.fetched_at desc limit 1"""),
        {"sym": symbol.upper(), "stale": _stale_seconds(db)},
    ).first()
    if row is None or row.is_stale or row.is_anomalous or not row.fresh:
        raise AppError("price_unavailable", "No fresh price for this asset right now. Try again shortly.", 503)
    return Decimal(row.price)


def _live_market_exists(db: Session, symbol: str, duration_seconds: int, target: Decimal) -> bool:
    return db.execute(
        text("""select 1 from markets m join assets a on a.id = m.asset_id
                where a.symbol = :s and m.duration_seconds = :d and m.target_price = :t
                  and m.status in ('open','paused') and m.closes_at > now() limit 1"""),
        {"s": symbol.upper(), "d": duration_seconds, "t": target},
    ).first() is not None


def create_ladder(
    db: Session, *, actor_id: uuid.UUID, symbol: str,
    durations: list[tuple[int, int | None]], reason: str,
) -> dict:
    """Create one market per (strike, timeframe) around the current price.

    `durations` = [(duration_seconds, payout_bps or None for the default)].
    Existing live markets with the same terms are skipped, not duplicated.
    """
    if not durations:
        raise AppError("invalid_duration", "Pick at least one timeframe.", 422)
    base = latest_good_price(db, symbol)
    targets = ladder_targets(base)
    created: list[dict] = []
    skipped = 0
    for duration, bps in durations:
        for target in targets:
            if _live_market_exists(db, symbol, duration, target):
                skipped += 1
                continue
            created.append(create_market(
                db, actor_id=actor_id, symbol=symbol, duration_seconds=duration,
                target_price=target, reason=reason,
                payout_bps=None,          # auto odds from distance to current price (odds.py)
            ))
    return {"base_price": base, "created": created, "skipped": skipped}

def list_assets(db: Session) -> list[dict]:
    rows = db.execute(
        text("""select a.symbol, a.name, s.price as last_price, p.price as old_price,
                       (select count(*) from markets m where m.asset_id = a.id
                          and m.status in ('open','paused') and m.betting_closes_at > now()) as open_markets
                from assets a
                left join lateral (select price from market_price_snapshots
                                   where asset_id = a.id and not is_stale and not is_anomalous
                                   order by fetched_at desc limit 1) s on true
                left join lateral (select price from market_price_snapshots
                                   where asset_id = a.id and not is_stale and not is_anomalous
                                     and fetched_at <= now() - interval '24 hours'
                                   order by fetched_at desc limit 1) p on true
                where a.is_prediction_asset and a.is_active order by a.symbol""")
    ).mappings().all()
    out = []
    for r in rows:
        change = None
        if r["last_price"] is not None and r["old_price"]:
            change = str(((Decimal(r["last_price"]) - Decimal(r["old_price"])) / Decimal(r["old_price"]) * 100).quantize(Decimal("0.01")))
        out.append({"symbol": r["symbol"], "name": r["name"], "last_price": r["last_price"],
                    "change_pct": change, "open_markets": int(r["open_markets"])})
    return out
