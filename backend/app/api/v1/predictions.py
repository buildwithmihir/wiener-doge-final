from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.serialize import prediction_out
from app.core.errors import AppError
from app.core.rate_limit import PREDICTION_LIMIT, limiter
from app.database import get_db
from app.deps import CurrentUserDep
from app.services.ledger import parse_demo
from app.services.predictions import list_predictions, place_prediction

import uuid

router = APIRouter(tags=["predictions"])


class PredictionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_id: uuid.UUID
    direction: str = Field(min_length=1, max_length=8)
    stake: str = Field(min_length=1, max_length=24, description="DEMO amount as text, e.g. '25' or '12.5'")
    expected_target_price: str | None = Field(default=None, max_length=40)


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
