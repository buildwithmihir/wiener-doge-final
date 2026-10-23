"""Database test for the markets service. SAFE for a real Supabase project: everything
runs in ONE transaction that is rolled back at the end, so nothing is saved.

Needs DATABASE_URL in backend/.env (migration applied).
Run from the backend folder:
    python -m tests.test_markets_db
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "t" * 48)

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import AppError, NotFound, translate_db_error
from app.database import check_db, session_scope
from app.services.markets import (
    create_market, get_market, list_markets, pause_market, price_chart, resume_market,
)


def main() -> int:
    probe = check_db()
    if not probe.get("ok"):
        print(f"SKIPPED: cannot connect to the database ({probe.get('error')}). Check DATABASE_URL in backend/.env")
        return 1

    with session_scope() as db:
        tag = uuid.uuid4().int % 10**12
        admin = db.execute(
            text("insert into users(telegram_id, display_name) values (:t, 'Mkt Admin') returning id"),
            {"t": 9_200_000_000_000 + tag},
        ).scalar_one()

        # odd target so it cannot clash with real markets
        target = f"{(tag % 900000) / 1000 + 100:.3f}"
        m = create_market(db, actor_id=admin, symbol="sol", duration_seconds=86400,
                          target_price=target, reason="test market")
        assert m["status"] == "open" and m["symbol"] == "SOL" and m["effective_status"] == "open"
        assert m["payout_bps"] == 18000 and m["betting_closes_in_seconds"] > 0
        print("PASS create open market with correct schedule")

        assert get_market(db, m["id"])["id"] == m["id"]
        assert any(x["id"] == m["id"] for x in list_markets(db, symbol="SOL", status="open", limit=100))
        assert not any(x["id"] == m["id"] for x in list_markets(db, symbol="WIENER", limit=100))
        print("PASS get and list with filters")

        draft = create_market(db, actor_id=admin, symbol="SOL", duration_seconds=172800,
                              target_price=target, reason="draft test", publish=False)
        assert draft["status"] == "draft"
        assert not any(x["id"] == draft["id"] for x in list_markets(db, limit=100))
        assert any(x["id"] == draft["id"] for x in list_markets(db, include_drafts=True, limit=100))
        try:
            get_market(db, draft["id"])
        except NotFound:
            pass
        else:
            raise AssertionError("draft visible to public")
        print("PASS drafts hidden from public reads")

        paused = pause_market(db, actor_id=admin, market_id=m["id"], reason="maintenance")
        assert paused["status"] == "paused" and paused["pause_reason"] == "maintenance"
        try:
            pause_market(db, actor_id=admin, market_id=m["id"], reason="again")
        except AppError as exc:
            assert exc.code == "illegal_market_transition"
        else:
            raise AssertionError("double pause accepted")
        resumed = resume_market(db, actor_id=admin, market_id=m["id"], reason="all good")
        assert resumed["status"] == "open" and resumed["pause_reason"] is None
        print("PASS pause / resume")

        versions = db.execute(
            text("select count(*), bool_and(changed_by = :a) from market_config_versions where market_id = :m"),
            {"a": admin, "m": m["id"]},
        ).one()
        assert versions[0] == 3 and versions[1] is True, versions   # create, pause, resume
        audits = db.execute(
            text("select count(*) from audit_logs where entity_id = :m and action like 'market.%'"),
            {"m": str(m["id"])},
        ).scalar_one()
        assert audits == 3, audits
        print("PASS versioned with actor + audited")

        try:
            with db.begin_nested():
                db.execute(text("update markets set target_price = target_price + 1 where id = :m"), {"m": m["id"]})
        except DBAPIError as exc:
            assert translate_db_error(exc).code == "market_terms_immutable_after_draft"
        else:
            raise AssertionError("terms changed after creation")
        print("PASS terms immutable after creation")

        try:
            with db.begin_nested():
                create_market(db, actor_id=admin, symbol="USDC", duration_seconds=86400,
                              target_price="1", reason="x")
        except AppError as exc:
            assert exc.code == "asset_not_supported"
        else:
            raise AssertionError("USDC market accepted")
        print("PASS non-prediction asset rejected")

        chart = price_chart(db, "SOL", "24h")
        assert chart["symbol"] == "SOL" and isinstance(chart["points"], list)
        try:
            price_chart(db, "SOL", "99y")
        except AppError as exc:
            assert exc.code == "invalid_range"
        else:
            raise AssertionError("bad range accepted")
        print("PASS chart shape and range check")

        db.rollback()
    print("ALL MARKETS DB TESTS PASSED (nothing was saved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
