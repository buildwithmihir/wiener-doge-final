"""Wallet and ledger service (demo credits).

The money rules live in the database (supabase/migrations/0001_init_schema.sql):
append-only ledger, balances maintained by trigger, idempotent SQL functions.
This module only READS wallet state and calls the admin adjustment function.
Nothing here ever writes a balance directly.

Amounts are integers in base units: 1 DEMO = 1,000,000 units. No floats anywhere.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound

UNIT = 1_000_000
DECIMALS = 6
MAX_PARSE_DEMO = 10**12                    # sanity cap when parsing user input
MAX_ADJUSTMENT_UNITS = 1_000_000 * UNIT    # admin adjustment cap: 1,000,000 DEMO
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# ---- amount helpers ----------------------------------------------------------
def format_demo(units: int) -> str:
    """Exact text for a base-unit amount: 1500000 -> '1.5', 1000000000 -> '1000'."""
    sign = "-" if units < 0 else ""
    whole, frac = divmod(abs(int(units)), UNIT)
    out = str(whole)
    if frac:
        out += "." + f"{frac:0{DECIMALS}d}".rstrip("0")
    return sign + out


def parse_demo(value: Any) -> int:
    """Parse a DEMO amount ('12.5', 12, Decimal) to base units. Rejects floats-with-noise,
    more than 6 decimals, NaN/inf and absurdly large values. May be negative."""
    if value is None or isinstance(value, bool):
        raise AppError("invalid_amount", "Enter a valid amount.", 422)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except InvalidOperation:
        raise AppError("invalid_amount", "Enter a valid amount.", 422) from None
    if not number.is_finite() or abs(number) > MAX_PARSE_DEMO:
        raise AppError("invalid_amount", "Enter a valid amount.", 422)
    scaled = number * UNIT
    if scaled != scaled.to_integral_value():
        raise AppError("invalid_amount", f"Use at most {DECIMALS} decimal places.", 422)
    return int(scaled)


_EXPLANATIONS = {
    "signup_grant": "Welcome bonus",
    "stake_reserve": "Stake reserved for a prediction",
    "win_payout": "Prediction won",
    "loss_settle": "Prediction lost: stake forfeited",
    "refund": "Stake refunded",
    "admin_adjustment": "Balance adjustment by admin",
    "referral_reward": "Referral reward",
    "vip_reward": "VIP tier reward",
    "deposit": "Deposit",
    "withdraw_hold": "Withdrawal requested",
    "withdraw_release": "Withdrawal rejected: refunded",
    "withdraw_sent": "Withdrawal sent",
}


def explain_entry(kind: str) -> str:
    return _EXPLANATIONS.get(kind, "Balance change")


# ---- read models ---------------------------------------------------------------
@dataclass(frozen=True)
class Wallet:
    available: int
    reserved: int
    total: int


@dataclass(frozen=True)
class WalletEvent:
    tx_id: uuid.UUID
    kind: str
    title: str
    created_at: datetime
    available_delta: int
    reserved_delta: int
    net: int                  # change in total balance (available + reserved)
    ref_type: str | None
    ref_id: uuid.UUID | None
    cursor: int               # pass as before_cursor to get the next (older) page


def get_wallet(db: Session, user_id: uuid.UUID) -> Wallet:
    row = db.execute(
        text("select available, reserved, total from v_wallet where user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().first()
    if row is None:
        raise NotFound("Wallet not found.", "wallet_not_found")
    return Wallet(int(row["available"]), int(row["reserved"]), int(row["total"]))


_EVENTS_SQL = text(
    """
    select e.tx_id, e.kind, e.ref_type, e.ref_id,
           max(e.id)         as cursor,
           min(e.created_at) as created_at,
           coalesce(sum(e.amount) filter (where a.account_type = 'user_available'), 0) as available_delta,
           coalesce(sum(e.amount) filter (where a.account_type = 'user_reserved'),  0) as reserved_delta
    from ledger_entries e
    join ledger_accounts a on a.id = e.account_id
    where a.owner_user_id = :user_id
    group by e.tx_id, e.kind, e.ref_type, e.ref_id
    having cast(:before_cursor as bigint) is null or max(e.id) < cast(:before_cursor as bigint)
    order by max(e.id) desc
    limit :fetch_count
    """
)


def list_transactions(
    db: Session,
    user_id: uuid.UUID,
    limit: int = DEFAULT_PAGE_SIZE,
    before_cursor: int | None = None,
) -> tuple[list[WalletEvent], int | None]:
    """Newest first. Returns (events, next_cursor); next_cursor is None on the last page.

    One row per ledger transaction, showing how it moved the user's available and
    reserved balances (a lost prediction, for example, only reduces reserved).
    The admin's internal reason text is deliberately NOT exposed here.
    """
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    rows = db.execute(
        _EVENTS_SQL,
        {"user_id": user_id, "before_cursor": before_cursor, "fetch_count": limit + 1},
    ).mappings().all()

    has_more = len(rows) > limit
    events = [
        WalletEvent(
            tx_id=r["tx_id"],
            kind=r["kind"],
            title=explain_entry(r["kind"]),
            created_at=r["created_at"],
            available_delta=int(r["available_delta"]),
            reserved_delta=int(r["reserved_delta"]),
            net=int(r["available_delta"]) + int(r["reserved_delta"]),
            ref_type=r["ref_type"],
            ref_id=r["ref_id"],
            cursor=int(r["cursor"]),
        )
        for r in rows[:limit]
    ]
    return events, (events[-1].cursor if has_more and events else None)


# ---- admin / integrity -----------------------------------------------------------
def adjust_demo_credits(
    db: Session,
    *,
    user_id: uuid.UUID,
    amount_units: int,
    idempotency_key: str,
    actor_id: uuid.UUID,
    reason: str,
) -> int:
    """Admin credit (+) or debit (-). Idempotent by key; reason is mandatory and audited.
    Returns the user's new available balance. The database enforces no overdraft."""
    if isinstance(amount_units, bool) or not isinstance(amount_units, int):
        raise AppError("invalid_amount", "Amount must be a whole number of base units.", 422)
    if amount_units == 0 or abs(amount_units) > MAX_ADJUSTMENT_UNITS:
        raise AppError("invalid_amount", "Amount must be non-zero and at most 1,000,000 DEMO.", 422)
    reason = (reason or "").strip()
    if not reason or len(reason) > 500:
        raise AppError("reason_required", "A reason (1-500 characters) is required.", 422)
    if not (8 <= len(idempotency_key or "") <= 100):
        raise AppError("invalid_key", "Idempotency key must be 8-100 characters.", 422)

    return int(
        db.execute(
            text("select adjust_demo_credits(:user_id, cast(:amount as bigint), :key, :actor, :reason)"),
            {
                "user_id": user_id,
                "amount": amount_units,
                "key": idempotency_key,
                "actor": actor_id,
                "reason": reason,
            },
        ).scalar_one()
    )


def run_reconciliation(db: Session) -> list[tuple[str, str]]:
    """Ledger invariants check. Empty list = everything consistent."""
    rows = db.execute(text("select check_name, detail from ledger_reconcile()")).all()
    return [(r[0], r[1]) for r in rows]
