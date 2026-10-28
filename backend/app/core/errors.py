"""Uniform, safe API errors.

Every error leaves the API as {"error": {"code", "message", "details?"}}.
Database errors raised by our SQL functions are translated to friendly codes;
anything unknown becomes a generic 500 and is logged server-side only.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("wienerdoge")


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFound(AppError):
    def __init__(self, message: str = "Not found", code: str = "not_found") -> None:
        super().__init__(code, message, 404)


class Unauthorized(AppError):
    def __init__(self, message: str = "Authentication required", code: str = "unauthorized") -> None:
        super().__init__(code, message, 401)


class Forbidden(AppError):
    def __init__(self, message: str = "Not allowed", code: str = "forbidden") -> None:
        super().__init__(code, message, 403)


class Conflict(AppError):
    def __init__(self, message: str = "Conflict", code: str = "conflict") -> None:
        super().__init__(code, message, 409)


# Keys are the exact error names raised by supabase/migrations/0001_init_schema.sql
DB_MESSAGE_MAP: dict[str, tuple[int, str]] = {
    "insufficient_balance": (400, "Not enough balance."),
    "stake_out_of_range": (400, "Stake is outside the allowed range for this market."),
    "market_not_found": (404, "Market not found."),
    "user_not_found": (404, "User not found."),
    "user_not_active": (403, "This account is not active."),
    "market_not_open": (409, "This market is not open for predictions."),
    "market_not_started": (409, "This market has not started yet."),
    "betting_closed": (409, "Betting has closed for this market."),
    "terms_mismatch": (409, "Market terms changed. Please refresh and try again."),
    "market_not_closed_yet": (409, "This market has not closed yet."),
    "market_not_settleable": (409, "This market cannot be settled."),
    "market_final_state_immutable": (409, "This market is already final."),
    "market_terms_immutable_after_draft": (409, "Market terms cannot be changed after creation."),
    "illegal_market_transition": (409, "That market status change is not allowed."),
    "cannot_open_after_betting_closes": (409, "Cannot open a market after betting has closed."),
    "market_already_closed_for_betting": (409, "Betting window already ended."),
    "market_must_start_draft_or_open": (409, "A new market must start as draft or open."),
    "price_unavailable": (503, "No reliable price is available right now."),
    "snapshot_unreliable": (503, "Price data is stale or abnormal."),
    "snapshot_wrong_asset": (400, "Price snapshot is for a different asset."),
    "snapshot_outside_settlement_window": (409, "Price snapshot is outside the settlement window."),
    "reason_required": (400, "A reason is required."),
    "actor_required": (400, "An acting admin is required."),
    "amount_zero": (400, "Amount cannot be zero."),
    "payments_disabled_demo_only": (403, "Deposits and withdrawals are currently unavailable."),
    "balance_is_ledger_managed": (403, "Balances can only change through the ledger."),
    "ledger_is_append_only": (403, "Ledger records cannot be changed."),
    "audit_log_is_append_only": (403, "Audit records cannot be changed."),
    "prediction_terms_immutable": (409, "Prediction terms cannot be changed."),
    "prediction_already_final": (409, "This prediction is already settled."),
    "predictions_are_permanent": (403, "Predictions cannot be deleted."),
    "invalid_code": (404, "That referral code does not exist."),
    "self_referral": (400, "You cannot use your own referral code."),
    "already_referred": (409, "A referral code was already applied to your account."),
    "too_late_existing_user": (409, "Referral codes can only be applied before your first prediction."),
    "circular_referral": (400, "That referral is not allowed."),
    "referrer_not_active": (409, "That referral code cannot be used."),
    "withdraw_out_of_range": (400, "Amount is outside the allowed withdrawal range."),
    "daily_withdraw_limit": (400, "Daily withdrawal limit reached."),
    "withdraw_bad_state": (409, "This withdrawal cannot be changed in its current state."),
    "withdrawal_not_found": (404, "Withdrawal not found."),
    "asset_not_supported": (400, "That asset is not supported."),
}

SQLSTATE_MAP: dict[str, tuple[int, str, str]] = {
    "23505": (409, "duplicate", "This record already exists."),
    "23503": (409, "reference_error", "A related record is missing or in use."),
    "23514": (400, "invalid_value", "A value is not allowed."),
    "23502": (400, "missing_value", "A required value is missing."),
}


def map_db_message(raw: str | None) -> AppError | None:
    """Turn a raw 'error_name: extra' database message into an AppError."""
    key = (raw or "").split(":", 1)[0].strip()
    hit = DB_MESSAGE_MAP.get(key)
    if hit is None:
        return None
    return AppError(key, hit[1], hit[0])


def translate_db_error(exc: DBAPIError) -> AppError | None:
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    raw = getattr(diag, "message_primary", None) or str(orig)
    mapped = map_db_message(raw)
    if mapped is not None:
        return mapped
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate in SQLSTATE_MAP:
        status, code, message = SQLSTATE_MAP[sqlstate]
        return AppError(code, message, status)
    return None


def _json_error(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return _json_error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")),
                "message": str(err.get("msg", "Invalid value")),
            }
            for err in exc.errors()
        ]
        return _json_error(422, "validation_error", "Some fields are invalid.", fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _json_error(exc.status_code, f"http_{exc.status_code}", message)

    @app.exception_handler(DBAPIError)
    async def _db_error(_: Request, exc: DBAPIError) -> JSONResponse:
        mapped = translate_db_error(exc)
        if mapped is not None:
            return _json_error(mapped.status_code, mapped.code, mapped.message)
        logger.exception("Unhandled database error")
        return _json_error(500, "database_error", "A database error occurred.")

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return _json_error(500, "internal_error", "Something went wrong.")
