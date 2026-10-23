"""Telegram webhook end-to-end test. SAFE for a real Supabase project: one transaction,
rolled back at the end. No network calls.

Run from the backend folder:
    python -m tests.test_bot_db
"""
import os
import sys
import uuid

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "hook_secret-0123456789"
os.environ["MINI_APP_URL"] = "https://app.example.com"
ADMIN_TG = 9_599_000_000_003
os.environ["ADMIN_TELEGRAM_IDS"] = str(ADMIN_TG)

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.rate_limit import limiter
from app.database import check_db, get_db, session_scope
from app.main import app

HOOK = "/api/v1/telegram/webhook"
GOOD = {"X-Telegram-Bot-Api-Secret-Token": "hook_secret-0123456789"}


def message(text_, uid, chat_type="private"):
    return {"update_id": 7, "message": {"text": text_, "chat": {"id": uid, "type": chat_type},
                                        "from": {"id": uid, "is_bot": False, "first_name": "X"}}}


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        def override_get_db():
            with db.begin_nested():
                yield db

        app.dependency_overrides[get_db] = override_get_db
        limiter.reset()
        client = TestClient(app, raise_server_exceptions=False)
        tag = uuid.uuid4().int % 10**9
        uid = 9_700_000_000_000 + tag
        grant_demo = int(db.execute(text("select wd_setting_int('wallet.signup_grant', 0)")).scalar_one()) // 1_000_000

        # ---- the secret is the only way in -----------------------------------------------
        assert client.post(HOOK, json=message("/start", uid)).status_code == 401
        assert client.post(HOOK, json=message("/start", uid),
                           headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret-0123456789"}).status_code == 401
        print("PASS webhook rejects requests without the right secret")

        r = client.post(HOOK, json=message("/start", uid), headers=GOOD)
        assert r.status_code == 200, r.text
        reply = r.json()
        assert reply["method"] == "sendMessage" and reply["chat_id"] == uid
        assert "DEMO" in reply["text"] and "no cash value" in reply["text"]
        assert reply["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"] == "https://app.example.com"
        print("PASS /start replies with the demo notice and the Open WienerDoge button")

        # ---- /balance --------------------------------------------------------------------
        r = client.post(HOOK, json=message("/balance", uid), headers=GOOD).json()
        assert "Open the app once" in r["text"]
        client.post("/api/v1/auth/dev", json={"telegram_id": uid, "display_name": "Bot Tester"})
        r = client.post(HOOK, json=message("/balance", uid), headers=GOOD).json()
        assert f"Available: {grant_demo} DEMO" in r["text"] and "Total:" in r["text"], r
        print("PASS /balance: unknown user is invited to open the app; existing user sees the wallet")

        # ---- /markets --------------------------------------------------------------------
        empty = client.post(HOOK, json=message("/markets", uid), headers=GOOD).json()["text"]
        admin = client.post("/api/v1/auth/dev", json={"telegram_id": ADMIN_TG, "display_name": "Boss"}).json()
        target = f"{(tag % 900000) / 1000 + 4000:.3f}"
        made = client.post("/api/v1/admin/markets", headers={"Authorization": f"Bearer {admin['access_token']}"},
                           json={"symbol": "SOL", "duration_seconds": 86400, "target_price": target, "reason": "bot test"})
        assert made.status_code == 201, made.text
        listing = client.post(HOOK, json=message("/markets", uid), headers=GOOD).json()["text"]
        assert "SOL 24h" in listing and f"${target.rstrip('0').rstrip('.')}" in listing, listing
        print("PASS /markets lists open markets")

        # ---- suspended users get no balance ---------------------------------------------
        db.execute(text("update users set status = 'suspended' where telegram_id = :t"), {"t": uid})
        assert "not active" in client.post(HOOK, json=message("/balance", uid), headers=GOOD).json()["text"]
        print("PASS suspended account sees no balance")

        # ---- things the bot must ignore or survive ---------------------------------------
        assert client.post(HOOK, json=message("/start", uid, chat_type="group"), headers=GOOD).json() == {}
        assert client.post(HOOK, json={"update_id": 8, "edited_message": {}}, headers=GOOD).json() == {}
        assert client.post(HOOK, content=b"not json at all", headers={**GOOD, "Content-Type": "application/json"}).json() == {}
        assert client.post(HOOK, json=[1, 2, 3], headers=GOOD).json() == {}
        assert client.post(HOOK, content=b"x" * 70_000, headers={**GOOD, "Content-Type": "application/json"}).json() == {}
        reply = client.post(HOOK, json=message("/nonsense <script>", uid), headers=GOOD).json()
        assert "script" not in reply["text"]
        print("PASS groups, edits, junk and oversized bodies are ignored without errors; no input echoed")

        app.dependency_overrides.clear()
        db.rollback()
    print("ALL BOT WEBHOOK TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
