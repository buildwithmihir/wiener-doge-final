"""Deposits (SOL + WIENER), sweeps to the hot wallet, and admin-approved withdrawals.

The ledger is in USD. Token amounts are converted with a CONSERVATIVE price:
  deposit  -> the LOWEST good price of the last N minutes (a pumped pool cannot inflate a credit)
  withdraw -> the HIGHEST good price of the last N minutes (the user never receives too many tokens)
"""
from __future__ import annotations

import logging
import uuid
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.database import session_scope
from app.payments.solana import (
    SYSTEM_PROGRAM, Rpc, RpcError, create_ata_idempotent_ix, derive_deposit_keypair, get_balance,
    mint_decimals, send_tx, sign_tx, system_transfer_ix, token_account_for, token_balance, transfer_checked_ix,
)
from app.services.markets import latest_good_price

log = logging.getLogger("wienerdoge.payments")

UNIT = 1_000_000
SOL_DECIMALS = 9
SYMBOLS = ("SOL", "WIENER")
PRICE_WINDOW_MIN = {"SOL": 15, "WIENER": 60}
SOL_SWEEP_MIN = 2_000_000        # lamports: do not sweep dust
SOL_FEE_BUFFER = 5_000_000       # lamports kept in the hot wallet for fees / token-account rent
MAX_SIG_PAGES = 10
TICK_LOCK_ID = 727_002


# ---- basics ---------------------------------------------------------------------------------
def open_rpc() -> Rpc:
    try:
        return Rpc(get_settings().solana_rpc_url)
    except RpcError:
        raise AppError("payments_not_configured", "Payments are not available yet.", 503) from None


def _wiener_mint() -> Pubkey:
    mint = get_settings().wiener_mint_address
    if not mint:
        raise AppError("payments_not_configured", "Payments are not available yet.", 503)
    return Pubkey.from_string(mint)


def _hot() -> Keypair:
    secret = get_settings().hot_wallet_secret
    if not secret:
        raise AppError("payments_not_configured", "Withdrawals are not configured.", 503)
    return Keypair.from_base58_string(secret)


def _decimals(rpc: Rpc, symbol: str) -> int:
    return SOL_DECIMALS if symbol == "SOL" else mint_decimals(rpc, str(_wiener_mint()))


def usd_units(native: int, decimals: int, price: Decimal) -> int:
    value = Decimal(native) / (Decimal(10) ** decimals) * price * UNIT
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def native_units(usd: int, decimals: int, price: Decimal) -> int:
    value = Decimal(usd) / UNIT / price * (Decimal(10) ** decimals)
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def conservative_price(db: Session, symbol: str, side: str) -> Decimal:
    latest = latest_good_price(db, symbol)            # AppError if the feed is stale / missing
    fn = "min" if side == "deposit" else "max"        # fixed whitelist, never user input
    row = db.execute(
        text(f"""select {fn}(s.price) from market_price_snapshots s join assets a on a.id = s.asset_id
                 where a.symbol = :sym and not s.is_stale and not s.is_anomalous
                   and s.fetched_at > now() - make_interval(mins => :m)"""),
        {"sym": symbol, "m": PRICE_WINDOW_MIN[symbol]},
    ).scalar_one()
    if row is None:
        return latest
    window = Decimal(row)
    return min(window, latest) if side == "deposit" else max(window, latest)


