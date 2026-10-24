"""Admin API end-to-end test. SAFE for a real Supabase project: everything runs in ONE
transaction (each request in a savepoint) that is rolled back at the end.

Run from the backend folder:
    python -m tests.test_admin_api_db
"""
import os
import sys
import uuid

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"
ADMIN_TG = 9_599_000_000_002
os.environ["ADMIN_TELEGRAM_IDS"] = str(ADMIN_TG)

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.rate_limit import limiter
from app.database import check_db, get_db, session_scope
from app.main import app


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
        API = "/api/v1"
        tag = uuid.uuid4().int % 10**9
        grant = int(db.execute(text("select wd_setting_int('wallet.signup_grant', 0)")).scalar_one())

        def err(resp, status, code):
            assert resp.status_code == status, (resp.status_code, resp.text)
            assert resp.json()["error"]["code"] == code, resp.json()

        def login(tg_id, name="User"):
            r = client.post(f"{API}/auth/dev", json={"telegram_id": tg_id, "display_name": name})
            assert r.status_code == 200, r.text
            return r.json()

        H = lambda t: {"Authorization": f"Bearer {t['access_token']}"}
        admin = login(ADMIN_TG, "Boss")
        user = login(9_600_000_000_000 + tag, "Plain")
        mod = login(9_610_000_000_000 + tag, "Mod")
        db.execute(text("insert into user_roles(user_id, role) values (:u, 'moderator')"), {"u": mod["user"]["id"]})

        # ---- who may call what -----------------------------------------------------------
        err(client.get(f"{API}/admin/audit"), 401, "missing_token")
        for method, path in (("get", "/admin/audit"), ("get", "/admin/reconcile"), ("get", "/admin/markets"),
                             ("post", "/admin/markets"), ("get", "/admin/users/lookup?telegram_id=5")):
            r = getattr(client, method)(f"{API}{path}", headers=H(user), **({"json": {}} if method == "post" else {}))
            assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden", (path, r.status_code, r.text)
        assert client.get(f"{API}/admin/markets", headers=H(mod)).status_code == 200          # moderator: read
        err(client.get(f"{API}/admin/audit", headers=H(mod)), 403, "forbidden")               # but not audit
        print("PASS normal users and moderators are limited; admin-only endpoints enforced")

        # ---- market create ---------------------------------------------------------------
        db.execute(text("""insert into market_price_snapshots(asset_id, price, source, fetched_at)
                           select id, 100, 'test', now() from assets where symbol = 'SOL'"""))
        target = f"{(tag % 900000) / 1000 + 3000:.3f}"
        body = {"symbol": "sol", "duration_seconds": 86400, "target_price": target, "reason": "admin test"}
        created = client.post(f"{API}/admin/markets", headers=H(admin), json=body)
        assert created.status_code == 201, created.text
        mid = created.json()["id"]
        assert created.json()["status"] == "open" and created.json()["symbol"] == "SOL"
        err(client.post(f"{API}/admin/markets", headers=H(admin), json={**body, "duration_seconds": 3600}), 422, "invalid_duration")
        err(client.post(f"{API}/admin/markets", headers=H(admin), json={**body, "symbol": "USDC"}), 422, "asset_not_supported")
        err(client.post(f"{API}/admin/markets", headers=H(admin), json={**body, "target_price": "-5"}), 422, "invalid_target_price")
        err(client.post(f"{API}/admin/markets", headers=H(admin), json={**body, "reason": ""}), 422, "validation_error")
        err(client.post(f"{API}/admin/markets", headers=H(admin), json={**body, "extra": 1}), 422, "validation_error")
        draft = client.post(f"{API}/admin/markets", headers=H(admin),
                            json={**body, "duration_seconds": 172800, "publish": False, "max_stake": "50"}).json()
        assert draft["status"] == "draft" and draft["max_stake"]["demo"] == "50"
        assert draft["id"] in [m["id"] for m in client.get(f"{API}/admin/markets", headers=H(admin)).json()["items"]]
        assert draft["id"] not in [m["id"] for m in client.get(f"{API}/markets", params={"limit": 100}).json()["items"]]
        err(client.get(f"{API}/markets/{draft['id']}"), 404, "market_not_found")
        print("PASS admin creates markets with validation; drafts stay hidden from the public")

        # ---- pause / resume --------------------------------------------------------------
        err(client.post(f"{API}/admin/markets/{mid}/pause", headers=H(mod), json={"reason": "auto:fake"}), 422, "invalid_reason")
        paused = client.post(f"{API}/admin/markets/{mid}/pause", headers=H(mod), json={"reason": "checking feed"})
        assert paused.status_code == 200 and paused.json()["status"] == "paused" and paused.json()["pause_reason"] == "checking feed"
        err(client.post(f"{API}/admin/markets/{mid}/pause", headers=H(mod), json={"reason": "again"}), 409, "illegal_market_transition")
        resumed = client.post(f"{API}/admin/markets/{mid}/resume", headers=H(mod), json={"reason": "ok now"})
        assert resumed.json()["status"] == "open"
        err(client.post(f"{API}/admin/markets/{mid}/void", headers=H(mod), json={"reason": "x"}), 403, "forbidden")
        err(client.post(f"{API}/admin/markets/ladder", headers=H(mod),
                        json={"symbol": "SOL", "durations": [{"duration_seconds": 86400}], "reason": "x"}), 403, "forbidden")
        print("PASS moderator can pause/resume (not void); system-only reason prefix refused")

        # ---- demo credits ----------------------------------------------------------------
        uid = user["user"]["id"]
        def adjust(amount, key, reason="goodwill"):
            headers = H(admin)
            if key:
                headers["Idempotency-Key"] = key
            return client.post(f"{API}/admin/users/{uid}/credits", headers=headers, json={"amount": amount, "reason": reason})

        r = adjust("50", "credit-key-0001")
        assert r.status_code == 200 and r.json()["wallet"]["total"]["units"] == str(grant + 50_000_000), r.text
        adjust("50", "credit-key-0001")
        assert client.get(f"{API}/wallet", headers=H(user)).json()["total"]["units"] == str(grant + 50_000_000)
        err(adjust("-100000", "credit-key-0002"), 400, "insufficient_balance")
        err(adjust("50", None), 422, "invalid_key")
        err(adjust("2000000", "credit-key-0003"), 422, "invalid_amount")
        err(adjust("0", "credit-key-0004"), 422, "invalid_amount")
        err(adjust("abc", "credit-key-0005"), 422, "invalid_amount")
        feed = client.get(f"{API}/wallet/transactions", headers=H(user)).json()["items"]
        assert feed[0]["title"] == "Balance adjustment by admin" and "goodwill" not in str(feed)
        print("PASS credit adjustment: once per key, never below zero, reason not shown to the user")

        # ---- user status -----------------------------------------------------------------
        err(client.post(f"{API}/admin/users/{admin['user']['id']}/status", headers=H(admin),
                        json={"status": "banned", "reason": "oops"}), 409, "cannot_lock_self")
        err(client.post(f"{API}/admin/users/{uid}/status", headers=H(admin), json={"status": "weird", "reason": "x"}), 422, "invalid_status")
        err(client.post(f"{API}/admin/users/{uuid.uuid4()}/status", headers=H(admin), json={"status": "banned", "reason": "x"}), 404, "user_not_found")
        ok = client.post(f"{API}/admin/users/{uid}/status", headers=H(admin), json={"status": "suspended", "reason": "abuse report"})
        assert ok.json()["previous_status"] == "active"
        err(client.get(f"{API}/wallet", headers=H(user)), 403, "account_not_active")
        client.post(f"{API}/admin/users/{uid}/status", headers=H(admin), json={"status": "active", "reason": "cleared"})
        assert client.get(f"{API}/wallet", headers=H(user)).status_code == 200
        found = client.get(f"{API}/admin/users/lookup", headers=H(admin), params={"telegram_id": 9_600_000_000_000 + tag})
        assert found.json()["id"] == uid and found.json()["wallet"]["total"]["demo"]
        err(client.get(f"{API}/admin/users/lookup", headers=H(admin), params={"telegram_id": 12345}), 404, "user_not_found")
        print("PASS suspend / reactivate / lookup; admins cannot lock themselves out")

        # ---- void refunds ----------------------------------------------------------------
        before = client.get(f"{API}/wallet", headers=H(user)).json()
        pred = client.post(f"{API}/predictions", headers={**H(user), "Idempotency-Key": "void-test-0001"},
                           json={"market_id": mid, "direction": "below", "stake": "20"})
        assert pred.status_code == 201, pred.text
        assert client.get(f"{API}/wallet", headers=H(user)).json()["reserved"]["demo"] == "20"
        err(client.post(f"{API}/admin/markets/{mid}/void", headers=H(admin), json={"reason": "  "}), 422, "reason_required")
        v = client.post(f"{API}/admin/markets/{mid}/void", headers=H(admin), json={"reason": "bad target price"})
        assert v.status_code == 200 and v.json() == {"market_id": mid, "result": "void", "refunded_predictions": 1}, v.text
        assert client.get(f"{API}/wallet", headers=H(user)).json() == before
        assert client.get(f"{API}/predictions", headers=H(user)).json()["items"][0]["status"] == "refunded"
        print("PASS void refunds every stake; wallet back to where it was")

        # ---- reconcile + audit -----------------------------------------------------------
        assert client.get(f"{API}/admin/reconcile", headers=H(admin)).json() == {"ok": True, "issues": []}
        log = client.get(f"{API}/admin/audit", headers=H(admin), params={"limit": 100}).json()
        actions = {i["action"] for i in log["items"]}
        assert {"market.create", "market.pause", "market.resume", "market.void", "user.set_status"} <= actions, actions
        small = client.get(f"{API}/admin/audit", headers=H(admin), params={"limit": 2}).json()
        assert len(small["items"]) == 2 and small["next_cursor"] is not None
        print("PASS reconciliation clean; every admin action is in the audit log")

        app.dependency_overrides.clear()
        db.rollback()
    print("ALL ADMIN API TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
