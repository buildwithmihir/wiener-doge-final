"""Database test for notifications. SAFE for a real Supabase project: one transaction, rolled back.

Needs migrations 0001 and 0002. Run from the backend folder:
    python -m tests.test_notifications_db
"""
import os
import sys
import uuid

os.environ.setdefault("JWT_SECRET", "t" * 48)

from sqlalchemy import text

from app.database import check_db, session_scope
from app.services.markets import create_market
from app.services.notifications import (
    SendResult, deliver_pending, enqueue_results, get_preferences, run_notifications, update_preferences,
)
from app.services.predictions import place_prediction
from app.services.settlement import settle_due_markets

DEMO = 1_000_000


def new_user(db, base, tag, name):
    return db.execute(text("insert into users(telegram_id, display_name) values (:t, :n) returning id"),
                      {"t": base + tag, "n": name}).scalar_one()


def counts(db, uids):
    rows = db.execute(text("select status, count(*) from notifications where user_id = any(:u) group by status"),
                      {"u": list(uids)}).all()
    return {r[0]: r[1] for r in rows}


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1
    with session_scope() as db:
        tag = uuid.uuid4().int % 10**12
        admin = new_user(db, 9_700_000_000_000, tag, "N Admin")
        alice = new_user(db, 9_710_000_000_000, tag, "Alice")
        bob = new_user(db, 9_720_000_000_000, tag, "Bob")
        carol = new_user(db, 9_730_000_000_000, tag, "Carol")
        users = [alice, bob, carol]
        tg = {u: db.execute(text("select telegram_id from users where id=:u"), {"u": u}).scalar_one() for u in users}

        db.execute(text("""insert into market_price_snapshots(asset_id, price, source, fetched_at)
                           select id, 100, 'test', now() from assets where symbol='SOL'"""))
        target = f"{(tag % 900000) / 1000 + 1000:.3f}"
        m = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=86400, target_price=target, reason="notif")
        for u, d, key in ((alice, "above", "n-alice-key1"), (bob, "below", "n-bob-key001"), (carol, "above", "n-carol-key1")):
            place_prediction(db, user_id=u, market_id=m["id"], direction=d, stake_units=10 * DEMO, idempotency_key=key)
        update_preferences(db, carol, {"market_results": False})
        assert get_preferences(db, carol) == {"market_results": False, "market_closing": True, "referrals": True, "vip": True}
        assert get_preferences(db, alice)["market_results"] is True

        assert enqueue_results(db) == 0                       # nothing settled yet
        db.execute(text("alter table markets disable trigger trg_markets_guard"))
        db.execute(text("""update markets set opens_at = now() - interval '4 days',
                           betting_closes_at = now() - interval '2 hours', closes_at = now() - interval '1 hour' where id=:m"""), {"m": m["id"]})
        db.execute(text("alter table markets enable trigger trg_markets_guard"))
        db.execute(text("""insert into market_price_snapshots(asset_id, price, source, fetched_at)
                           select id, 1000, 'test', (select closes_at from markets where id=:m) + interval '60 seconds'
                           from assets where symbol='SOL'"""), {"m": m["id"]})
        assert settle_due_markets(db)["settled"] == 1
        print("PASS setup: market settled with 3 predictions")

        made = enqueue_results(db)
        assert made == 2, made                                 # Carol switched results off
        assert enqueue_results(db) == 0                        # idempotent: same events never queue twice
        assert counts(db, users) == {"pending": 2}
        print("PASS results queued once each; Carol's opt-out respected")

        sent = []

        def good(chat_id, body):
            sent.append((chat_id, body))
            return SendResult.SENT

        out = deliver_pending(db, good)
        assert out == {"sent": 2, "retry": 0, "failed": 0}, out
        assert {c for c, _ in sent} == {tg[alice], tg[bob]}
        assert all("demo credits" in b and "$" not in b for _, b in sent)
        assert counts(db, users) == {"sent": 2}
        assert deliver_pending(db, good) == {"sent": 0, "retry": 0, "failed": 0} and len(sent) == 2   # no resend
        print("PASS delivered once, nothing resent")

        # retry -> failed after 3 attempts; permanent failure stops at once; budget stops a batch
        db.execute(text("""insert into notifications(user_id, type, title, body, dedupe_key) values
            (:a,'market_result','t','b1','t:1'), (:b,'market_result','t','b2','t:2')"""), {"a": alice, "b": bob})
        flaky = lambda c, b: SendResult.RETRY if c == tg[alice] else SendResult.PERMANENT
        r1 = deliver_pending(db, flaky)
        assert r1 == {"sent": 0, "retry": 1, "failed": 1}, r1
        deliver_pending(db, flaky)
        r3 = deliver_pending(db, flaky)
        assert r3 == {"sent": 0, "retry": 0, "failed": 1}, r3
        assert counts(db, [alice, bob]).get("pending", 0) == 0
        raising = lambda c, b: (_ for _ in ()).throw(RuntimeError("boom"))
        db.execute(text("insert into notifications(user_id, type, title, body, dedupe_key) values (:a,'market_result','t','b3','t:3')"), {"a": alice})
        assert deliver_pending(db, raising)["retry"] == 1      # a crashing sender is just a retry
        ticks = iter([0.0, 100.0, 200.0])
        db.execute(text("insert into notifications(user_id, type, title, body, dedupe_key) values (:a,'market_result','t','b4','t:4'),(:b,'market_result','t','b5','t:5')"), {"a": bob, "b": bob})
        slow = deliver_pending(db, good, budget_seconds=5, clock=lambda: next(ticks))
        assert slow["sent"] <= 1, slow                          # over budget: the rest wait for the next tick
        print("PASS retry limit, permanent failure, crashing sender, time budget")

        summary = run_notifications(db, None)                   # no bot token: enqueue only, never crashes
        assert "deliver_error" not in summary and "enqueue_error" not in summary
        db.rollback()
    print("ALL NOTIFICATION DB TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
