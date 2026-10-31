from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.serialize import iso, money
from app.core.rate_limit import limiter
from app.database import get_db
from app.deps import CurrentUserDep
from app.services import growth, notifications

router = APIRouter(tags=["growth"])


def _tier_out(t: dict | None) -> dict | None:
    if t is None:
        return None
    return {
        "id": t["id"], "name": t["name"], "min_staked": money(t["min_staked"]), "reward": money(t["reward"]),
        "benefits": t["benefits"], "unlocked": t["unlocked"], "achieved_at": iso(t["achieved_at"]),
        "reward_paid": t["reward_paid"],
    }


@router.get("/vip")
def read_vip(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    growth.refresh_vip(db, user.id)      # catches up users who staked before tiers existed
    v = growth.vip_ladder(db, user.id)
    nxt = v["next"]
    return {
        "total_staked": money(v["total_staked"]),
        "tiers": [_tier_out(t) for t in v["tiers"]],
        "current": _tier_out(v["current"]),
        "next": _tier_out(nxt),
        "remaining_to_next": money(max(0, nxt["min_staked"] - v["total_staked"])) if nxt else None,
    }


@router.get("/profile")
def read_profile(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    stats = growth.profile_stats(db, user.id)
    ref = growth.referral_summary(db, user.id)
    priv = growth.get_privacy(db, user.id)
    vip = growth.vip_ladder(db, user.id)
    return {
        "user": {"id": str(user.id), "display_name": user.display_name, "username": user.username,
                 "member_since": iso(priv["member_since"])},
        "stats": {"settled": stats["settled"], "wins": stats["wins"], "open": stats["open"],
                  "staked": money(stats["staked"]), "accuracy_pct": stats["accuracy_pct"]},
        "vip": {"current": _tier_out(vip["current"])},
        "referral": {"code": ref["code"], "total": ref["total"], "pending": ref["pending"],
                     "rewarded": ref["rewarded"], "earned": money(ref["earned"]),
                     "reward_per_referral": money(ref["reward_per_referral"]),
                     "already_referred": ref["already_referred"]},
        "privacy": {"leaderboard_alias": priv["leaderboard_alias"], "hide_on_leaderboard": priv["hide_on_leaderboard"]},
    }


class PrivacyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leaderboard_alias: str | None = Field(default=None, max_length=64)
    hide_on_leaderboard: bool | None = None


@router.patch("/profile")
def patch_profile(body: PrivacyIn, user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    priv = growth.update_privacy(
        db, user.id, alias=body.leaderboard_alias, alias_set="leaderboard_alias" in body.model_fields_set,
        hide=body.hide_on_leaderboard,
    )
    return {"leaderboard_alias": priv["leaderboard_alias"], "hide_on_leaderboard": priv["hide_on_leaderboard"]}


class ReferralIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=32)


@router.post("/referrals/apply", status_code=201)
@limiter.limit("10/minute")
def apply_referral(request: Request, body: ReferralIn, user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    growth.apply_referral_code(db, user.id, body.code)
    return {"applied": True}


@router.get("/leaderboard")
def read_leaderboard(
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    metric: Annotated[str, Query(max_length=12)] = "accuracy",
    period: Annotated[str, Query(max_length=10)] = "all",
):
    lb = growth.read_leaderboard(db, user.id, metric, period)

    def row(i: dict | None) -> dict | None:
        if i is None:
            return None
        return {"rank": i["rank"], "alias": i["alias"], "settled": i["settled"], "wins": i["wins"],
                "staked": money(i["staked"]), "won_total": money(i["won_total"]),
                "accuracy_pct": i["accuracy_pct"], "is_me": i["is_me"]}

    return {"metric": lb["metric"], "period": lb["period"], "min_settled": lb["min_settled"],
            "items": [row(i) for i in lb["items"]], "me": row(lb["me"])}


# ---- notifications ----------------------------------------------------------------------------
class NotificationPrefsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_results: bool | None = None
    market_closing: bool | None = None
    referrals: bool | None = None
    vip: bool | None = None
    payments: bool | None = None
    raffles: bool | None = None


@router.get("/notifications")
def read_notifications(
    user: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
):
    """The in-app bell: newest first, plus how many are unread."""
    data = notifications.list_for_user(db, user.id, limit)
    return {
        "unread": data["unread"],
        "items": [{"id": str(n["id"]), "type": n["type"], "title": n["title"], "body": n["body"],
                   "created_at": iso(n["created_at"]), "read": n["read_at"] is not None} for n in data["items"]],
    }


@router.post("/notifications/read")
def read_all_notifications(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    notifications.mark_all_read(db, user.id)
    return {"ok": True}


@router.get("/notifications/preferences")
def read_notification_prefs(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    return notifications.get_preferences(db, user.id)


@router.patch("/notifications/preferences")
def patch_notification_prefs(body: NotificationPrefsIn, user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    return notifications.update_preferences(db, user.id, changes)