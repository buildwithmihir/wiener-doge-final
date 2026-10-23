"""Public market data (no login needed; nothing here is personal)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.serialize import market_out
from app.database import get_db
from app.services.markets import get_market, list_markets, price_chart

router = APIRouter(tags=["markets"])


@router.get("/markets")
def read_markets(
    db: Annotated[Session, Depends(get_db)],
    symbol: Annotated[str | None, Query(max_length=16)] = None,
    duration_seconds: Annotated[int | None, Query()] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    rows = list_markets(db, symbol=symbol, duration_seconds=duration_seconds, status=status,
                        limit=limit, offset=offset)
    return {"items": [market_out(m) for m in rows]}


@router.get("/markets/{market_id}")
def read_market(market_id: uuid.UUID, db: Annotated[Session, Depends(get_db)]):
    return market_out(get_market(db, market_id))


@router.get("/assets/{symbol}/chart")
def read_chart(symbol: Annotated[str, Path(max_length=16)], db: Annotated[Session, Depends(get_db)],
               range: Annotated[str, Query(max_length=4)] = "24h"):
    return price_chart(db, symbol, range)
