"""Posts short alerts to the admin Telegram channel. Never raises: an alert must not break a request."""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.services.notifications import SendResult, make_telegram_sender

log = logging.getLogger("wienerdoge.alerts")


def notify_admin_channel(text: str) -> None:
    s = get_settings()
    if not s.admin_channel_id or not s.telegram_bot_token:
        return
    try:
        chat_id = int(s.admin_channel_id)
    except ValueError:
        log.warning("ADMIN_CHANNEL_ID is not a number")
        return
    try:
        with httpx.Client(timeout=4.0) as client:
            result = make_telegram_sender(s.telegram_bot_token, client)(chat_id, text)
        if result is not SendResult.SENT:
            log.warning("admin alert not delivered (%s): is the bot an admin of the channel?", result.value)
    except Exception as exc:  # noqa: BLE001
        log.warning("admin alert failed: %s", type(exc).__name__)