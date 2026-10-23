"""Rate limiting (slowapi).

Buckets are per logged-in user when a valid session token is present, otherwise
per client IP. An invalid or forged token never creates a new bucket: it falls
back to the IP bucket, so limits cannot be dodged with garbage tokens.

Storage is in-memory (per process). That is fine for one server process; with
several workers/instances switch the limiter to a shared store (Redis) later.
Behind a reverse proxy, run uvicorn with --proxy-headers so the real client IP
is used (deployment phase).

Usage on an endpoint (the endpoint MUST take `request: Request`):

    @router.post("/auth/telegram")
    @limiter.limit(AUTH_LIMIT)
    async def login(request: Request, ...): ...
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

AUTH_LIMIT = "10/minute"          # login attempts
PREDICTION_LIMIT = "30/minute"    # placing predictions
WRITE_LIMIT = "60/minute"         # other state-changing calls
ADMIN_LIMIT = "120/minute"        # admin panel calls
DEFAULT_LIMIT = "240/minute"      # everything else


def client_key(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        try:
            from app.core.security import decode_access_token

            return f"user:{decode_access_token(token.strip())['sub']}"
        except Exception:  # noqa: BLE001 - any failure => treat as anonymous
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=client_key,
    default_limits=[DEFAULT_LIMIT],
    headers_enabled=False,
)


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    try:
        return int(exc.limit.limit.get_expiry())  # window length, e.g. 60 for "x/minute"
    except Exception:  # noqa: BLE001
        return 60


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = _retry_after_seconds(exc)
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Too many requests. Please slow down.",
                "details": {"retry_after_seconds": retry_after},
            }
        },
        headers={"Retry-After": str(retry_after)},
    )


def setup_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_middleware(SlowAPIMiddleware)
