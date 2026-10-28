"""Telegram bot logic. Pure functions: an incoming update in, an optional reply out.

Replies are returned as the webhook RESPONSE (Telegram executes `{"method": "sendMessage", ...}`
sent back in the HTTP response), so the bot makes no outbound calls and needs no bot token at
request time; only the webhook secret is checked. Messages are plain text (no parse_mode) and
never echo user-supplied text, so there is nothing to escape or inject.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.api.serialize import price
from app.services.ledger import format_demo, get_wallet
from app.services.markets import list_markets
from app.services.users import find_user_by_telegram_id

WELCOME = (
    "Welcome to WienerDoge!\n\n"
    "Pick a market for SOL or WIENER and predict if the price will close ABOVE or BELOW the target. "
    "Price at close >= target means ABOVE wins; below the target means BELOW wins."
)
HELP = (
    "How it works\n"
    "1. Open the app and pick a market (24h, 48h, 7d or 30d).\n"
    "2. Choose ABOVE or BELOW and your stake.\n"
    "3. When the market closes it is settled from a fresh price snapshot. A win pays the multiplier "
    "shown on the market; a loss forfeits the stake. If no reliable price is available the market is "
    "voided and every stake is refunded.\n\n"
    "Commands: /start /balance /markets /help"
)
UNKNOWN = "I did not understand that. Send /help to see what I can do."


def parse_command(text: str | None) -> tuple[str | None, str]:
    """'/start@MyBot ref_ABC' -> ('start', 'ref_ABC'). Not a command -> (None, '')."""
    if not text or not text.startswith("/"):
        return None, ""
    head, _, rest = text.strip().partition(" ")
    command = head[1:].split("@", 1)[0].lower()
    return (command or None), rest.strip()[:200]


def _open_app_markup(mini_app_url: str) -> dict[str, Any] | None:
    if not mini_app_url.startswith("https://"):
        return None                       # Telegram only accepts https web apps
    return {"inline_keyboard": [[{"text": "Open WienerDoge", "web_app": {"url": mini_app_url}}]]}


def _reply(chat_id: int, text: str, markup: dict[str, Any] | None = None) -> dict[str, Any]:
    reply: dict[str, Any] = {"method": "sendMessage", "chat_id": chat_id, "text": text[:4000],
                             "disable_web_page_preview": True}
    if markup:
        reply["reply_markup"] = markup
    return reply


def _duration_label(seconds: int) -> str:
    return {86400: "24h", 172800: "48h", 604800: "7d", 2592000: "30d"}.get(seconds, f"{seconds}s")


def handle_update(db: Session, update: Any, mini_app_url: str = "") -> dict[str, Any] | None:
    """Return a webhook reply (dict) or None when there is nothing to say."""
    if not isinstance(update, dict):
        return None
    message = update.get("message")
    if not isinstance(message, dict):
        return None                       # we only subscribe to plain messages
    chat, sender = message.get("chat"), message.get("from")
    if not isinstance(chat, dict) or not isinstance(sender, dict):
        return None
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int) or not isinstance(sender.get("id"), int):
        return None                       # private chats only; ignore groups and channels
    if sender.get("is_bot"):
        return None

    chat_id = chat["id"]
    markup = _open_app_markup(mini_app_url)
    command, _payload = parse_command(message.get("text"))

    if command == "start":
        return _reply(chat_id, WELCOME, markup)
    if command == "help":
        return _reply(chat_id, HELP, markup)
    if command == "balance":
        user = find_user_by_telegram_id(db, sender["id"])
        if user is None:
            return _reply(chat_id, "Open the app once to create your account.", markup)
        if user["status"] != "active":
            return _reply(chat_id, "This account is not active.")
        wallet = get_wallet(db, user["id"])
        return _reply(
            chat_id,
            f"Available: ${format_demo(wallet.available)}\nIn open predictions: ${format_demo(wallet.reserved)}\n"
            f"Total: ${format_demo(wallet.total)}",
            markup,
        )
    if command == "markets":
        rows = list_markets(db, status="open", limit=5)
        if not rows:
            return _reply(chat_id, "No open markets right now. Check back soon.", markup)
        lines = []
        for m in rows:
            hours = max(1, int(m["closes_in_seconds"]) // 3600)
            lines.append(f"{m['symbol']} {_duration_label(m['duration_seconds'])}: target ${price(m['target_price'])}, "
                         f"closes in about {hours}h")
        return _reply(chat_id, "Open markets\n" + "\n".join(lines) + "\n\nOpen the app to predict.", markup)

    return _reply(chat_id, UNKNOWN, markup)
