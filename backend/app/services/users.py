"""Users: create / update a user from a verified Telegram identity.

The database trigger creates the wallet accounts and the signup demo-credit grant when a
user row is inserted, so a user can never exist without a wallet.
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import Forbidden
from app.core.telegram_auth import TelegramUser


def display_name_for(tg: TelegramUser) -> str:
    name = " ".join(part for part in (tg.first_name, tg.last_name) if part).strip()
    return (name or tg.username or f"User {tg.id}")[:128]


def upsert_telegram_user(
    db: Session, tg: TelegramUser, admin_telegram_ids: Iterable[int] = ()
) -> tuple[uuid.UUID, bool]:
    """Returns (user_id, created). Suspended / banned users cannot log in."""
    row = db.execute(
        text(
            """insert into users(telegram_id, username, display_name, photo_url, language_code, last_seen_at)
               values (:tid, :username, :name, :photo, :lang, now())
               on conflict (telegram_id) do update
                 set username = excluded.username, display_name = excluded.display_name,
                     photo_url = excluded.photo_url, language_code = excluded.language_code,
                     last_seen_at = now()
               returning id, status, (xmax = 0) as created"""
        ),
        {"tid": tg.id, "username": (tg.username or None), "name": display_name_for(tg),
         "photo": tg.photo_url, "lang": tg.language_code},
    ).mappings().one()
    if row["status"] != "active":
        raise Forbidden("This account is not active.", "account_not_active")

    if tg.id in set(admin_telegram_ids):
        granted = db.execute(
            text("insert into user_roles(user_id, role) values (:u, 'admin') on conflict (user_id, role) do nothing"),
            {"u": row["id"]},
        ).rowcount
        if granted:
            db.execute(
                text("select wd_audit(:u, 'system', 'role.bootstrap_admin', 'user', :id, null, "
                     "cast('{\"role\":\"admin\"}' as jsonb), 'listed in ADMIN_TELEGRAM_IDS')"),
                {"u": row["id"], "id": str(row["id"])},
            )
    return row["id"], bool(row["created"])


# ---- admin helpers -------------------------------------------------------------------
USER_STATUSES = ("active", "suspended", "banned")


def find_user_by_telegram_id(db: Session, telegram_id: int) -> dict | None:
    row = db.execute(
        text("select id, telegram_id, username, display_name, status, created_at, last_seen_at "
             "from users where telegram_id = :t"),
        {"t": telegram_id},
    ).mappings().first()
    return dict(row) if row else None


def set_user_status(db: Session, *, actor_id: uuid.UUID, user_id: uuid.UUID, status: str, reason: str) -> dict:
    """Suspend / ban / reactivate a user. Reason is mandatory and audited. Admins cannot lock themselves out."""
    from app.core.errors import AppError, NotFound

    if status not in USER_STATUSES:
        raise AppError("invalid_status", "Status must be active, suspended or banned.", 422)
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    if user_id == actor_id and status != "active":
        raise AppError("cannot_lock_self", "You cannot suspend or ban your own account.", 409)

    before = db.execute(text("select status from users where id = :u for update"), {"u": user_id}).scalar_one_or_none()
    if before is None:
        raise NotFound("User not found.", "user_not_found")
    db.execute(text("update users set status = :s where id = :u"), {"s": status, "u": user_id})
    db.execute(
        text("select wd_audit(:a, 'admin', 'user.set_status', 'user', :id, "
             "jsonb_build_object('status', cast(:b as text)), jsonb_build_object('status', cast(:s as text)), :r)"),
        {"a": actor_id, "id": str(user_id), "b": before, "s": status, "r": reason},
    )
    return {"user_id": str(user_id), "status": status, "previous_status": before}
