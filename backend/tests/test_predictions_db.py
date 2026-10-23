"""Database test for predictions + settlement. SAFE for a real Supabase project: one
transaction, rolled back at the end, nothing is saved.

Note: it briefly disables the markets guard trigger INSIDE the transaction to move a test
market's times into the past (so it can be settled). That is rolled back too.

Run from the backend folder:
    python -m tests.test_predictions_db
"""
import os
import sys
import uuid

os.environ.setdefault("JWT_SECRET", "t" * 48)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError, NotFound, translate_db_error
from app.database import check_db, session_scope
from app.services.ledger import get_wallet, run_reconciliation
from app.services.markets import create_market
from app.services.predictions import get_prediction, list_predictions, place_prediction
from app.services.settlement import settle_due_markets, void_market_admin

DEMO = 1_000_000


def expect_db_error(code, func, db):
    try:
        with db.begin_nested():
            func()
    except DBAPIError as exc:
        mapped = translate_db_error(exc)
        assert mapped is not None and mapped.code == code, mapped
        return
    except AppError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError(f"expected {code}")


def new_user(db, base, tag, name):
    return db.execute(
        text("insert into users(telegram_id, display_name) values (:t, :n) returning id"),
        {"t": base + tag, "n": name},
    ).scalar_one()


