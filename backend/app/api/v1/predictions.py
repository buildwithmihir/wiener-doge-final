from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.serialize import money, prediction_out, price
from app.core.errors import AppError
from app.core.rate_limit import PREDICTION_LIMIT, limiter
from app.database import get_db
from app.deps import CurrentUserDep
from app.services import cashout as cashout_service
from app.services.ledger import parse_demo
from app.services.predictions import list_predictions, place_prediction

router = APIRouter(tags=["predictions"])


class PredictionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_id: uuid.UUID
    direction: str = Field(min_length=1, max_length=8)
    stake: str = Field(min_length=1, max_length=24, description="DEMO amount as text, e.g. '25' or '12.5'")
    expected_target_price: str | None = Field(default=None, max_length=40)


class CashoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_amount: str | None = Field(default=None, max_length=24, description="The cashout value the user saw")


@router.post("/predictions", status_code=201)
@limiter.limit(PREDICTION_LIMIT)
def create_prediction(
    request: Request,
    body: PredictionIn,
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=120)] = None,
):
    """Send an Idempotency-Key header (a fresh random value per tap). Retrying with the SAME key
    returns the same prediction instead of taking the stake twice."""
    if not idempotency_key:
        raise AppError("invalid_key", "Idempotency-Key header is required.", 422)
    stake_units = parse_demo(body.stake)
    prediction = place_prediction(
        db, user_id=user.id, market_id=body.market_id, direction=body.direction,
        stake_units=stake_units, idempotency_key=idempotency_key,
        expected_target_price=body.expected_target_price,
    )
    return prediction_out(prediction)


@router.get("/predictions")
def read_predictions(
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[str | None, Query(max_length=12)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    rows = list_predictions(db, user.id, status=status, limit=limit, offset=offset)
    return {"items": [prediction_out(p) for p in rows]}


@router.get("/predictions/quotes")
def read_cashout_quotes(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    """Live cashout value of every open prediction (winning bets are worth more, losing bets less)."""
    items = []
    for q in cashout_service.open_quotes(db, user.id):
        items.append({
            "prediction_id": str(q["prediction_id"]),
            "available": q["available"],
            "reason": q["reason"],
            "message": cashout_service.REASONS.get(q["reason"]) if q["reason"] else None,
            "amount": money(q["amount"]) if q["amount"] is not None else None,
            "current_price": price(q["current_price"]),
            "winning": q["winning"],
            "seconds_left": q["seconds_left"],
        })
    return {"items": items}


@router.post("/predictions/{prediction_id}/cashout")
@limiter.limit(PREDICTION_LIMIT)
def cashout_prediction(
    request: Request,
    prediction_id: uuid.UUID,
    body: CashoutIn,
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
):
    expected = parse_demo(body.expected_amount) if body.expected_amount else None
    done = cashout_service.cashout(db, user_id=user.id, prediction_id=prediction_id, expected_units=expected)
    return prediction_out(done)