"""Cashout of live predictions.

The value is computed on the SERVER from the live price and the time left (odds.py), so a bet that is
winning cashes out for more and a bet that is losing cashes out for less. The browser only shows the
quote and sends back the amount it showed; if the value moved against the user by more than 2% in the
meantime the request is refused (cashout_changed) so nobody cashes out at a surprise price.

The money movement itself is the SQL function cashout_prediction() (ledger, idempotent).
A cashed-out bet NEVER counts as wager: wager only counts won/lost (settled) bets.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services.markets import latest_good_price
from app.services.odds import cashout_units, win_probability
from app.services.predictions import get_prediction, list_predictions

MAX_QUOTES = 50
TOLERANCE = Decimal("0.98")

REASONS = {
    "feed": "Live price is unavailable right now.",
    "too_late": "Cashout is closed shortly before the market ends.",
    "closed": "This bet can no longer be cashed out.",
}


def _cutoff(db: Session) -> int:
    return int(db.execute(text("select wd_setting_int('cashout.cutoff_seconds', 300)")).scalar_one())


def quote_one(p: dict[str, Any], spot: Decimal | None, now: datetime, cutoff: int) -> dict[str, Any]:
    seconds_left = max(0, int((p["closes_at"] - now).total_seconds()))
    base: dict[str, Any] = {"prediction_id": p["id"], "available": False, "reason": None, "amount": None,
                            "current_price": spot, "winning": None, "seconds_left": seconds_left}
    if p["status"] != "open":
        return {**base, "reason": "closed"}
    if spot is None:
        return {**base, "reason": "feed"}
    target = Decimal(p["target_price"])
    base["winning"] = (spot >= target) == (p["direction"] == "above")
    if seconds_left <= cutoff:
        return {**base, "reason": "too_late"}
    prob = win_probability(p["symbol"], spot, target, p["direction"], seconds_left)
    return {**base, "available": True, "amount": cashout_units(int(p["potential_payout"]), prob)}


def open_quotes(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    now = db.execute(text("select now()")).scalar_one()
    cutoff = _cutoff(db)
    spots: dict[str, Decimal | None] = {}
    out = []
    for p in list_predictions(db, user_id, status="open", limit=MAX_QUOTES):
        sym = p["symbol"]
        if sym not in spots:
            try:
                spots[sym] = latest_good_price(db, sym)
            except AppError:
                spots[sym] = None
        out.append(quote_one(p, spots[sym], now, cutoff))
    return out


def cashout(db: Session, *, user_id: uuid.UUID, prediction_id: uuid.UUID, expected_units: int | None) -> dict:
    p = get_prediction(db, user_id, prediction_id)
    if p["status"] == "cashed_out":
        return p                                   # retry of a request that already worked
    if p["status"] != "open":
        raise AppError("prediction_already_final", "This prediction is already settled.", 409)

    now = db.execute(text("select now()")).scalar_one()
    try:
        spot: Decimal | None = latest_good_price(db, p["symbol"])
    except AppError:
        spot = None
    q = quote_one(p, spot, now, _cutoff(db))
    if not q["available"] or q["amount"] is None:
        raise AppError("cashout_unavailable", REASONS.get(q["reason"] or "closed", REASONS["closed"]), 409)

    if expected_units is not None and Decimal(q["amount"]) < Decimal(expected_units) * TOLERANCE:
        raise AppError("cashout_changed", "The cashout value changed. Check the new amount and try again.", 409)

    new_id = db.execute(
        text("select id from cashout_prediction(:u, :p, cast(:a as bigint))"),
        {"u": user_id, "p": prediction_id, "a": q["amount"]},
    ).scalar_one()
    return get_prediction(db, user_id, new_id)