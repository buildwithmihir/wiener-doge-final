"""FastAPI dependencies: database session, current user, role checks.

Authorization rule: the token only says WHO the user is. Account status and
roles are re-read from the database on EVERY request, so suspending a user or
removing an admin role takes effect immediately, and a token can never carry or
grant privileges.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.database import get_db

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    telegram_id: int
    username: str | None
    display_name: str
    status: str
    roles: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    @property
    def is_moderator(self) -> bool:
        return bool(self.roles & {"moderator", "admin"})


_LOAD_USER_SQL = text(
    """
    select u.id, u.telegram_id, u.username, u.display_name, u.status,
           coalesce(array_agg(r.role) filter (where r.role is not null), '{}'::text[]) as roles
    from users u
    left join user_roles r on r.user_id = u.id
    where u.id = :user_id
    group by u.id
    """
)


def load_user(db: Session, user_id: uuid.UUID) -> CurrentUser | None:
    row = db.execute(_LOAD_USER_SQL, {"user_id": user_id}).mappings().first()
    if row is None:
        return None
    return CurrentUser(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        display_name=row["display_name"],
        status=row["status"],
        roles=frozenset(row["roles"] or []),
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise Unauthorized("Login required.", "missing_token")

    claims = decode_access_token(credentials.credentials)
    user = load_user(db, uuid.UUID(str(claims["sub"])))
    if user is None:
        raise Unauthorized("Invalid session.", "invalid_token")
    if user.status != "active":
        raise Forbidden("This account is not active.", "account_not_active")
    return user


def require_roles(*allowed: str):
    """Build a dependency that only lets users holding at least one of `allowed` roles in."""
    allowed_set = frozenset(allowed)

    def dependency(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not (user.roles & allowed_set):
            raise Forbidden("You do not have permission to do that.", "forbidden")
        return user

    return dependency


require_admin = require_roles("admin")
require_moderator = require_roles("moderator", "admin")

# Shorthand types for endpoint signatures:  def endpoint(user: CurrentUserDep, db: DbSession)
DbSession = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
AdminUser = Annotated[CurrentUser, Depends(require_admin)]
ModeratorUser = Annotated[CurrentUser, Depends(require_moderator)]
