"""Tests for Telegram initData verification.

Run from the backend folder (no pytest needed):
    python -m tests.test_telegram_auth
Also pytest-compatible later: pytest tests/test_telegram_auth.py
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.core.errors import Unauthorized
from app.core.telegram_auth import verify_init_data

BOT_TOKEN = "123456:TEST_TOKEN"
DEFAULT_USER = {"id": 42, "first_name": "Mihir", "username": "mihir"}


def make_fields(age_seconds=0, user=None):
    return {
        "auth_date": str(int(time.time()) - age_seconds),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(DEFAULT_USER if user is None else user, separators=(",", ":")),
    }


def sign(fields, token=BOT_TOKEN):
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signed = dict(fields)
    signed["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(signed)


def expect_fail(code, func):
    try:
        func()
    except Unauthorized as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}"
        return
    raise AssertionError(f"expected Unauthorized({code}) but call succeeded")


def test_valid_login():
    result = verify_init_data(sign(make_fields()), BOT_TOKEN, 3600)
    assert result.user.id == 42
    assert result.user.username == "mihir"
    assert result.query_id is not None
    assert len(result.fingerprint) == 64


def test_wrong_bot_token_rejected():
    data = sign(make_fields(), token="999:OTHER_BOT")
    expect_fail("initdata_invalid", lambda: verify_init_data(data, BOT_TOKEN, 3600))


def test_tampered_user_rejected():
    data = sign(make_fields())
    tampered = data.replace("Mihir", "Hacker")
    assert tampered != data
    expect_fail("initdata_invalid", lambda: verify_init_data(tampered, BOT_TOKEN, 3600))


def test_tampered_user_id_rejected():
    fields = make_fields()
    data = sign(fields)
    fields["user"] = json.dumps({"id": 1, "first_name": "Mihir"}, separators=(",", ":"))
    forged = urlencode({**fields, "hash": data.split("hash=")[1]})
    expect_fail("initdata_invalid", lambda: verify_init_data(forged, BOT_TOKEN, 3600))


def test_expired_rejected():
    data = sign(make_fields(age_seconds=7200))
    expect_fail("initdata_expired", lambda: verify_init_data(data, BOT_TOKEN, 3600))


def test_future_auth_date_rejected():
    data = sign(make_fields(age_seconds=-600))
    expect_fail("initdata_invalid", lambda: verify_init_data(data, BOT_TOKEN, 3600))


def test_missing_hash_rejected():
    expect_fail("initdata_invalid", lambda: verify_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN, 3600))


def test_empty_rejected():
    expect_fail("initdata_missing", lambda: verify_init_data("", BOT_TOKEN, 3600))


def test_duplicate_keys_rejected():
    data = sign(make_fields()) + "&auth_date=1"
    expect_fail("initdata_invalid", lambda: verify_init_data(data, BOT_TOKEN, 3600))


def test_user_without_id_rejected():
    data = sign(make_fields(user={"first_name": "NoId"}))
    expect_fail("initdata_invalid", lambda: verify_init_data(data, BOT_TOKEN, 3600))


def test_oversized_rejected():
    expect_fail("initdata_invalid", lambda: verify_init_data("a=" + "x" * 9000, BOT_TOKEN, 3600))


def test_non_ascii_hash_does_not_crash():
    data = sign(make_fields()).split("&hash=")[0] + "&hash=%C3%A9%C3%A9"
    expect_fail("initdata_invalid", lambda: verify_init_data(data, BOT_TOKEN, 3600))


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, func in tests:
        func()
        print("PASS", name)
    print(f"ALL {len(tests)} TESTS PASSED")
