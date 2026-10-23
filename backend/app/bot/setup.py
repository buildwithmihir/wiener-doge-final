"""One-time Telegram setup, run from YOUR computer (needs internet and your real bot token).

    python -m app.bot.setup --webhook-url https://YOUR-API-HOST/api/v1/telegram/webhook

Registers: the webhook (with your secret), the command list, and the menu button that opens the
Mini App. The bot token is read from backend/.env and is never printed.
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import Any

import httpx

from app.config import get_settings

SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")
COMMANDS = [
    {"command": "start", "description": "Open WienerDoge"},
    {"command": "markets", "description": "Show open markets"},
    {"command": "balance", "description": "Show your DEMO balance"},
    {"command": "help", "description": "How it works"},
]


def build_webhook_payload(url: str, secret: str, drop_pending: bool = False) -> dict[str, Any]:
    if not url.startswith("https://"):
        raise ValueError("webhook URL must start with https://")
    if not SECRET_RE.match(secret):
        raise ValueError("TELEGRAM_WEBHOOK_SECRET must be 16-256 characters of A-Z a-z 0-9 _ -")
    return {"url": url, "secret_token": secret, "allowed_updates": ["message"],
            "max_connections": 20, "drop_pending_updates": drop_pending}


def build_menu_payload(mini_app_url: str) -> dict[str, Any]:
    if not mini_app_url.startswith("https://"):
        raise ValueError("MINI_APP_URL must start with https://")
    return {"menu_button": {"type": "web_app", "text": "Play", "web_app": {"url": mini_app_url}}}


def run_setup(client: httpx.Client, token: str, webhook_url: str, secret: str, mini_app_url: str,
              drop_pending: bool = False) -> list[str]:
    """Returns one short status line per step. Raises RuntimeError with a safe message on failure."""
    steps = [
        ("setWebhook", build_webhook_payload(webhook_url, secret, drop_pending)),
        ("setMyCommands", {"commands": COMMANDS}),
        ("setChatMenuButton", build_menu_payload(mini_app_url)),
    ]
    results = []
    for method, payload in steps:
        try:
            response = client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=15)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # never include str(exc): it can contain the request URL, which contains the token
            raise RuntimeError(f"{method} failed ({type(exc).__name__})") from None
        if not body.get("ok"):
            raise RuntimeError(f"{method} rejected by Telegram: {body.get('description', 'unknown error')}")
        results.append(f"{method}: ok")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register the WienerDoge bot webhook and menu button.")
    parser.add_argument("--webhook-url", required=True)
    parser.add_argument("--drop-pending", action="store_true", help="discard updates queued while the bot was offline")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is empty in backend/.env")
        return 1
    try:
        with httpx.Client() as client:
            for line in run_setup(client, settings.telegram_bot_token, args.webhook_url,
                                  settings.telegram_webhook_secret, settings.mini_app_url, args.drop_pending):
                print(line)
    except (ValueError, RuntimeError) as exc:
        print(f"Setup failed: {exc}")
        return 1
    print("Done. Open your bot in Telegram and send /start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
