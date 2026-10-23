from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.serialize import event_out, wallet_out
from app.database import get_db
from app.deps import CurrentUserDep
from app.services.ledger import get_wallet, list_transactions

router = APIRouter(tags=["wallet"])


@router.get("/wallet")
def read_wallet(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    return wallet_out(get_wallet(db, user.id))


@router.get("/wallet/transactions")
def read_transactions(
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[int | None, Query(ge=1)] = None,
):
    events, next_cursor = list_transactions(db, user.id, limit=limit, before_cursor=before)
    return {"items": [event_out(e) for e in events], "next_cursor": next_cursor}
