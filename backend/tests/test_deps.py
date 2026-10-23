"""Tests for authentication / authorization dependencies (no database needed).

Run from the backend folder (no pytest needed):
    python -m tests.test_deps
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

# Independent of backend/.env: env vars override the .env file.
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import deps
from app.core.errors import register_exception_handlers
from app.core.security import ALGORITHM, AUDIENCE, ISSUER, create_access_token
from app.database import get_db
from app.deps import AdminUser, CurrentUser, CurrentUserDep, ModeratorUser

USERS: dict[uuid.UUID, CurrentUser] = {}


def add_user(roles=(), status="active"):
    uid = uuid.uuid4()
    USERS[uid] = CurrentUser(
        id=uid,
        telegram_id=1000 + len(USERS),
        username="u",
        display_name="U",
        status=status,
        roles=frozenset(roles),
    )
    return uid


# Replace the real database lookup with an in-memory one for these tests.
deps.load_user = lambda db, user_id: USERS.get(user_id)

app = FastAPI()
register_exception_handlers(app)
app.dependency_overrides[get_db] = lambda: None


@app.get("/me")
def me(user: CurrentUserDep):
    return {"id": str(user.id)}


@app.get("/mod")
def mod(user: ModeratorUser):
    return {"ok": True}


@app.get("/admin")
def admin(user: AdminUser):
    return {"ok": True}


client = TestClient(app)


def auth(user_id):
    token, _ = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def code_of(response):
    return response.json()["error"]["code"]


def test_missing_token():
    r = client.get("/me")
    assert r.status_code == 401 and code_of(r) == "missing_token"


def test_garbage_token():
    r = client.get("/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and code_of(r) == "invalid_token"


def test_expired_token():
    token, _ = create_access_token(add_user(), expires_minutes=-5)
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401 and code_of(r) == "token_expired"


def test_valid_user_gets_in():
    uid = add_user()
    r = client.get("/me", headers=auth(uid))
    assert r.status_code == 200 and r.json()["id"] == str(uid)


def test_unknown_user_rejected():
    r = client.get("/me", headers=auth(uuid.uuid4()))
    assert r.status_code == 401 and code_of(r) == "invalid_token"


def test_suspended_user_blocked():
    r = client.get("/me", headers=auth(add_user(status="suspended")))
    assert r.status_code == 403 and code_of(r) == "account_not_active"


def test_normal_user_cannot_use_admin_or_moderator_routes():
    headers = auth(add_user())
    assert client.get("/admin", headers=headers).status_code == 403
    assert client.get("/mod", headers=headers).status_code == 403


def test_moderator_can_moderate_but_not_admin():
    headers = auth(add_user(roles=["moderator"]))
    assert client.get("/mod", headers=headers).status_code == 200
    assert client.get("/admin", headers=headers).status_code == 403


def test_admin_can_do_both():
    headers = auth(add_user(roles=["admin"]))
    assert client.get("/admin", headers=headers).status_code == 200
    assert client.get("/mod", headers=headers).status_code == 200


def test_role_removed_takes_effect_immediately():
    uid = add_user(roles=["admin"])
    headers = auth(uid)
    assert client.get("/admin", headers=headers).status_code == 200
    USERS[uid] = CurrentUser(uid, 1, "u", "U", "active", frozenset())  # admin role revoked in DB
    assert client.get("/admin", headers=headers).status_code == 403


def test_forged_roles_claim_in_token_is_ignored():
    uid = add_user()  # plain user in the database
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uid), "iat": now, "exp": now + timedelta(minutes=5),
            "iss": ISSUER, "aud": AUDIENCE, "typ": "access",
            "roles": ["admin"], "role": "admin", "is_admin": True,
        },
        os.environ["JWT_SECRET"],
        algorithm=ALGORITHM,
    )
    r = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403, r.text


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
