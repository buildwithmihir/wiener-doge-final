"""Unit tests for notification texts and the Telegram sender (no database, no internet)."""
import logging
import os
from decimal import Decimal

os.environ.setdefault("JWT_SECRET", "t" * 48)
os.environ.setdefault("APP_ENV", "development")

import httpx

from app.services.notifications import SendResult, make_telegram_sender, result_text

DEMO = 1_000_000
TOKEN = "123456:SECRET_TOKEN_VALUE"


def test_result_texts_are_plain_and_demo_labelled():
    won = result_text("SOL", "above", Decimal("119.400000000000"), "won", 10 * DEMO, 18 * DEMO)
    lost = result_text("WIENER", "below", Decimal("0.000012"), "lost", 5 * DEMO, 0)
    void = result_text("SOL", "above", Decimal("119.4"), "refunded", 5 * DEMO, 5 * DEMO)
    assert "won" in won and "18 demo credits" in won and "stake 10" in won and "SOL ABOVE 119.4" in won
    assert "did not win" in lost and "5 demo credits" in lost and "WIENER BELOW 0.000012" in lost
    assert "voided" in void and "refunded" in void
    for m in (won, lost, void):
        assert "Demo credits only. No cash value." in m and "$" not in m and "<" not in m


def make(handler):
    return make_telegram_sender(TOKEN, httpx.Client(transport=httpx.MockTransport(handler)))


def test_sender_maps_http_results():
    seen = []

    def ok(req):
        seen.append(req)
        return httpx.Response(200, json={"ok": True})

    send = make(ok)
    assert send(42, "hello") == SendResult.SENT
    assert str(seen[0].url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    import json
    assert json.loads(seen[0].content) == {"chat_id": 42, "text": "hello", "disable_web_page_preview": True}
    assert make(lambda r: httpx.Response(403))(1, "x") == SendResult.PERMANENT     # bot blocked
    assert make(lambda r: httpx.Response(400))(1, "x") == SendResult.PERMANENT     # chat not found
    assert make(lambda r: httpx.Response(429))(1, "x") == SendResult.RETRY
    assert make(lambda r: httpx.Response(502))(1, "x") == SendResult.RETRY


def test_network_error_retries_and_never_logs_the_token(caplog):
    def boom(req):
        raise httpx.ConnectError(f"cannot reach {req.url}")        # httpx errors can contain the URL

    with caplog.at_level(logging.DEBUG):
        assert make(boom)(1, "x") == SendResult.RETRY
        assert make(lambda r: httpx.Response(500))(1, "x") == SendResult.RETRY
    assert TOKEN not in caplog.text and "SECRET_TOKEN_VALUE" not in caplog.text
