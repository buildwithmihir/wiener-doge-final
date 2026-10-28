from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.admin_alerts import notify_admin_channel
from app.services.ledger import format_demo, parse_demo

from app.api.serialize import iso, money
from app.core.errors import AppError
from app.core.rate_limit import ADMIN_LIMIT, WRITE_LIMIT, limiter
from app.database import get_db
from app.deps import AdminUser, CurrentUserDep
from app.payments import service

router = APIRouter(tags=["payments"])
Db = Annotated[Session, Depends(get_db)]


def _native_text(w: dict) -> str | None:
    if w.get("native_amount") is None or w.get("native_decimals") is None:
        return None
    value = Decimal(int(w["native_amount"])) / (Decimal(10) ** int(w["native_decimals"]))
    out = format(value, "f")
    return out.rstrip("0").rstrip(".") if "." in out else out


def _out(w: dict) -> dict:
    return {"id": str(w["id"]), "status": w["status"], "asset": w["asset"], "amount": money(w["amount"]),
            "native_amount": _native_text(w), "address": w["destination_ref"], "created_at": iso(w["created_at"]),
            "tx_signature": w.get("tx_signature"), "note": w.get("reviewed_reason")}


@router.get("/deposit/address")
def deposit_address(user: CurrentUserDep, db: Db):
    row = service.ensure_deposit_address(db, user.id)
    minimum = int(db.execute(text("select wd_setting_int('payments.min_deposit', 1000000)")).scalar_one())
    return {"network": "Solana", "address": row["owner_address"], "min_deposit": money(minimum),
            "assets": [{"symbol": "SOL", "name": "Solana"}, {"symbol": "WIENER", "name": "Wiener"}]}


class WithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset: Literal["SOL", "WIENER"]
    amount: str = Field(min_length=1, max_length=24, description="USD amount, e.g. '25' or '12.5'")
    address: str = Field(min_length=32, max_length=44)


@router.post("/withdrawals", status_code=201)
@limiter.limit(WRITE_LIMIT)
def request_withdrawal(request: Request, body: WithdrawIn, user: CurrentUserDep, db: Db,
                       background: BackgroundTasks,
                       idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=120)] = None):
    if not idempotency_key:
        raise AppError("invalid_key", "Idempotency-Key header is required.", 422)
    already = db.execute(
        text("select 1 from withdrawals where user_id = :u and idempotency_key = :k"),
        {"u": user.id, "k": idempotency_key},
    ).first() is not None
    rpc = service.open_rpc()
    try:
        w = service.create_withdrawal(db, rpc, user_id=user.id, asset=body.asset,
                                      usd_units_=parse_demo(body.amount), address=body.address, key=idempotency_key)
    finally:
        rpc.close()
    if not already:   # a retry of the same request must not alert twice
        background.add_task(notify_admin_channel, (
            "New withdrawal request\n"
            f"${format_demo(int(w['amount']))} as {w['asset']}\n"
            f"User: {user.display_name} (tg {user.telegram_id})\n"
            f"Address: {w['destination_ref']}\n\n"
            "Open the app: Admin > Withdrawals to approve or reject."
        ))
    return _out(w)


@router.get("/withdrawals")
def my_withdrawals(user: CurrentUserDep, db: Db):
    return {"items": [_out(w) for w in service.list_withdrawals(db, user.id)]}


class Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=300)


@router.get("/admin/withdrawals")
def admin_withdrawals(admin: AdminUser, db: Db, status: Annotated[str | None, Query(max_length=12)] = "pending"):
    return {"items": [{**_out(w), "user_id": str(w["user_id"])} for w in service.list_withdrawals(db, None, status)]}


@router.post("/admin/withdrawals/{wid}/approve")
@limiter.limit(ADMIN_LIMIT)
def admin_approve(request: Request, wid: uuid.UUID, body: Reason, admin: AdminUser, db: Db):
    service.approve_withdrawal(db, admin.id, wid, body.reason)
    return {"ok": True}


@router.post("/admin/withdrawals/{wid}/reject")
@limiter.limit(ADMIN_LIMIT)
def admin_reject(request: Request, wid: uuid.UUID, body: Reason, admin: AdminUser, db: Db):
    service.reject_withdrawal(db, admin.id, wid, body.reason)
    return {"ok": True}