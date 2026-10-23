"""Deterministic close + settlement of markets.

For every market whose close time has passed and that has no settlement yet:
  1. markets past their betting window are moved to 'closed' (close_due_markets)
  2. take the EARLIEST fresh, non-anomalous price snapshot at/after closes_at and within
     settlement.max_snapshot_delay_seconds, then settle_market() (price >= target => ABOVE)
  3. no such snapshot yet -> stay pending (a result is never invented)
  4. still none after settlement.void_after_seconds -> void_market(): every stake refunded
Everything is idempotent, so retries and parallel workers are safe.

The caller owns the transaction: each market runs in its own savepoint, so one bad market
cannot block the others, and the caller commits once at the end.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError

log = logging.getLogger("wienerdoge.settlement")

DEFAULT_MAX_DELAY = 300
DEFAULT_VOID_AFTER = 3600


def settle_due_markets(db: Session) -> dict[str, int]:
    out = {"settled": 0, "voided": 0, "pending": 0, "errors": 0}
    db.execute(text("select close_due_markets()"))

    window = int(db.execute(text("select wd_setting_int('settlement.max_snapshot_delay_seconds', :d)"),
                            {"d": DEFAULT_MAX_DELAY}).scalar_one())
    void_after = int(db.execute(text("select wd_setting_int('settlement.void_after_seconds', :d)"),
                                {"d": DEFAULT_VOID_AFTER}).scalar_one())

    due = db.execute(
        text(
            """select m.id, m.asset_id, m.closes_at,
                      now() > m.closes_at + make_interval(secs => :void_after) as overdue
               from markets m
               where m.status in ('open','paused','closed','settling') and now() >= m.closes_at
                 and not exists (select 1 from settlements s where s.market_id = m.id)
               order by m.closes_at"""
        ),
        {"void_after": void_after},
    ).mappings().all()

    for m in due:
        try:
            with db.begin_nested():
                snapshot_id = find_settlement_snapshot(db, m["asset_id"], m["closes_at"], window)
                if snapshot_id is not None:
                    db.execute(text("select settle_market(:m, :s, null)"), {"m": m["id"], "s": snapshot_id})
                    out["settled"] += 1
                elif m["overdue"]:
                    db.execute(
                        text("select void_market(:m, 'no reliable price within the settlement window', null)"),
                        {"m": m["id"]},
                    )
                    out["voided"] += 1
                else:
                    out["pending"] += 1
        except Exception:  # noqa: BLE001  (one market failing must not stop the rest)
            out["errors"] += 1
            log.exception("settlement failed for market %s", m["id"])
    return out


def find_settlement_snapshot(db: Session, asset_id: Any, closes_at: Any, window_seconds: int) -> int | None:
    return db.execute(
        text(
            """select id from market_price_snapshots
               where asset_id = :a and fetched_at >= :c
                 and fetched_at <= :c + make_interval(secs => :w)
                 and not is_stale and not is_anomalous
               order by fetched_at asc limit 1"""
        ),
        {"a": asset_id, "c": closes_at, "w": window_seconds},
    ).scalar_one_or_none()


def void_market_admin(db: Session, *, actor_id: uuid.UUID, market_id: uuid.UUID, reason: str) -> dict:
    """Admin void: refunds every open prediction. Reason is mandatory and audited."""
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    row = db.execute(text("select result, predictions_settled from void_market(:m, :r, :a)"),
                     {"m": market_id, "r": reason, "a": actor_id}).mappings().one()
    return dict(row)
