"""Tests for rate limiting.

Run from the backend folder (no pytest needed):
    python -m tests.test_rate_limit
"""
import os
import uuid

# Make the test independent of backend/.env (env vars override the .env file).
os.environ["JWT_SECRET"] = "t" * 48
os.environ["APP_ENV"] = "development"

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.errors import register_exception_handlers
from app.core.rate_limit import limiter, setup_rate_limiting
from app.core.security import create_access_token

app = FastAPI()
register_exception_handlers(app)
setup_rate_limiting(app)


@app.get("/limited")
@limiter.limit("3/minute")
async def limited(request: Request):
    return {"ok": True}


def bearer(user_id=None):
    token, _ = create_access_token(user_id or uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


def fresh_client():
    """New client with empty counters, so tests do not affect each other."""
    limiter.reset()
    return TestClient(app)


def test_limit_enforced_with_clean_error_shape():
    client = fresh_client()
    headers = bearer()
    for _ in range(3):
        assert client.get("/limited", headers=headers).status_code == 200
    blocked = client.get("/limited", headers=headers)
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["details"]["retry_after_seconds"] == 60
    assert blocked.headers["retry-after"] == "60"


def test_users_have_separate_buckets():
    client = fresh_client()
    a, b = bearer(), bearer()
    for _ in range(3):
        client.get("/limited", headers=a)
    assert client.get("/limited", headers=a).status_code == 429
    assert client.get("/limited", headers=b).status_code == 200


def test_garbage_tokens_cannot_dodge_the_limit():
    client = fresh_client()
    codes = [
        client.get("/limited", headers={"Authorization": f"Bearer garbage-{i}"}).status_code
        for i in range(6)
    ]
    assert codes[:3] == [200, 200, 200], codes
    assert all(c == 429 for c in codes[3:]), codes


def test_anonymous_requests_share_an_ip_bucket():
    client = fresh_client()
    codes = [client.get("/limited").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429], codes


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