def snapshot(db, symbol, price, fetched_sql, stale=False):
    db.execute(
        text(f"""insert into market_price_snapshots(asset_id, price, source, fetched_at, is_stale)
                 select id, cast(:p as numeric), 'test', {fetched_sql}, :s from assets where symbol = :sym"""),
        {"p": price, "s": stale, "sym": symbol},
    )


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        tag = uuid.uuid4().int % 10**12
        admin = new_user(db, 9_300_000_000_000, tag, "Pred Admin")
        alice = new_user(db, 9_310_000_000_000, tag, "Alice")
        bob = new_user(db, 9_320_000_000_000, tag, "Bob")
        grant = int(db.execute(text("select wd_setting_int('wallet.signup_grant', 0)")).scalar_one())

        snapshot(db, "SOL", "100", "now()")                       # fresh price -> feed ok for SOL
        target = f"{(tag % 900000) / 1000 + 1000:.3f}"
        m1 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=86400, target_price=target, reason="t1")
        m2 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=172800, target_price=target, reason="t2")
        m3 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=604800, target_price=target, reason="t3")
        m4 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=2592000, target_price=target, reason="t4")

        # ---- placing -------------------------------------------------------------------
        p = place_prediction(db, user_id=alice, market_id=m1["id"], direction="above",
                             stake_units=10 * DEMO, idempotency_key="alice-m1-key1",
                             expected_target_price=target)
        assert p["status"] == "open" and p["stake"] == 10 * DEMO and p["potential_payout"] == 18 * DEMO
        again = place_prediction(db, user_id=alice, market_id=m1["id"], direction="above",
                                 stake_units=10 * DEMO, idempotency_key="alice-m1-key1")
        assert again["id"] == p["id"]
        w = get_wallet(db, alice)
        assert (w.available, w.reserved) == (grant - 10 * DEMO, 10 * DEMO), w
        print("PASS place prediction, stake reserved, retry is idempotent")

        b = place_prediction(db, user_id=bob, market_id=m1["id"], direction="below",
                             stake_units=10 * DEMO, idempotency_key="bob-m1-key001")
        place_prediction(db, user_id=alice, market_id=m2["id"], direction="above",
                         stake_units=10 * DEMO, idempotency_key="alice-m2-key1")
        place_prediction(db, user_id=bob, market_id=m3["id"], direction="below",
                         stake_units=7 * DEMO, idempotency_key="bob-m3-key001")
        place_prediction(db, user_id=bob, market_id=m4["id"], direction="below",
                         stake_units=3 * DEMO, idempotency_key="bob-m4-key001")

        expect_db_error("terms_mismatch", lambda: place_prediction(
            db, user_id=bob, market_id=m1["id"], direction="above", stake_units=DEMO,
            idempotency_key="bob-m1-key002", expected_target_price="1.5"), db)
        expect_db_error("insufficient_balance", lambda: place_prediction(
            db, user_id=bob, market_id=m1["id"], direction="above", stake_units=990 * DEMO,
            idempotency_key="bob-m1-key003"), db)
        expect_db_error("stake_out_of_range", lambda: place_prediction(
            db, user_id=bob, market_id=m1["id"], direction="above", stake_units=1,
            idempotency_key="bob-m1-key004"), db)
        expect_db_error("invalid_direction", lambda: place_prediction(
            db, user_id=bob, market_id=m1["id"], direction="up", stake_units=DEMO,
            idempotency_key="bob-m1-key005"), db)
        expect_db_error("market_not_found", lambda: place_prediction(
            db, user_id=bob, market_id=uuid.uuid4(), direction="above", stake_units=DEMO,
            idempotency_key="bob-m1-key006"), db)
        print("PASS terms mismatch / balance / stake / direction / unknown market rejected")

        # unhealthy feed blocks new predictions (WIENER gets a stale-only price)
        wm = create_market(db, actor_id=admin, symbol="WIENER", duration_seconds=86400,
                           target_price="0.0001", reason="feed test")
        snapshot(db, "WIENER", "0.0001", "now()", stale=True)
        expect_db_error("price_unavailable", lambda: place_prediction(
            db, user_id=bob, market_id=wm["id"], direction="above", stake_units=DEMO,
            idempotency_key="bob-wm-key001"), db)
        print("PASS unhealthy feed blocks new predictions")

        mine = list_predictions(db, alice)
        # (inside one transaction every created_at is identical, so only the set is checked here)
        assert {x["market_id"] for x in mine} == {m2["id"], m1["id"]} and len(mine) == 2
        assert [x["status"] for x in list_predictions(db, alice, status="won")] == []
        try:
            get_prediction(db, bob, p["id"])        # Alice's prediction, asked as Bob
        except NotFound:
            pass
        else:
            raise AssertionError("saw someone else's prediction")
        print("PASS history, status filter, other users' predictions hidden")

        # ---- settlement ----------------------------------------------------------------
        # move markets into the past (guard trigger off inside this transaction only)
        db.execute(text("alter table markets disable trigger trg_markets_guard"))
        for mid, closes_ago in ((m1["id"], "1 hour"), (m2["id"], "10 minutes"), (m3["id"], "2 hours")):
            db.execute(
                text(f"""update markets set opens_at = now() - interval '4 days',
                         betting_closes_at = now() - interval '{closes_ago}' - interval '1 hour',
                         closes_at = now() - interval '{closes_ago}' where id = :m"""),
                {"m": mid},
            )
        db.execute(text("alter table markets enable trigger trg_markets_guard"))

        snapshot(db, "SOL", "1000", f"(select closes_at from markets where id = '{m1['id']}') + interval '60 seconds'")
        # m2: only a STALE snapshot after close -> must stay pending
        snapshot(db, "SOL", "1", f"(select closes_at from markets where id = '{m2['id']}') + interval '30 seconds'", stale=True)
        # m3: nothing at all, and overdue (closed 2h ago, void window 1h) -> voided + refunded

        # the void window is a setting (6h by default); pin it to 1h for this test, inside the transaction only
        db.execute(text("update application_settings set value = to_jsonb(3600) where key = 'settlement.void_after_seconds'"))
        result = settle_due_markets(db)
        assert result["errors"] == 0, result
        status = lambda mid: db.execute(text("select status from markets where id = :m"), {"m": mid}).scalar_one()
        assert status(m1["id"]) == "settled" and status(m2["id"]) == "closed" and status(m3["id"]) == "voided"
        print("PASS settled / left pending (stale only) / voided (no price, overdue)")

        # m1: price 1000 vs target ~1000.xxx -> decide from the real numbers
        res = db.execute(text("select result, settle_price from settlements where market_id = :m"), {"m": m1["id"]}).one()
        expected = "above" if res.settle_price >= db.execute(text("select target_price from markets where id = :m"), {"m": m1["id"]}).scalar_one() else "below"
        assert res.result == expected
        a1, b1 = get_prediction(db, alice, p["id"]), get_prediction(db, bob, b["id"])
        winner, loser = (a1, b1) if expected == "above" else (b1, a1)
        assert winner["status"] == "won" and winner["payout_amount"] == 18 * DEMO
        assert loser["status"] == "lost" and loser["payout_amount"] == 0
        print(f"PASS winner paid 1.8x, loser forfeits (result: {expected})")

        wb = get_wallet(db, bob)      # m3 refunded, m4 still open, m1 settled
        bob_pnl_m1 = 8 * DEMO if expected == "below" else -10 * DEMO
        assert wb.total == grant + bob_pnl_m1, wb
        assert wb.reserved == 3 * DEMO + 0 and wb.reserved == 3 * DEMO, wb       # only m4 still reserved
        print("PASS refund returned to wallet, open stake still reserved")

        settle_due_markets(db)
        assert status(m1["id"]) == "settled" and status(m2["id"]) == "closed"
        wb2 = get_wallet(db, bob)
        assert wb2 == wb, (wb, wb2)
        print("PASS second settlement run changes nothing (idempotent)")

        admin_void = void_market_admin(db, actor_id=admin, market_id=m4["id"], reason="test void")
        assert admin_void["result"] == "void" and admin_void["predictions_settled"] == 1
        assert get_wallet(db, bob).reserved == 0
        try:
            void_market_admin(db, actor_id=admin, market_id=m4["id"], reason="  ")
        except AppError as exc:
            assert exc.code == "reason_required"
        else:
            raise AssertionError("void without reason accepted")
        print("PASS admin void refunds; reason required")

        issues = run_reconciliation(db)
        assert issues == [], issues
        print("PASS ledger reconciliation clean")

        db.rollback()
    print("ALL PREDICTION + SETTLEMENT DB TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
