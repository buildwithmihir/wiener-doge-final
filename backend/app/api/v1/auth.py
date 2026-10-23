"""Login. Telegram initData is verified server-side; the token only carries the user id."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.serialize import iso, wallet_out
from app.config import get_settings
from app.core.errors import NotFound
from app.core.rate_limit import AUTH_LIMIT, limiter
from app.core.security import create_access_token
from app.core.telegram_auth import TelegramUser, verify_init_data_with_settings
from app.database import get_db
from app.deps import CurrentUser, CurrentUserDep
from app.services.ledger import get_wallet
from app.services.users import upsert_telegram_user

router = APIRouter(tags=["auth"])


class TelegramLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    init_data: str = Field(min_length=10, max_length=4096)


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    telegram_id: int = Field(gt=0, lt=10**13)
    display_name: str = Field(default="Dev User", min_length=1, max_length=64)


def _session_payload(db: Session, user_id, created: bool) -> dict:
    token, expires_at = create_access_token(user_id)
    from app.deps import load_user

    user = load_user(db, user_id)
    return {
        "access_token": token, "token_type": "bearer", "expires_at": iso(expires_at),
        "new_user": created, "user": _user_out(user),
        "wallet": wallet_out(get_wallet(db, user_id)),
    }


def _user_out(user: CurrentUser) -> dict:
    return {"id": str(user.id), "display_name": user.display_name, "username": user.username,
            "roles": sorted(user.roles), "is_admin": user.is_admin}


@router.post("/auth/telegram")
@limiter.limit(AUTH_LIMIT)
def login_with_telegram(request: Request, body: TelegramLogin, db: Annotated[Session, Depends(get_db)]):
    verified = verify_init_data_with_settings(body.init_data)
    user_id, created = upsert_telegram_user(db, verified.user, get_settings().admin_telegram_id_set)
    return _session_payload(db, user_id, created)


@router.post("/auth/dev")
@limiter.limit(AUTH_LIMIT)
def login_dev(request: Request, body: DevLogin, db: Annotated[Session, Depends(get_db)]):
    """Local development only. Does not exist when DEV_AUTH_ENABLED is off (and never in production)."""
    settings = get_settings()
    if settings.is_production or not settings.dev_auth_enabled:
        raise NotFound("Not found.", "not_found")
    tg = TelegramUser(id=body.telegram_id, first_name=body.display_name, last_name=None, username=None,
                      language_code=None, photo_url=None, is_premium=False)
    user_id, created = upsert_telegram_user(db, tg, settings.admin_telegram_id_set)
    return _session_payload(db, user_id, created)


@router.get("/me")
def me(user: CurrentUserDep, db: Annotated[Session, Depends(get_db)]):
    return {"user": _user_out(user), "wallet": wallet_out(get_wallet(db, user.id))}
