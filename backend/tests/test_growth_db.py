"""API test for VIP tiers, referrals, leaderboard and profile settings. SAFE for a real Supabase
project: everything runs in ONE outer transaction that is rolled back at the end.

Needs migrations 0001 AND 0002 applied. Run from the backend folder:
    python -m tests.test_growth_db
"""
import os
import sys
import uuid

os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"
os.environ["DEV_AUTH_ENABLED"] = "true"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:TEST_TOKEN"
os.environ["TICK_SECRET"] = "s" * 40
os.environ["LOG_LEVEL"] = "WARNING"
ADMIN_TG = 9_699_000_000_001
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


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        if db.execute(text("select to_regproc('update_vip')")).scalar_one() is None:
            print("FAILED: migration 0002_growth_functions.sql is not applied on this database.")
            return 1

        def override_get_db():
            with db.begin_nested():
                yield db

        registry = ProviderRegistry()
        registry.register(MockProvider())
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

        def login(offset, name):
            r = client.post(f"{API}/auth/dev", json={"telegram_id": 9_600_000_000_000 + tag * 10 + offset, "display_name": name})
            assert r.status_code == 200, r.text
            j = r.json()
            return j["access_token"], j["user"]["id"]

        def H(tok, key=None):
            h = {"Authorization": f"Bearer {tok}"}
            if key:
                h["Idempotency-Key"] = key
            return h

        err(client.get(f"{API}/vip"), 401, "missing_token")
        err(client.get(f"{API}/leaderboard"), 401, "missing_token")

        alice, alice_id = login(1, "Alice Wonder")
        bob, bob_id = login(2, "Bob")
        carol, carol_id = login(3, "Carol")
        dave, dave_id = login(4, "Dave")
        admin = client.post(f"{API}/auth/dev", json={"telegram_id": ADMIN_TG, "display_name": "Boss"}).json()

        # ---- profile + referral code ----------------------------------------------------
        pa = client.get(f"{API}/profile", headers=H(alice)).json()
        code_a = pa["referral"]["code"]
        assert len(code_a) == 8 and code_a.isalnum() and code_a == code_a.upper()
        assert client.get(f"{API}/profile", headers=H(alice)).json()["referral"]["code"] == code_a   # stable
        assert pa["stats"]["settled"] == 0 and pa["stats"]["accuracy_pct"] is None
        assert pa["vip"]["current"] is None and pa["user"]["display_name"] == "Alice Wonder"
        print("PASS profile returns a stable referral code and empty stats")

        # ---- VIP ladder -----------------------------------------------------------------
        vip = client.get(f"{API}/vip", headers=H(alice)).json()
        names = [t["name"] for t in vip["tiers"]]
        assert names == ["Bronze", "Silver", "Gold", "Platinum"], names
        assert vip["current"] is None and vip["next"]["name"] == "Bronze"
        assert vip["total_staked"]["units"] == "0" and vip["remaining_to_next"]["demo"] == "500"
        print("PASS VIP ladder: 4 tiers, next=Bronze, 500 DEMO to go")

        # ---- referral rules -------------------------------------------------------------
        err(client.post(f"{API}/referrals/apply", headers=H(alice), json={"code": code_a}), 400, "self_referral")
        err(client.post(f"{API}/referrals/apply", headers=H(bob), json={"code": "ZZZZZZZZ"}), 404, "invalid_code")
        err(client.post(f"{API}/referrals/apply", headers=H(bob), json={"code": "x!"}), 404, "invalid_code")
        err(client.post(f"{API}/referrals/apply", headers=H(bob), json={"code": code_a, "extra": 1}), 422, "validation_error")
        ok = client.post(f"{API}/referrals/apply", headers=H(bob), json={"code": code_a.lower()})
        assert ok.status_code == 201 and ok.json() == {"applied": True}, ok.text
        err(client.post(f"{API}/referrals/apply", headers=H(bob), json={"code": code_a}), 409, "already_referred")
        pb = client.get(f"{API}/profile", headers=H(bob)).json()
        assert pb["referral"]["already_referred"] is True
        pa = client.get(f"{API}/profile", headers=H(alice)).json()
        assert pa["referral"]["total"] == 1 and pa["referral"]["pending"] == 1 and pa["referral"]["rewarded"] == 0
        # circular: Dave joins through Carol, then Carol tries Dave's code
        code_c = client.get(f"{API}/profile", headers=H(carol)).json()["referral"]["code"]
        code_d = client.get(f"{API}/profile", headers=H(dave)).json()["referral"]["code"]
        assert client.post(f"{API}/referrals/apply", headers=H(dave), json={"code": code_c}).status_code == 201
        err(client.post(f"{API}/referrals/apply", headers=H(carol), json={"code": code_d}), 400, "circular_referral")
        print("PASS referral rules: self / invalid / duplicate / circular rejected; valid code accepted (pending)")

        # ---- a market to bet on ---------------------------------------------------------
        db.execute(text("""insert into market_price_snapshots(asset_id, price, source, fetched_at)
                           select id, 100, 'test', now() from assets where symbol = 'SOL'"""))
        target = f"{(tag % 900000) / 1000 + 3000:.3f}"
        market = create_market(db, actor_id=uuid.UUID(admin["user"]["id"]), symbol="SOL", duration_seconds=86400,
                               target_price=target, reason="growth test")
        mid = str(market["id"])

        def predict(tok, key, stake):
            return client.post(f"{API}/predictions", headers=H(tok, key),
                               json={"market_id": mid, "direction": "above", "stake": stake})

        # already played -> cannot join late
        assert predict(carol, "growth-test-carol-1", "5").status_code == 201
        err(client.post(f"{API}/referrals/apply", headers=H(carol), json={"code": code_a}), 409, "too_late_existing_user")

        # ---- VIP unlock + one-time reward ----------------------------------------------
        before = client.get(f"{API}/wallet", headers=H(alice)).json()
        assert before["total"]["units"] == str(grant)
        assert predict(alice, "growth-test-alice-1", "400").status_code == 201
        assert client.get(f"{API}/vip", headers=H(alice)).json()["current"] is None       # 400 < 500
        assert predict(alice, "growth-test-alice-2", "100").status_code == 201                      # total 500
        vip = client.get(f"{API}/vip", headers=H(alice)).json()
        assert vip["current"]["name"] == "Bronze" and vip["current"]["reward_paid"] is True
        assert vip["next"]["name"] == "Silver" and vip["remaining_to_next"]["demo"] == "1500", vip["remaining_to_next"]
        w = client.get(f"{API}/wallet", headers=H(alice)).json()
        assert w["total"]["units"] == str(grant + 5_000_000), w          # +5 DEMO Bronze reward, minted via the ledger
        client.get(f"{API}/vip", headers=H(alice))
        assert client.get(f"{API}/wallet", headers=H(alice)).json() == w  # reward never paid twice
        print("PASS VIP: Bronze unlocks at exactly 500 staked, +5 DEMO paid once")

        # ---- referral reward after the referred user plays -----------------------------
        assert db.execute(text("select process_referral_rewards()")).scalar_one() >= 0   # Bob has not played: still pending
        pa = client.get(f"{API}/profile", headers=H(alice)).json()
        assert pa["referral"]["pending"] == 1
        wal = client.get(f"{API}/wallet", headers=H(alice)).json()["total"]["units"]
        _r = predict(bob, "growth-test-bob-1", "5"); assert _r.status_code == 201, _r.text
        db.execute(text("select process_referral_rewards()"))
        db.execute(text("select process_referral_rewards()"))            # twice: must not double pay
        pa = client.get(f"{API}/profile", headers=H(alice)).json()
        reward = int(pa["referral"]["reward_per_referral"]["units"])
        assert pa["referral"]["rewarded"] == 1 and pa["referral"]["pending"] == 0
        assert pa["referral"]["earned"]["units"] == str(reward)
        assert client.get(f"{API}/wallet", headers=H(alice)).json()["total"]["units"] == str(int(wal) + reward)
        print(f"PASS referral reward paid once after the referred user predicted (+{reward // 1_000_000} DEMO)")

        # ---- ledger still balances ------------------------------------------------------
        bad = db.execute(text("select count(*) from ledger_reconcile()")).scalar_one()
        assert bad == 0, f"ledger_reconcile found {bad} problems"
        print("PASS ledger_reconcile() is empty after VIP + referral rewards")

        # ---- leaderboard ----------------------------------------------------------------
        err(client.get(f"{API}/leaderboard", headers=H(alice), params={"metric": "luck"}), 422, "invalid_metric")
        err(client.get(f"{API}/leaderboard", headers=H(alice), params={"period": "year"}), 422, "invalid_period")
        lb = client.get(f"{API}/leaderboard", headers=H(alice), params={"metric": "wagered"}).json()
        me = lb["me"]
        assert me is not None and me["is_me"] and me["alias"] == "Alice" and me["staked"]["units"] == "500000000", me
        assert [i["rank"] for i in lb["items"]] == sorted(i["rank"] for i in lb["items"])
        assert all("user_id" not in i for i in lb["items"])                 # no internal ids leak
        assert client.get(f"{API}/leaderboard", headers=H(bob), params={"metric": "wagered"}).json()["me"]["is_me"]
        acc = client.get(f"{API}/leaderboard", headers=H(alice), params={"metric": "accuracy"}).json()
        assert acc["me"] is None                                            # nothing settled yet
        print("PASS leaderboard: Alice ranked by wagered with first-name alias; no internal ids; accuracy needs settled bets")

        # ---- privacy settings -----------------------------------------------------------
        r = client.patch(f"{API}/profile", headers=H(alice), json={"leaderboard_alias": "  DogeKing  "})
        assert r.json() == {"leaderboard_alias": "DogeKing", "hide_on_leaderboard": False}, r.text
        lb = client.get(f"{API}/leaderboard", headers=H(bob), params={"metric": "wagered"}).json()
        assert any(i["alias"] == "DogeKing" for i in lb["items"]) or lb["me"] is not None
        err(client.patch(f"{API}/profile", headers=H(alice), json={"leaderboard_alias": "x" * 40}), 422, "invalid_alias")
        err(client.patch(f"{API}/profile", headers=H(alice), json={"is_admin": True}), 422, "validation_error")
        r = client.patch(f"{API}/profile", headers=H(alice), json={"hide_on_leaderboard": True})
        assert r.json()["hide_on_leaderboard"] is True and r.json()["leaderboard_alias"] == "DogeKing"   # alias untouched
        lb = client.get(f"{API}/leaderboard", headers=H(alice), params={"metric": "wagered"}).json()
        assert lb["me"] is None and all(not i["is_me"] for i in lb["items"])
        r = client.patch(f"{API}/profile", headers=H(alice), json={"leaderboard_alias": None, "hide_on_leaderboard": False})
        assert r.json() == {"leaderboard_alias": None, "hide_on_leaderboard": False}
        print("PASS privacy: alias trimmed/cleared, hide removes you from the board, unknown fields rejected")

        # ---- no stray endpoints for payments --------------------------------------------
        assert client.post(f"{API}/vip/claim", headers=H(alice)).status_code in (404, 405)

        # ---- notification preferences ---------------------------------------------------
        err(client.get(f"{API}/notifications/preferences"), 401, "missing_token")
        assert client.get(f"{API}/notifications/preferences", headers=H(alice)).json() == {
            "market_results": True, "market_closing": True, "referrals": True, "vip": True}
        off = client.patch(f"{API}/notifications/preferences", headers=H(alice), json={"market_results": False})
        assert off.status_code == 200 and off.json()["market_results"] is False and off.json()["vip"] is True, off.text
        assert client.get(f"{API}/notifications/preferences", headers=H(alice)).json()["market_results"] is False
        err(client.patch(f"{API}/notifications/preferences", headers=H(alice), json={"bogus": True}), 422, "validation_error")
        print("PASS notification preferences: default on, opt out per type, unknown fields rejected")

        db.rollback()

    print("\nALL GROWTH TESTS PASSED (rolled back, nothing saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
