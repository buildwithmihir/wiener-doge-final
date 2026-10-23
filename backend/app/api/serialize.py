"""Response helpers. Money goes out as {"units": "<base units as text>", "demo": "<display>"}
(text, so a JavaScript client can never lose precision); prices go out as text."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.services.ledger import Wallet, WalletEvent, format_demo


def money(units: int) -> dict[str, str]:
    return {"units": str(int(units)), "demo": format_demo(int(units))}


def price(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text_value = format(Decimal(value), "f")
    return text_value.rstrip("0").rstrip(".") if "." in text_value else text_value


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def wallet_out(w: Wallet) -> dict[str, Any]:
    return {"available": money(w.available), "reserved": money(w.reserved), "total": money(w.total)}


def event_out(e: WalletEvent) -> dict[str, Any]:
    return {
        "id": str(e.tx_id), "kind": e.kind, "title": e.title, "created_at": iso(e.created_at),
        "available_change": money(e.available_delta), "reserved_change": money(e.reserved_delta),
        "net_change": money(e.net), "ref_type": e.ref_type,
        "ref_id": str(e.ref_id) if e.ref_id else None, "cursor": e.cursor,
    }


def market_out(m: dict[str, Any]) -> dict[str, Any]:
    reason = m.get("pause_reason") or ""
    return {
        "id": str(m["id"]), "symbol": m["symbol"], "asset_name": m["asset_name"],
        "duration_seconds": m["duration_seconds"], "target_price": price(m["target_price"]),
        "opens_at": iso(m["opens_at"]), "betting_closes_at": iso(m["betting_closes_at"]),
        "closes_at": iso(m["closes_at"]), "status": m["effective_status"],
        "payout_multiplier": f"{m['payout_bps'] / 10000:.2f}",
        "min_stake": money(m["min_stake"]), "max_stake": money(m["max_stake"]),
        "betting_closes_in_seconds": int(m["betting_closes_in_seconds"]),
        "closes_in_seconds": int(m["closes_in_seconds"]),
        "paused_by_feed": reason.startswith("auto:"),
        "pause_reason": None if reason.startswith("auto:") else (m.get("pause_reason") or None),
        "last_price": price(m["last_price"]), "price_source": m["price_source"],
        "price_updated_at": iso(m["price_updated_at"]), "feed_ok": bool(m["feed_ok"]),
        "result": m["settlement_result"], "settle_price": price(m["settle_price"]),
        "settled_at": iso(m["settled_at"]),
        "rule": "Price at close >= target: ABOVE wins. Below target: BELOW wins. Demo credits only.",
    }


def prediction_out(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(p["id"]), "market_id": str(p["market_id"]), "symbol": p["symbol"],
        "duration_seconds": p["duration_seconds"], "direction": p["direction"],
        "stake": money(p["stake"]), "target_price": price(p["target_price"]),
        "payout_multiplier": f"{p['payout_bps'] / 10000:.2f}",
        "potential_payout": money(p["potential_payout"]), "status": p["status"],
        "payout": money(p["payout_amount"]), "created_at": iso(p["created_at"]),
        "closes_at": iso(p["closes_at"]), "settled_at": iso(p["settled_at"]),
        "market_result": p["market_result"], "settle_price": price(p["settle_price"]),
    }
