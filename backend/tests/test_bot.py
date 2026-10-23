"""Pure tests for the bot helpers and the Telegram setup script (no database, no network).

Run from the backend folder:
    python -m tests.test_bot
"""
import os

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

import httpx

from app.bot.handlers import DEMO_NOTE, handle_update, parse_command
from app.bot.setup import build_menu_payload, build_webhook_payload, run_setup

URL = "https://app.example.com"
TOKEN = "123456:SECRET_TOKEN_VALUE"
SECRET = "webhook_secret-0123456789"


def private(text, uid=1, chat_type="private", is_bot=False):
    return {"update_id": 1, "message": {"text": text, "chat": {"id": uid, "type": chat_type},
                                        "from": {"id": uid, "is_bot": is_bot}}}


def test_parse_command():
    assert parse_command("/start") == ("start", "")
    assert parse_command("/start ref_ABC123") == ("start", "ref_ABC123")
    assert parse_command("/Start@WienerDogeBot hi") == ("start", "hi")
    assert parse_command("hello") == (None, "")
    assert parse_command(None) == (None, "")
    assert parse_command("/") == (None, "")
    assert parse_command("/x " + "a" * 500)[1] == "a" * 200


def test_start_and_help_replies_need_no_database():
    r = handle_update(None, private("/start"), URL)
    assert r["method"] == "sendMessage" and r["chat_id"] == 1
    assert "DEMO" in r["text"] and "no cash value" in r["text"] and DEMO_NOTE in r["text"]
    assert r["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"] == URL
    h = handle_update(None, private("/help"), URL)
    assert "ABOVE" in h["text"] and "voided" in h["text"]


def test_no_button_without_https_url():
    assert "reply_markup" not in handle_update(None, private("/start"), "http://localhost:5173")
    assert "reply_markup" not in handle_update(None, private("/start"), "")


def test_ignored_updates():
    for update in (None, [], "x", {}, {"message": "x"}, {"edited_message": {}}, {"callback_query": {}},
                   private("/start", chat_type="group"), private("/start", chat_type="channel"),
                   private("/start", is_bot=True), {"message": {"text": "/start", "chat": {"id": "1", "type": "private"},
                                                                 "from": {"id": 1}}}):
        assert handle_update(None, update, URL) is None, update


def test_unknown_text_never_echoes_user_input():
    r = handle_update(None, private("<b>hack</b> https://evil.example"), URL)
    assert "hack" not in r["text"] and "evil" not in r["text"] and "/help" in r["text"]
    assert "parse_mode" not in r


def test_webhook_payload_rules():
    p = build_webhook_payload("https://api.example.com/api/v1/telegram/webhook", SECRET)
    assert p["secret_token"] == SECRET and p["allowed_updates"] == ["message"] and p["drop_pending_updates"] is False
    for bad_url in ("http://api.example.com/x", "", "ftp://x"):
        try:
            build_webhook_payload(bad_url, SECRET)
        except ValueError:
            continue
        raise AssertionError(bad_url)
    for bad_secret in ("", "short", "has space in it 0123456789", "bad/char/0123456789", "x" * 300):
        try:
            build_webhook_payload("https://a.example/w", bad_secret)
        except ValueError:
            continue
        raise AssertionError(bad_secret)
    assert build_menu_payload(URL)["menu_button"]["web_app"]["url"] == URL
    try:
        build_menu_payload("http://x")
    except ValueError:
        pass
    else:
        raise AssertionError("http menu url accepted")


def test_run_setup_calls_three_methods_and_never_leaks_token():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"ok": True, "result": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        lines = run_setup(client, TOKEN, "https://api.example.com/w", SECRET, URL)
    assert calls == ["setWebhook", "setMyCommands", "setChatMenuButton"]
    assert lines == ["setWebhook: ok", "setMyCommands: ok", "setChatMenuButton: ok"]

    def refuse(request):
        return httpx.Response(200, json={"ok": False, "description": "Unauthorized"})

    def boom(request):
        raise httpx.ConnectError("could not reach " + str(request.url))

    for transport in (refuse, boom):
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            try:
                run_setup(client, TOKEN, "https://api.example.com/w", SECRET, URL)
            except RuntimeError as exc:
                assert TOKEN not in str(exc) and "SECRET_TOKEN_VALUE" not in str(exc), str(exc)
            else:
                raise AssertionError("failure not reported")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
