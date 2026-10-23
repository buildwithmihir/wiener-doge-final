"""Telegram webhook. Telegram proves a request is genuine by echoing the secret we registered in
the X-Telegram-Bot-Api-Secret-Token header; anything else is rejected."""
from __future__ import annotations

import hmac
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.bot.handlers import handle_update
from app.config import get_settings
from app.core.errors import NotFound, Unauthorized
from app.database import get_db

log = logging.getLogger("wienerdoge.bot")
router = APIRouter(tags=["telegram"])
MAX_BODY_BYTES = 64 * 1024
MIN_SECRET_LENGTH = 16


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    settings = get_settings()
    expected = settings.telegram_webhook_secret
    if len(expected) < MIN_SECRET_LENGTH:
        raise NotFound("Not found.", "not_found")              # off until a secret is configured
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token.encode(), expected.encode()
    ):
        raise Unauthorized("Invalid webhook secret.", "invalid_webhook_secret")

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return {}
    try:
        update = await request.json()
    except ValueError:
        return {}                                            # not JSON: nothing to do
    try:
        with db.begin_nested():                              # a failure here must not poison the request transaction
            reply = handle_update(db, update, settings.mini_app_url)
    except Exception:  # noqa: BLE001 - always answer 200 so Telegram does not retry forever
        log.exception("bot update failed")
        return {}
    return reply or {}
