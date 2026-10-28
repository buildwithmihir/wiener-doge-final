"""Health, public config, and the scheduler endpoint."""
from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.payments.service import run_payments_tick

from app.config import get_settings
from app.core.errors import NotFound, Unauthorized
from app.database import check_db, get_db
from app.providers.registry import ProviderRegistry, build_default_registry
from app.services.notifications import Sender, make_telegram_sender
from app.services.worker import tick

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    probe = check_db()
    return {"status": "ok" if probe.get("ok") else "unavailable", "database": probe.get("ok", False)}


@router.get("/config")
def public_config(db: Annotated[Session, Depends(get_db)]):
    """What the app needs to show honest labels. Payments are off in this demo."""
    payments = db.execute(text("select wd_setting_bool('payments.enabled', false)")).scalar_one()
    return {
        "demo_mode": True,
        "payments_enabled": bool(payments),
        "currency": "DEMO credits (no cash value, not redeemable)",
        "settlement_rule": "Price at close >= target: ABOVE wins. Below target: BELOW wins.",
        "durations_seconds": [86400, 172800, 604800, 2592000],
    }


def get_registry(request: Request) -> ProviderRegistry:
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        registry = build_default_registry()
        request.app.state.registry = registry
    return registry


def get_notifier(request: Request) -> Sender | None:
    """One Telegram sender per process, built from the server-side bot token (never exposed)."""
    state = request.app.state
    if not hasattr(state, "notifier"):
        token = get_settings().telegram_bot_token
        state.notifier = make_telegram_sender(token) if token and ":" in token else None
    return state.notifier


@router.post("/internal/tick", include_in_schema=False)
def run_scheduler_tick(
    db: Annotated[Session, Depends(get_db)],
    registry: Annotated[ProviderRegistry, Depends(get_registry)],
    notifier: Annotated[Sender | None, Depends(get_notifier)],
    x_tick_secret: Annotated[str | None, Header()] = None,
):
    """Called by the scheduler (about once a minute). Not for browsers."""
    expected = get_settings().tick_secret
    if not expected or len(expected) < 32:
        raise NotFound("Not found.", "not_found")           # endpoint is off until a secret is set
    if not x_tick_secret or not hmac.compare_digest(x_tick_secret.encode(), expected.encode()):
        raise Unauthorized("Invalid scheduler secret.", "invalid_tick_secret")
    return tick(db, registry, notifier=notifier)


@router.post("/internal/payments-tick", include_in_schema=False)
def run_payments(x_tick_secret: Annotated[str | None, Header()] = None):
    expected = get_settings().tick_secret
    if not expected or len(expected) < 32:
        raise NotFound("Not found.", "not_found")
    if not x_tick_secret or not hmac.compare_digest(x_tick_secret.encode(), expected.encode()):
        raise Unauthorized("Invalid scheduler secret.", "invalid_tick_secret")
    return run_payments_tick()