# ---- deposit wallet -----------------------------------------------------------------------------
def ensure_deposit_address(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    q = text("select owner_address, token_account from deposit_addresses where user_id = :u")
    row = db.execute(q, {"u": user_id}).mappings().first()
    if row is None:
        seed = get_settings().deposit_master_seed
        if not seed:
            raise AppError("payments_not_configured", "Deposits are not available yet.", 503)
        kp = derive_deposit_keypair(seed, user_id)
        db.execute(
            text("""insert into deposit_addresses(user_id, owner_address, token_account)
                    values (:u, :o, :t) on conflict (user_id) do nothing"""),
            {"u": user_id, "o": str(kp.pubkey()), "t": str(token_account_for(kp.pubkey(), _wiener_mint()))},
        )
        row = db.execute(q, {"u": user_id}).mappings().one()
    return dict(row)


# ---- deposits: detect + credit ------------------------------------------------------------------
def _sol_delta(tx: dict, owner: str) -> int:
    keys = [k["pubkey"] if isinstance(k, dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    if owner not in keys:
        return 0
    i = keys.index(owner)
    return int(tx["meta"]["postBalances"][i]) - int(tx["meta"]["preBalances"][i])


def _token_delta(meta: dict, owner: str, mint: str) -> int:
    def total(entries: Any) -> int:
        return sum(int(e["uiTokenAmount"]["amount"]) for e in (entries or [])
                   if e.get("owner") == owner and e.get("mint") == mint)
    return total(meta.get("postTokenBalances")) - total(meta.get("preTokenBalances"))


def _new_signatures(rpc: Rpc, address: str, last: str | None) -> list[dict]:
    out: list[dict] = []
    before = None
    for _ in range(MAX_SIG_PAGES):
        params: dict[str, Any] = {"limit": 100, "commitment": "finalized"}
        if last:
            params["until"] = last
        if before:
            params["before"] = before
        page = rpc.call("getSignaturesForAddress", [address, params]) or []
        out.extend(page)
        if len(page) < 100:
            break
        before = page[-1]["signature"]
    return out          # newest first


def _scan_one(db: Session, rpc: Rpc, r: Any, symbol: str, minimum: int) -> int:
    is_sol = symbol == "SOL"
    address = r["owner_address"] if is_sol else r["token_account"]
    cursor_col = "sol_cursor" if is_sol else "token_cursor"         # fixed whitelist
    sigs = _new_signatures(rpc, address, r[cursor_col])
    if not sigs:
        return 0
    decimals = _decimals(rpc, symbol)
    mint = None if is_sol else str(_wiener_mint())
    credited = 0
    for item in reversed(sigs):
        if item.get("err") is not None:
            continue
        tx = rpc.call("getTransaction", [item["signature"], {
            "encoding": "jsonParsed", "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
        if not tx:
            raise RpcError("transaction not available yet")          # retry next tick; the cursor is not moved
        if tx["meta"].get("err") is not None:
            continue
        delta = _sol_delta(tx, r["owner_address"]) if is_sol else _token_delta(tx["meta"], r["owner_address"], mint)
        if delta <= 0:
            continue                                                  # sweeps / outgoing moves
        price = conservative_price(db, symbol, "deposit")
        usd = usd_units(delta, decimals, price)
        if usd < minimum:
            continue                                                  # dust: stays on-chain, not credited
        if db.execute(
            text("select credit_deposit(:u, :sym, cast(:a as bigint), cast(:usd as bigint), cast(:p as numeric), :t)"),
            {"u": r["user_id"], "sym": symbol, "a": delta, "usd": usd, "p": price, "t": item["signature"]},
        ).scalar_one():
            credited += 1
    db.execute(text(f"update deposit_addresses set {cursor_col} = :s where user_id = :u"),
               {"s": sigs[0]["signature"], "u": r["user_id"]})
    return credited


def scan_deposits(db: Session, rpc: Rpc) -> int:
    minimum = int(db.execute(text("select wd_setting_int('payments.min_deposit', 1000000)")).scalar_one())
    rows = db.execute(text(
        "select user_id, owner_address, token_account, sol_cursor, token_cursor from deposit_addresses")).mappings().all()
    credited = 0
    for r in rows:
        for symbol in SYMBOLS:
            try:
                with db.begin_nested():
                    credited += _scan_one(db, rpc, r, symbol, minimum)
            except Exception as exc:  # noqa: BLE001 - one user/asset must not block the rest
                log.warning("deposit scan skipped for user %s %s: %s", r["user_id"], symbol, type(exc).__name__)
    return credited


def sweep_deposits(db: Session, rpc: Rpc) -> int:
    """Move SOL and WIENER from each user's deposit wallet into the hot wallet (the hot wallet pays the fees)."""
    s, hot, mint = get_settings(), _hot(), _wiener_mint()
    decimals = mint_decimals(rpc, str(mint))
    hot_ata = token_account_for(hot.pubkey(), mint)
    rows = db.execute(text("select user_id, owner_address, token_account from deposit_addresses")).mappings().all()
    swept = 0
    for r in rows:
        try:
            kp = derive_deposit_keypair(s.deposit_master_seed, r["user_id"])
            ixs = []
            tokens = token_balance(rpc, r["token_account"])
            if tokens > 0:
                ixs += [create_ata_idempotent_ix(hot.pubkey(), hot_ata, hot.pubkey(), mint),
                        transfer_checked_ix(Pubkey.from_string(r["token_account"]), mint, hot_ata, kp.pubkey(), tokens, decimals)]
            lamports = get_balance(rpc, r["owner_address"])
            if lamports >= SOL_SWEEP_MIN:
                ixs.append(system_transfer_ix(kp.pubkey(), hot.pubkey(), lamports))
            if not ixs:
                continue
            _, raw = sign_tx(rpc, ixs, hot, [kp])
            send_tx(rpc, raw)
            swept += 1
        except Exception:  # noqa: BLE001
            log.exception("sweep failed for user %s", r["user_id"])
    return swept


# ---- withdrawals -------------------------------------------------------------------------------
def validate_destination(rpc: Rpc, address: str) -> str:
    address = (address or "").strip()
    try:
        pk = Pubkey.from_string(address)
    except Exception:  # noqa: BLE001
        raise AppError("invalid_address", "Enter a valid Solana wallet address.", 422) from None
    if hasattr(pk, "is_on_curve") and not pk.is_on_curve():
        raise AppError("invalid_address", "That is not a normal wallet address.", 422)
    try:
        info = (rpc.call("getAccountInfo", [str(pk), {"encoding": "base64"}]) or {}).get("value")
    except RpcError:
        raise AppError("payments_unavailable", "Could not check the address right now. Try again.", 503) from None
    if info is not None and info.get("owner") != str(SYSTEM_PROGRAM):
        raise AppError("invalid_address", "Use your normal wallet address (not a token account or a program).", 422)
    return str(pk)


_LIST_SQL = """
select w.id, w.user_id, a.symbol as asset, w.status, w.amount, w.native_amount, w.native_decimals,
       w.destination_ref, w.tx_signature, w.created_at, w.reviewed_reason
from withdrawals w join assets a on a.id = w.asset_id
"""


def get_withdrawal(db: Session, wid: uuid.UUID) -> dict:
    return dict(db.execute(text(_LIST_SQL + " where w.id = :i"), {"i": wid}).mappings().one())


def list_withdrawals(db: Session, user_id: uuid.UUID | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    rows = db.execute(
        text(_LIST_SQL + """ where (cast(:u as uuid) is null or w.user_id = :u) and (cast(:s as text) is null or w.status = :s)
                             order by w.created_at desc limit :n"""),
        {"u": user_id, "s": status, "n": max(1, min(limit, 100))},
    ).mappings().all()
    return [dict(r) for r in rows]


def create_withdrawal(db: Session, rpc: Rpc, *, user_id: uuid.UUID, asset: str, usd_units_: int, address: str, key: str) -> dict:
    if not (8 <= len(key or "") <= 120):
        raise AppError("invalid_key", "Idempotency key must be 8-120 characters.", 422)
    dest = validate_destination(rpc, address)
    wid = db.execute(
        text("select id from request_withdrawal(:u, :sym, cast(:a as bigint), :d, :k)"),
        {"u": user_id, "sym": asset, "a": usd_units_, "d": dest, "k": key},
    ).scalar_one()
    return get_withdrawal(db, wid)


def approve_withdrawal(db: Session, actor_id: uuid.UUID, wid: uuid.UUID, reason: str) -> None:
    reason = (reason or "").strip()
    if not reason or len(reason) > 300:
        raise AppError("reason_required", "A reason (1-300 characters) is required.", 422)
    done = db.execute(
        text("""update withdrawals set status = 'approved', reviewed_by = :a, reviewed_reason = :r, updated_at = now()
                where id = :i and status in ('pending','failed') returning id"""),
        {"a": actor_id, "r": reason, "i": wid},
    ).first()
    if done is None:
        raise AppError("withdraw_bad_state", "This withdrawal cannot be approved in its current state.", 409)
    db.execute(text("select wd_audit(:a, 'admin', 'withdrawal.approve', 'withdrawal', :i, null, null, :r)"),
               {"a": actor_id, "i": str(wid), "r": reason})


def reject_withdrawal(db: Session, actor_id: uuid.UUID, wid: uuid.UUID, reason: str) -> None:
    db.execute(text("select reject_withdrawal(:i, :a, :r)"), {"i": wid, "a": actor_id, "r": (reason or "").strip()})


def _settle_sending(rpc: Rpc) -> None:
    """Resolve withdrawals that were sent but not yet recorded. A live transaction is never re-sent."""
    with session_scope() as db:
        rows = db.execute(text(
            """select id, tx_signature, sending_at < now() - interval '3 minutes' as old
               from withdrawals where status = 'sending' and tx_signature is not null""")).mappings().all()
        for w in rows:
            try:
                st = rpc.call("getSignatureStatuses", [[w["tx_signature"]], {"searchTransactionHistory": True}])["value"][0]
            except (RpcError, KeyError, TypeError):
                continue
            if st is None:
                if w["old"]:     # the blockhash has expired, so this transaction can never land: safe to retry
                    db.execute(text("update withdrawals set status = 'approved', updated_at = now() where id = :i"), {"i": w["id"]})
            elif st.get("err") is not None:
                db.execute(text("update withdrawals set status = 'failed', updated_at = now() where id = :i"), {"i": w["id"]})
            elif st.get("confirmationStatus") == "finalized":
                db.execute(text("select finalize_withdrawal(:i, :s)"), {"i": w["id"], "s": w["tx_signature"]})


def _send_approved(rpc: Rpc) -> int:
    hot, mint = _hot(), _wiener_mint()
    hot_ata = token_account_for(hot.pubkey(), mint)
    with session_scope() as db:
        ids = [r[0] for r in db.execute(text(
            "select id from withdrawals where status = 'approved' order by created_at limit 5")).all()]
    sent = 0
    for wid in ids:
        raw = None
        try:
            with session_scope() as db:   # claim + record the signature, COMMITTED before anything is sent
                w = db.execute(text(
                    """select w.id, w.amount, w.destination_ref, a.symbol from withdrawals w join assets a on a.id = w.asset_id
                       where w.id = :i and w.status = 'approved' for update of w skip locked"""), {"i": wid}).mappings().first()
                if w is None:
                    continue
                symbol = w["symbol"]
                decimals = _decimals(rpc, symbol)
                price = conservative_price(db, symbol, "withdraw")
                native = native_units(int(w["amount"]), decimals, price)
                if native <= 0:
                    continue
                dest = Pubkey.from_string(w["destination_ref"])
                if symbol == "SOL":
                    if get_balance(rpc, str(hot.pubkey())) < native + SOL_FEE_BUFFER:
                        log.warning("hot wallet has too little SOL for withdrawal %s", wid)
                        continue
                    ixs = [system_transfer_ix(hot.pubkey(), dest, native)]
                else:
                    if token_balance(rpc, str(hot_ata)) < native:
                        log.warning("hot wallet has too little WIENER for withdrawal %s", wid)
                        continue
                    dest_ata = token_account_for(dest, mint)
                    ixs = [create_ata_idempotent_ix(hot.pubkey(), dest_ata, dest, mint),
                           transfer_checked_ix(hot_ata, mint, dest_ata, hot.pubkey(), native, decimals)]
                sig, raw = sign_tx(rpc, ixs, hot)
                db.execute(text(
                    """update withdrawals set status = 'sending', tx_signature = :s, sending_at = now(), updated_at = now(),
                              native_amount = :n, native_decimals = :d, price = :p where id = :i"""),
                    {"s": sig, "n": native, "d": decimals, "p": price, "i": wid})
        except Exception as exc:  # noqa: BLE001
            log.warning("withdrawal %s not sent: %s", wid, type(exc).__name__)
            continue
        if raw is None:
            continue
        try:
            send_tx(rpc, raw)
            sent += 1
        except RpcError:
            log.exception("send failed for withdrawal %s (it will be re-checked)", wid)
    return sent


# ---- the one entry point the scheduler calls -----------------------------------------------------
def run_payments_tick() -> dict[str, Any]:
    s = get_settings()
    with session_scope() as lock_db:      # held open for the whole tick: two overlapping ticks never run
        if not lock_db.execute(text("select pg_try_advisory_xact_lock(:i)"), {"i": TICK_LOCK_ID}).scalar_one():
            return {"skipped": "another payments tick is running"}
        if not lock_db.execute(text("select wd_setting_bool('payments.enabled', false)")).scalar_one():
            return {"skipped": "payments disabled"}
        rpc = open_rpc()
        out: dict[str, Any] = {}
        try:
            with session_scope() as db:
                out["deposits_credited"] = scan_deposits(db, rpc)
            if s.hot_wallet_secret:
                with session_scope() as db:
                    out["swept"] = sweep_deposits(db, rpc)
                _settle_sending(rpc)
                out["withdrawals_sent"] = _send_approved(rpc)
                _settle_sending(rpc)
        finally:
            rpc.close()
        return out