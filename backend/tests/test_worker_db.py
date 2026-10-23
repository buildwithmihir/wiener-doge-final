"""Database test for the price worker tick(). SAFE for a real Supabase project: one
transaction, rolled back at the end, nothing is saved. Uses the MOCK provider only
(no network). Test times are shifted 2 hours ahead so a live worker cannot interfere.

Run from the backend folder:
    python -m tests.test_worker_db
"""
import os
import sys
import uuid
from datetime import timedelta
from decimal import Decimal

os.environ.setdefault("JWT_SECRET", "t" * 48)
os.environ["APP_ENV"] = "development"      # the mock provider refuses production

from sqlalchemy import text

from app.database import check_db, session_scope
from app.providers.mock_provider import MockProvider
from app.providers.registry import ProviderRegistry
from app.services.markets import create_market, get_market, pause_market
from app.services.worker import tick


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        tag = uuid.uuid4().int % 10**12
        admin = db.execute(
            text("insert into users(telegram_id, display_name) values (:t, 'Worker Admin') returning id"),
            {"t": 9_400_000_000_000 + tag},
        ).scalar_one()

        db.execute(text("update assets set provider_key = 'mock', provider_ref = symbol where symbol = 'SOL'"))
        db.execute(text("update assets set provider_key = null where symbol <> 'SOL'"))   # others unpriced

        t0 = db.execute(text("select now()")).scalar_one() + timedelta(hours=2)
        clock = {"now": t0}
        mock = MockProvider(now_fn=lambda: clock["now"])
        registry = ProviderRegistry()
        registry.register(mock)

        latest = db.execute(text(
            "select s.price from market_price_snapshots s join assets a on a.id = s.asset_id "
            "where a.symbol = 'SOL' order by s.fetched_at desc limit 1")).scalar_one_or_none()
        base = Decimal(latest) if latest is not None else Decimal("100")
        mock.set_price("SOL", base)

        target = f"{(tag % 900000) / 1000 + 1000:.3f}"
        m1 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=86400, target_price=target, reason="w1")
        m2 = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=172800, target_price=target, reason="w2")
        pause_market(db, actor_id=admin, market_id=m2["id"], reason="admin maintenance")

        def run(minutes):
            clock["now"] = t0 + timedelta(minutes=minutes)
            return tick(db, registry, now=clock["now"])

        status = lambda m: get_market(db, m["id"], include_drafts=True)

        # 1) healthy tick stores a snapshot and records health; WIENER has no provider -> missing
        r = run(0)
        assert r["feed"]["SOL"] == "healthy" and r["snapshots"] == 1, r
        assert r["feed"]["WIENER"] == "missing", r
        assert status(m1)["status"] == "open"
        print("PASS healthy tick: snapshot stored, unpriced asset reported missing")

        # 2) a second tick 30s later does not call the provider again
        r = run(0.5)
        assert r["polled"] == [] and r["snapshots"] == 0, r
        print("PASS adaptive polling skips a fresh asset")

        # 3) provider outage pauses the open market with an auto: reason
        mock.fail_next()
        r = run(11)
        assert r["feed"]["SOL"] == "error" and r["paused"] >= 1, r
        s = status(m1)
        assert s["status"] == "paused" and s["pause_reason"].startswith("auto:"), s
        print("PASS provider outage -> market auto-paused")

        # 4) reopen only after 3 consecutive healthy checks
        run(22)
        assert status(m1)["status"] == "paused"
        run(33)
        assert status(m1)["status"] == "paused"
        r = run(44)
        assert status(m1)["status"] == "open" and r["reopened"] >= 1, r
        print("PASS reopened only after 3 consecutive healthy checks")

        # 5) admin pause is never reopened by the worker
        for k in (55, 66, 77, 88):
            run(k)
        s2 = status(m2)
        assert s2["status"] == "paused" and s2["pause_reason"] == "admin maintenance", s2
        print("PASS admin-paused market stays paused")

        # 6) abnormal jump pauses the market; the snapshot is stored but flagged
        mock.jump("SOL", 40)
        r = run(99)
        assert r["feed"]["SOL"] == "anomalous", r
        assert status(m1)["status"] == "paused"
        flagged = db.execute(text(
            "select count(*) from market_price_snapshots s join assets a on a.id = s.asset_id "
            "where a.symbol = 'SOL' and s.is_anomalous and s.source = 'mock'")).scalar_one()
        assert flagged == 1, flagged
        print("PASS abnormal jump -> paused, snapshot flagged anomalous")

        # 7) a stale source price pauses too
        mock.set_price("SOL", mock.jump("SOL", 0))
        mock.go_stale("SOL", 3600)
        r = run(110)
        assert r["feed"]["SOL"] == "stale", r
        print("PASS stale price detected")

        # 8) audit trail written by the system
        audits = db.execute(text(
            "select count(*) from audit_logs where entity_id = :m and actor_type = 'system'"),
            {"m": str(m1["id"])}).scalar_one()
        assert audits >= 3, audits           # pause, reopen, pause (at least)
        assert r["settlement"]["errors"] == 0, r
        print("PASS system actions audited; settlement step ran without errors")

        db.rollback()
    print("ALL WORKER DB TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
