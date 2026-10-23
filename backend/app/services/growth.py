"""VIP tiers, referrals, leaderboard and profile settings (demo credits only).

The money-moving parts (reward grants, VIP unlocks, referral attribution) live in SQL
functions from supabase/migrations/0002_growth_functions.sql; this module reads, validates
and calls them. Rewards are minted through the append-only ledger and are idempotent.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError

METRICS = ("accuracy", "wagered")
PERIODS = {"all": None, "weekly": timedelta(days=7), "monthly": timedelta(days=30)}
LEADERBOARD_SIZE = 50
_RANK_SCAN = 1000          # how deep we look to find "my rank" (fine for a demo-sized user base)


def total_staked(db: Session, user_id: uuid.UUID) -> int:
    """Same definition the SQL update_vip() uses: open + won + lost stakes (refunds excluded)."""
    return int(db.execute(
        text("select coalesce(sum(stake), 0) from predictions where user_id = :u and status in ('open','won','lost')"),
        {"u": user_id},
    ).scalar_one())


def refresh_vip(db: Session, user_id: uuid.UUID) -> int:
    """Unlock any newly reached tiers. Never lets a VIP problem block the caller's transaction."""
    try:
        with db.begin_nested():
            return int(db.execute(text("select update_vip(:u)"), {"u": user_id}).scalar_one())
    except Exception:   # noqa: BLE001 - a failed VIP refresh must not fail a prediction
        return 0


def vip_ladder(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    staked = total_staked(db, user_id)
    tiers = db.execute(text("""
        select t.id, t.name, t.min_staked, t.reward, t.sort_order, t.benefits,
               s.achieved_at, coalesce(s.reward_paid, false) as reward_paid
        from vip_tiers t
        left join user_vip_status s on s.tier_id = t.id and s.user_id = :u
        where t.is_active order by t.sort_order
    """), {"u": user_id}).mappings().all()
    out: list[dict[str, Any]] = []
    current = None
    next_tier = None
    for t in tiers:
        unlocked = t["achieved_at"] is not None
        row = {
            "id": t["id"], "name": t["name"], "min_staked": int(t["min_staked"]), "reward": int(t["reward"]),
            "benefits": list(t["benefits"] or []), "unlocked": unlocked,
            "achieved_at": t["achieved_at"], "reward_paid": bool(t["reward_paid"]),
        }
        out.append(row)
        if unlocked:
            current = row
        elif next_tier is None:
            next_tier = row
    return {"total_staked": staked, "tiers": out, "current": current, "next": next_tier}


def referral_summary(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    code = db.execute(text("select ensure_referral_code(:u)"), {"u": user_id}).scalar_one()
    counts = db.execute(text("""
        select count(*) as total,
               count(*) filter (where status = 'pending') as pending,
               count(*) filter (where status = 'rewarded') as rewarded,
               coalesce(sum(reward_amount) filter (where status = 'rewarded'), 0) as earned
        from referrals where referrer_id = :u
    """), {"u": user_id}).mappings().one()
    applied = db.execute(text("select 1 from referrals where referred_id = :u"), {"u": user_id}).first() is not None
    reward = int(db.execute(text("select wd_setting_int('referral.reward', 0)")).scalar_one())
    return {
        "code": code, "total": int(counts["total"]), "pending": int(counts["pending"]),
        "rewarded": int(counts["rewarded"]), "earned": int(counts["earned"]),
        "reward_per_referral": reward, "already_referred": applied,
    }


def apply_referral_code(db: Session, user_id: uuid.UUID, code: str) -> None:
    clean = (code or "").strip().upper()
    if not (6 <= len(clean) <= 16) or not clean.isalnum():
        raise AppError("invalid_code", "That referral code does not exist.", 404)
    with db.begin_nested():
        db.execute(text("select * from apply_referral(:u, :c)"), {"u": user_id, "c": clean})


def profile_stats(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    row = db.execute(text("""
        select count(*) filter (where status in ('won','lost')) as settled,
               count(*) filter (where status = 'won') as wins,
               count(*) filter (where status = 'open') as open_count,
               coalesce(sum(stake) filter (where status in ('open','won','lost')), 0) as staked
        from predictions where user_id = :u
    """), {"u": user_id}).mappings().one()
    settled, wins = int(row["settled"]), int(row["wins"])
    return {
        "settled": settled, "wins": wins, "open": int(row["open_count"]), "staked": int(row["staked"]),
        "accuracy_pct": None if settled == 0 else round(100.0 * wins / settled, 1),
    }


def get_privacy(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    row = db.execute(text("select leaderboard_alias, hide_on_leaderboard, created_at from users where id = :u"),
                     {"u": user_id}).mappings().one()
    return {"leaderboard_alias": row["leaderboard_alias"], "hide_on_leaderboard": bool(row["hide_on_leaderboard"]),
            "member_since": row["created_at"]}


def update_privacy(db: Session, user_id: uuid.UUID, *, alias: str | None, alias_set: bool, hide: bool | None) -> dict[str, Any]:
    if alias_set:
        alias = (alias or "").strip() or None
        if alias is not None:
            if len(alias) > 32:
                raise AppError("invalid_alias", "Alias can be at most 32 characters.", 422)
            if any(ord(ch) < 32 for ch in alias):
                raise AppError("invalid_alias", "Alias contains invalid characters.", 422)
        db.execute(text("update users set leaderboard_alias = :a where id = :u"), {"a": alias, "u": user_id})
    if hide is not None:
        db.execute(text("update users set hide_on_leaderboard = :h where id = :u"), {"h": hide, "u": user_id})
    return get_privacy(db, user_id)


def read_leaderboard(db: Session, user_id: uuid.UUID, metric: str, period: str) -> dict[str, Any]:
    if metric not in METRICS:
        raise AppError("invalid_metric", "Unknown leaderboard metric.", 422)
    if period not in PERIODS:
        raise AppError("invalid_period", "Unknown leaderboard period.", 422)
    delta = PERIODS[period]
    since = None if delta is None else datetime.now(timezone.utc) - delta
    rows = db.execute(
        text("select * from leaderboard(:m, :s, :l, 0)"), {"m": metric, "s": since, "l": _RANK_SCAN}
    ).mappings().all()
    items, me = [], None
    for r in rows:
        item = {
            "rank": int(r["rank"]), "alias": r["alias"], "settled": int(r["settled"]), "wins": int(r["wins"]),
            "staked": int(r["staked"]), "won_total": int(r["won_total"]),
            "accuracy_pct": None if r["accuracy_pct"] is None else float(r["accuracy_pct"]),
            "is_me": r["user_id"] == user_id,
        }
        if item["is_me"]:
            me = item
        if len(items) < LEADERBOARD_SIZE:
            items.append(item)
    return {"metric": metric, "period": period, "items": items, "me": me,
            "min_settled": int(db.execute(text("select wd_setting_int('leaderboard.min_settled', 1)")).scalar_one())}
