"""Predictions service: place a prediction (demo credits) and read a user's history.

The stake, balance check and ledger movement all happen inside the SQL function
place_prediction() in ONE transaction, so a prediction can never exist without its
reserved stake. This module validates input and adds one safety rule on top: no new
prediction is accepted while the price feed for the asset is unhealthy.
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.services.growth import refresh_vip
from app.services.markets import get_market

DIRECTIONS = ("above", "below")
STATUSES = ("open", "won", "lost", "refunded", "cashed_out")
MAX_PAGE_SIZE = 100

_SELECT = """
select p.id, p.market_id, a.symbol, m.duration_seconds, p.direction, p.stake,
       p.target_price_snapshot as target_price, p.payout_bps_snapshot as payout_bps,
       p.potential_payout, p.status, p.payout_amount, p.created_at, p.settled_at,
       p.closes_at_snapshot as closes_at,
       st.result as market_result, st.settle_price
from predictions p
join markets m on m.id = p.market_id
join assets a on a.id = m.asset_id
left join settlements st on st.market_id = m.id
"""


def estimate_payout(stake: int, payout_bps: int) -> int:
    """Same formula as the database: simulated payout, never less than the stake."""
    return max(stake, (stake * payout_bps) // 10000)


def validate_prediction_input(direction: Any, stake_units: Any, key: Any) -> tuple[str, int, str]:
    direction = str(direction or "").strip().lower()
    if direction not in DIRECTIONS:
        raise AppError("invalid_direction", "Direction must be 'above' or 'below'.", 422)
    if isinstance(stake_units, bool) or not isinstance(stake_units, int) or stake_units <= 0:
        raise AppError("invalid_amount", "Stake must be a positive whole number of base units.", 422)
    if not isinstance(key, str) or not (8 <= len(key) <= 120):
        raise AppError("invalid_key", "Idempotency key must be 8-120 characters.", 422)
    return direction, stake_units, key


def get_prediction(db: Session, user_id: uuid.UUID, prediction_id: uuid.UUID) -> dict:
    row = db.execute(text(_SELECT + " where p.user_id = :u and p.id = :i"),
                     {"u": user_id, "i": prediction_id}).mappings().first()
    if row is None:
        raise NotFound("Prediction not found.", "prediction_not_found")
    return dict(row)


def place_prediction(
    db: Session,
    *,
    user_id: uuid.UUID,
    market_id: uuid.UUID,
    direction: str,
    stake_units: int,
    idempotency_key: str,
    expected_target_price: Any = None,
) -> dict:
    """Place a prediction. Safe to retry with the same key (returns the same prediction).

    expected_target_price: pass what the user saw on screen; if the market's target is
    different the request is refused (terms_mismatch) instead of silently changing it.
    """
    direction, stake_units, key = validate_prediction_input(direction, stake_units, idempotency_key)

    existing = db.execute(
        text("select id from predictions where user_id = :u and idempotency_key = :k"),
        {"u": user_id, "k": key},
    ).scalar_one_or_none()
    if existing is not None:
        return get_prediction(db, user_id, existing)

    market = get_market(db, market_id)            # NotFound for unknown / draft markets
    if expected_target_price is not None:
        try:
            expected = Decimal(str(expected_target_price))
        except InvalidOperation:
            raise AppError("terms_mismatch", "Market terms changed. Please refresh and try again.", 409) from None
        if expected != Decimal(market["target_price"]):
            raise AppError("terms_mismatch", "Market terms changed. Please refresh and try again.", 409)
    if not market["feed_ok"]:
        raise AppError("price_unavailable", "No reliable price is available right now. Try again shortly.", 503)

    new_id = db.execute(
        text("select id from place_prediction(:u, :m, :d, cast(:s as bigint), :k)"),
        {"u": user_id, "m": market_id, "d": direction, "s": stake_units, "k": key},
    ).scalar_one()
    refresh_vip(db, user_id)
    return get_prediction(db, user_id, new_id)


def list_predictions(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    if status is not None and status not in STATUSES:
        raise AppError("invalid_status", "Unknown prediction status.", 422)
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    rows = db.execute(
        text(_SELECT + """ where p.user_id = :u and (cast(:st as text) is null or p.status = :st)
                           order by p.created_at desc, p.id desc limit :lim offset :off"""),
        {"u": user_id, "st": status, "lim": limit, "off": max(0, int(offset))},
    ).mappings().all()
    return [dict(r) for r in rows]
