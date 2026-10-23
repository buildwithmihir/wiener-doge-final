"""End-to-end API test through FastAPI's TestClient. SAFE for a real Supabase project: every
request runs inside ONE outer transaction (each request in its own savepoint) that is
rolled back at the end, so nothing is saved. No network calls (mock price provider).

Run from the backend folder:
    python -m tests.test_api_db
"""
import os
import sys
import uuid

# Set BEFORE the app is imported (settings are read once). Environment beats backend/.env.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST_TOKEN"
os.environ["TICK_SECRET"] = "s" * 40
os.environ["LOG_LEVEL"] = "WARNING"
ADMIN_TG = 9_599_000_000_001
os.environ["ADMIN_TELEGRAM_IDS"] = str(ADMIN_TG)

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.system import get_registry
from app.core.rate_limit import limiter
from app.database import check_db, get_db, session_scope
from app.main import app
from app.providers.mock_provider import MockProvider
from app.providers.registry import ProviderRegistry
from app.services.markets import create_market
from tests.test_telegram_auth import BOT_TOKEN, make_fields, sign


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        def override_get_db():
            with db.begin_nested():          # one savepoint per request
                yield db

        mock = MockProvider()
        registry = ProviderRegistry()
        registry.register(mock)
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_registry] = lambda: registry
        limiter.reset()
        client = TestClient(app, raise_server_exceptions=False)
        API = "/api/v1"
        tag = uuid.uuid4().int % 10**9
        grant = int(db.execute(text("select wd_setting_int('wallet.signup_grant', 0)")).scalar_one())

        def err(resp, status, code):
            assert resp.status_code == status, (resp.status_code, resp.text)
            assert resp.json()["error"]["code"] == code, resp.json()

        def auth(token):
            return {"Authorization": f"Bearer {token}"}

        # ---- public + auth basics ------------------------------------------------------
        assert client.get(f"{API}/health").json() == {"status": "ok"}
        cfg = client.get(f"{API}/config").json()
        assert cfg["demo_mode"] is True and cfg["payments_enabled"] is False
        err(client.get(f"{API}/wallet"), 401, "missing_token")
        err(client.get(f"{API}/wallet", headers=auth("garbage")), 401, "invalid_token")
        print("PASS health, public config, missing/garbage token rejected")

        login = client.post(f"{API}/auth/dev", json={"telegram_id": 9_500_000_000_000 + tag, "display_name": "Alice"})
        assert login.status_code == 200, login.text
        body = login.json()
        token = body["access_token"]
        assert body["new_user"] is True and body["wallet"]["available"]["units"] == str(grant)
        again = client.post(f"{API}/auth/dev", json={"telegram_id": 9_500_000_000_000 + tag, "display_name": "Alice"})
        assert again.json()["new_user"] is False
        err(client.post(f"{API}/auth/dev", json={"telegram_id": 5, "display_name": "x", "is_admin": True}), 422, "validation_error")
        print("PASS dev login creates a wallet with the signup grant; extra fields rejected")

        tg_id = 9_510_000_000_000 + tag
        fields = make_fields(user={"id": tg_id, "first_name": "Telegram", "username": "tg_user"})
        ok = client.post(f"{API}/auth/telegram", json={"init_data": sign(fields, BOT_TOKEN)})
        assert ok.status_code == 200 and ok.json()["user"]["username"] == "tg_user", ok.text
        err(client.post(f"{API}/auth/telegram", json={"init_data": sign(fields, "999:WRONG")}), 401, "initdata_invalid")
        print("PASS Telegram login verified; wrong signature rejected")

        admin_login = client.post(f"{API}/auth/dev", json={"telegram_id": ADMIN_TG, "display_name": "Boss"}).json()
        assert admin_login["user"]["is_admin"] is True
        assert body["user"]["is_admin"] is False
        print("PASS admin role only for ids listed in ADMIN_TELEGRAM_IDS")

        # ---- markets -------------------------------------------------------------------
        admin_id = admin_login["user"]["id"]
        db.execute(text("""insert into market_price_snapshots(asset_id, price, source, fetched_at)
                           select id, 100, 'test', now() from assets where symbol = 'SOL'"""))
        target = f"{(tag % 900000) / 1000 + 2000:.3f}"
        market = create_market(db, actor_id=uuid.UUID(admin_id), symbol="SOL", duration_seconds=86400,
                               target_price=target, reason="api test")
        mid = str(market["id"])

        listing = client.get(f"{API}/markets", params={"symbol": "sol", "status": "open", "limit": 100}).json()
        mine = [m for m in listing["items"] if m["id"] == mid]
        assert len(mine) == 1 and mine[0]["status"] == "open" and mine[0]["feed_ok"] is True
        assert mine[0]["payout_multiplier"] == "1.80" and mine[0]["max_stake"]["demo"] == "1000"
        assert mine[0]["target_price"] == target.rstrip("0").rstrip(".")
        assert client.get(f"{API}/markets/{mid}").json()["id"] == mid
        err(client.get(f"{API}/markets/{uuid.uuid4()}"), 404, "market_not_found")
        assert client.get(f"{API}/assets/SOL/chart", params={"range": "24h"}).status_code == 200
        err(client.get(f"{API}/assets/SOL/chart", params={"range": "5y"}), 422, "invalid_range")
        print("PASS public market list / detail / chart")

        # ---- predictions ---------------------------------------------------------------
        def predict(key, stake="25", direction="above", market_id=mid, tok=token, **extra):
            headers = auth(tok)
            if key is not None:
                headers["Idempotency-Key"] = key
            return client.post(f"{API}/predictions", headers=headers, json={
                "market_id": market_id, "direction": direction, "stake": stake, **extra})

        first = predict("api-key-0001", expected_target_price=target)
        assert first.status_code == 201, first.text
        p = first.json()
        assert p["stake"] == {"units": "25000000", "demo": "25"} and p["potential_payout"]["demo"] == "45"
        assert p["status"] == "open" and p["direction"] == "above"
        wallet = client.get(f"{API}/wallet", headers=auth(token)).json()
        assert wallet["available"]["units"] == str(grant - 25_000_000) and wallet["reserved"]["demo"] == "25"
        retry = predict("api-key-0001")
        assert retry.json()["id"] == p["id"]
        assert client.get(f"{API}/wallet", headers=auth(token)).json() == wallet
        print("PASS place prediction; retry with the same key does not take the stake twice")

        err(predict(None), 422, "invalid_key")
        err(predict("api-key-0002", stake="abc"), 422, "invalid_amount")
        err(predict("api-key-0003", stake="0.0000001"), 422, "invalid_amount")
        err(predict("api-key-0004", direction="up"), 422, "invalid_direction")
        err(predict("api-key-0005", stake="990"), 400, "insufficient_balance")
        err(predict("api-key-0006", stake="0.5"), 400, "stake_out_of_range")
        err(predict("api-key-0007", market_id=str(uuid.uuid4())), 404, "market_not_found")
        err(predict("api-key-0008", expected_target_price="1"), 409, "terms_mismatch")
        err(predict("api-key-0009", tok="garbage"), 401, "invalid_token")
        print("PASS bad input / balance / limits / terms / auth all rejected with clear codes")

        history = client.get(f"{API}/predictions", headers=auth(token)).json()["items"]
        assert [h["id"] for h in history] == [p["id"]]
        other = client.post(f"{API}/auth/dev", json={"telegram_id": 9_520_000_000_000 + tag}).json()["access_token"]
        assert client.get(f"{API}/predictions", headers=auth(other)).json()["items"] == []
        tx = client.get(f"{API}/wallet/transactions", headers=auth(token), params={"limit": 1}).json()
        assert tx["items"][0]["kind"] == "stake_reserve" and tx["next_cursor"] is not None
        assert tx["items"][0]["reserved_change"]["demo"] == "25"
        page2 = client.get(f"{API}/wallet/transactions", headers=auth(token),
                           params={"limit": 1, "before": tx["next_cursor"]}).json()
        assert page2["items"][0]["kind"] == "signup_grant" and page2["next_cursor"] is None
        print("PASS history is per-user; wallet transactions paginate")

        # ---- suspended account ---------------------------------------------------------
        victim = client.post(f"{API}/auth/dev", json={"telegram_id": 9_530_000_000_000 + tag}).json()
        db.execute(text("update users set status = 'suspended' where id = :i"), {"i": victim["user"]["id"]})
        err(client.get(f"{API}/wallet", headers=auth(victim["access_token"])), 403, "account_not_active")
        err(client.post(f"{API}/auth/dev", json={"telegram_id": 9_530_000_000_000 + tag}), 403, "account_not_active")
        print("PASS suspended account blocked immediately (token and login)")

        # ---- scheduler endpoint --------------------------------------------------------
        db.execute(text("update assets set provider_key = 'mock', provider_ref = symbol where symbol = 'SOL'"))
        mock.set_price("SOL", 100)
        err(client.post(f"{API}/internal/tick"), 401, "invalid_tick_secret")
        err(client.post(f"{API}/internal/tick", headers={"X-Tick-Secret": "x" * 40}), 401, "invalid_tick_secret")
        done = client.post(f"{API}/internal/tick", headers={"X-Tick-Secret": "s" * 40})
        assert done.status_code == 200 and done.json()["feed"]["SOL"] == "healthy", done.text
        print("PASS /internal/tick needs the secret and runs the worker")

        # ---- no money-in/out endpoints exist -------------------------------------------
        for path in ("deposit", "withdraw", "wallet/deposit", "wallet/withdraw", "payments"):
            assert client.post(f"{API}/{path}", headers=auth(token)).status_code in (404, 405)
        print("PASS no deposit / withdraw endpoints exist (demo mode)")

        app.dependency_overrides.clear()
        db.rollback()
    print("ALL API TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
