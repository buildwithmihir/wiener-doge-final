"""Telegram Mini App initData verification (server-side, per Telegram's docs).

Algorithm (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  1. Parse the query string, remove "hash".
  2. data_check_string = remaining "key=value" pairs sorted by key, joined with "\\n".
  3. secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
  4. expected   = HMAC_SHA256(key=secret_key, msg=data_check_string) as hex
  5. Compare in constant time, then check auth_date freshness.

Never trust initDataUnsafe or a bare Telegram user ID sent by the browser: only
a value that passes this function proves the user opened the app via Telegram.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.core.errors import Unauthorized

MAX_INIT_DATA_LENGTH = 8192
MAX_FUTURE_SKEW_SECONDS = 60
MAX_FIELD_LENGTH = 128


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    photo_url: str | None
    is_premium: bool


@dataclass(frozen=True)
class VerifiedInitData:
    user: TelegramUser
    auth_date: int
    query_id: str | None
    start_param: str | None
    fingerprint: str  # sha256 of Telegram's hash; usable for audit / abuse tracking


def _invalid() -> Unauthorized:
    return Unauthorized("Telegram login could not be verified.", "initdata_invalid")


def _opt_str(data: dict, key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str) and value:
        return value[:MAX_FIELD_LENGTH]
    return None


def verify_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600,
    now: float | None = None,
) -> VerifiedInitData:
    if not init_data or not init_data.strip():
        raise Unauthorized("Telegram login data is missing.", "initdata_missing")
    if len(init_data) > MAX_INIT_DATA_LENGTH:
        raise _invalid()
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True, max_num_fields=50)
    except ValueError:
        raise _invalid() from None

    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:  # duplicate keys are ambiguous: reject
            raise _invalid()
        fields[key] = value

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise _invalid()

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode(), received_hash.lower().encode()):
        raise _invalid()

    # Signature is valid from here on; now check freshness (replay window).
    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError:
        raise _invalid() from None
    current = time.time() if now is None else now
    if auth_date > current + MAX_FUTURE_SKEW_SECONDS:
        raise _invalid()
    if current - auth_date > max_age_seconds:
        raise Unauthorized("Login expired. Please reopen the app.", "initdata_expired")

    raw_user = fields.get("user")
    if not raw_user:
        raise _invalid()
    try:
        user_obj = json.loads(raw_user)
    except ValueError:
        raise _invalid() from None
    if not isinstance(user_obj, dict):
        raise _invalid()
    user_id = user_obj.get("id")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise _invalid()

    user = TelegramUser(
        id=user_id,
        first_name=_opt_str(user_obj, "first_name") or "",
        last_name=_opt_str(user_obj, "last_name"),
        username=_opt_str(user_obj, "username"),
        language_code=_opt_str(user_obj, "language_code"),
        photo_url=_opt_str(user_obj, "photo_url"),
        is_premium=bool(user_obj.get("is_premium", False)),
    )
    return VerifiedInitData(
        user=user,
        auth_date=auth_date,
        query_id=_opt_str(fields, "query_id"),
        start_param=_opt_str(fields, "start_param"),
        fingerprint=hashlib.sha256(received_hash.lower().encode()).hexdigest(),
    )


def verify_init_data_with_settings(init_data: str) -> VerifiedInitData:
    """Convenience wrapper using the configured bot token and max age."""
    from app.config import get_settings

    settings = get_settings()
    return verify_init_data(
        init_data,
        settings.telegram_bot_token,
        settings.telegram_initdata_max_age_seconds,
    )
