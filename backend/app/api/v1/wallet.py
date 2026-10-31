from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.serialize import event_out, money, wallet_out
from app.database import get_db
from app.deps import CurrentUserDep
from app.services.ledger import get_wallet, list_transactions

router = APIRouter(tags=["wallet"])


@router.get("/wallet")
def read_wallet(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    return wallet_out(get_wallet(db, user.id))


@router.get("/wallet/wager")
def read_wager(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    """Wager rule: deposits and bonuses must be wagered (multiplier x, default 2x) on SETTLED bets
    before a withdrawal can be requested. Cashed-out and open bets do not count."""
    row = db.execute(text("select required, wagered from wager_status(:u)"), {"u": user.id}).mappings().one()
    required, wagered = int(row["required"]), int(row["wagered"])
    multiplier = int(db.execute(text("select wd_setting_int('payments.wager_multiplier', 2)")).scalar_one())
    return {
        "multiplier": multiplier,
        "required": money(required),
        "wagered": money(wagered),
        "remaining": money(max(0, required - wagered)),
        "met": wagered >= required,
    }


@router.get("/wallet/transactions")
def read_transactions(
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[int | None, Query(ge=1)] = None,
):
    events, next_cursor = list_transactions(db, user.id, limit=limit, before_cursor=before)
    return {"items": [event_out(e) for e in events], "next_cursor": next_cursor}