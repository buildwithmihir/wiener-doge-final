"""Admin API. Every call needs a logged-in admin (roles re-read from the database each time),
a written reason, and is audited. Money changes go through the ledger functions only."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.serialize import iso, market_out, money, price, wallet_out
from app.core.errors import AppError, NotFound
from app.core.rate_limit import ADMIN_LIMIT, limiter
from app.database import get_db
from app.deps import AdminUser, ModeratorUser
from app.services import audit as audit_service
from app.services import markets as market_service
from app.services import settlement
from app.services.ledger import adjust_demo_credits, get_wallet, parse_demo, run_reconciliation
from app.services.users import find_user_by_telegram_id, set_user_status

router = APIRouter(prefix="/admin", tags=["admin"])
Db = Annotated[Session, Depends(get_db)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketCreate(Strict):
    symbol: str = Field(min_length=1, max_length=16)
    duration_seconds: int
    target_price: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=300)
    publish: bool = True
    payout_bps: int | None = Field(default=None, gt=10000, le=100000)
    min_stake: str | None = Field(default=None, max_length=24)
    max_stake: str | None = Field(default=None, max_length=24)


class LadderDuration(Strict):
    duration_seconds: int
    payout_bps: int | None = Field(default=None, gt=10000, le=100000)


class LadderCreate(Strict):
    symbol: str = Field(min_length=1, max_length=16)
    durations: list[LadderDuration] = Field(min_length=1, max_length=4)
    reason: str = Field(min_length=1, max_length=300)


class Reason(Strict):
    reason: str = Field(min_length=1, max_length=300)


class CreditAdjust(Strict):
    amount: str = Field(min_length=1, max_length=24, description="Signed DEMO amount, e.g. '50' or '-12.5'")
    reason: str = Field(min_length=1, max_length=500)


class StatusChange(Strict):
    status: str = Field(min_length=1, max_length=12)
    reason: str = Field(min_length=1, max_length=300)


# ---- markets ----------------------------------------------------------------------------
@router.get("/markets")
def admin_list_markets(
    admin: ModeratorUser, db: Db,
    status: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    rows = market_service.list_markets(db, status=status, limit=limit, offset=offset, include_drafts=True)
    return {"items": [{**market_out(m), "admin_pause_reason": m.get("pause_reason")} for m in rows]}


@router.post("/markets", status_code=201)
@limiter.limit(ADMIN_LIMIT)
def admin_create_market(request: Request, body: MarketCreate, admin: AdminUser, db: Db):
    created = market_service.create_market(
        db, actor_id=admin.id, symbol=body.symbol, duration_seconds=body.duration_seconds,
        target_price=body.target_price, reason=body.reason, publish=body.publish,
        payout_bps=body.payout_bps,
        min_stake=parse_demo(body.min_stake) if body.min_stake else None,
        max_stake=parse_demo(body.max_stake) if body.max_stake else None,
    )
    return market_out(created)


@router.post("/markets/ladder", status_code=201)
@limiter.limit(ADMIN_LIMIT)
def admin_create_ladder(request: Request, body: LadderCreate, admin: AdminUser, db: Db):
    """Create a strike ladder (several target prices) for each chosen timeframe."""
    res = market_service.create_ladder(
        db, actor_id=admin.id, symbol=body.symbol, reason=body.reason,
        durations=[(d.duration_seconds, d.payout_bps) for d in body.durations],
    )
    return {"base_price": price(res["base_price"]), "created": len(res["created"]),
            "skipped": res["skipped"], "markets": [market_out(m) for m in res["created"]]}


@router.post("/markets/{market_id}/pause")
@limiter.limit(ADMIN_LIMIT)
def admin_pause_market(request: Request, market_id: uuid.UUID, body: Reason, admin: ModeratorUser, db: Db):
    return market_out(market_service.pause_market(db, actor_id=admin.id, market_id=market_id, reason=body.reason))


@router.post("/markets/{market_id}/resume")
@limiter.limit(ADMIN_LIMIT)
def admin_resume_market(request: Request, market_id: uuid.UUID, body: Reason, admin: ModeratorUser, db: Db):
    return market_out(market_service.resume_market(db, actor_id=admin.id, market_id=market_id, reason=body.reason))


@router.post("/markets/{market_id}/void")
@limiter.limit(ADMIN_LIMIT)
def admin_void_market(request: Request, market_id: uuid.UUID, body: Reason, admin: AdminUser, db: Db):
    """Refund every open prediction on this market and close it as void."""
    result = settlement.void_market_admin(db, actor_id=admin.id, market_id=market_id, reason=body.reason)
    return {"market_id": str(market_id), "result": result["result"], "refunded_predictions": result["predictions_settled"]}


# ---- users & demo credits -----------------------------------------------------------------
@router.get("/users/lookup")
def admin_find_user(admin: AdminUser, db: Db, telegram_id: Annotated[int, Query(gt=0, lt=10**13)]):
    user = find_user_by_telegram_id(db, telegram_id)
    if user is None:
        raise NotFound("User not found.", "user_not_found")
    return {
        "id": str(user["id"]), "telegram_id": user["telegram_id"], "username": user["username"],
        "display_name": user["display_name"], "status": user["status"],
        "created_at": iso(user["created_at"]), "last_seen_at": iso(user["last_seen_at"]),
        "wallet": wallet_out(get_wallet(db, user["id"])),
    }


@router.post("/users/{user_id}/credits")
@limiter.limit(ADMIN_LIMIT)
def admin_adjust_credits(
    request: Request, user_id: uuid.UUID, body: CreditAdjust, admin: AdminUser, db: Db,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=100)] = None,
):
    """Add or remove DEMO credits (never below zero). Same Idempotency-Key = applied once."""
    if not idempotency_key:
        raise AppError("invalid_key", "Idempotency-Key header is required.", 422)
    amount = parse_demo(body.amount)
    new_available = adjust_demo_credits(
        db, user_id=user_id, amount_units=amount, idempotency_key=idempotency_key,
        actor_id=admin.id, reason=body.reason,
    )
    return {"available": money(new_available), "wallet": wallet_out(get_wallet(db, user_id))}


@router.post("/users/{user_id}/status")
@limiter.limit(ADMIN_LIMIT)
def admin_set_status(request: Request, user_id: uuid.UUID, body: StatusChange, admin: AdminUser, db: Db):
    return set_user_status(db, actor_id=admin.id, user_id=user_id, status=body.status, reason=body.reason)


# ---- integrity & audit --------------------------------------------------------------------
@router.get("/reconcile")
def admin_reconcile(admin: AdminUser, db: Db):
    """Ledger integrity check. `ok: true` means every invariant holds."""
    issues = run_reconciliation(db)
    return {"ok": not issues, "issues": [{"check": c, "detail": d} for c, d in issues]}


@router.get("/audit")
def admin_audit(
    admin: AdminUser, db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: Annotated[int | None, Query(ge=1)] = None,
):
    items, next_cursor = audit_service.list_audit(db, limit=limit, before_id=before)
    return {
        "items": [{**i, "actor_user_id": str(i["actor_user_id"]) if i["actor_user_id"] else None,
                   "created_at": iso(i["created_at"])} for i in items],
        "next_cursor": next_cursor,
    }
