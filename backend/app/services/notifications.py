"""Notifications: in-app list (bell icon) + Telegram bot messages.

What users get notified about:
  * WON bets only (losses / refunds / cashouts are visible in History but never notified)
  * deposits credited, withdrawals sent or rejected
  * referral rewards and VIP unlocks
  * raffles and other announcements (broadcast())

Two steps, both run from the scheduler tick:
  1. enqueue_*  : turn recent events into `notifications` rows (idempotent: dedupe_key is unique,
                  so running it every minute never duplicates a message; honours the user's preferences)
  2. deliver_pending : send a few pending rows through Telegram's sendMessage, within a time budget
                  and mark them sent / retry / failed.
The same rows are what the app's notification bell shows (list_for_user), whatever their Telegram status.

Delivery is at-least-once. Messages are plain text with numbers, the asset symbol and fixed words, never
user-supplied text. The bot token is never logged or returned.
"""
from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any, Callable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.serialize import price
from app.core.errors import AppError
from app.core.logging_safety import quiet_http_loggers
from app.services.ledger import format_demo

log = logging.getLogger("wienerdoge.notifications")

MAX_ATTEMPTS = 3
RECENT_HOURS = 24            # never backfill older events (avoids a flood after first deploy)
FOOTER = ""
PREFERENCE_COLUMNS = ("market_results", "market_closing", "referrals", "vip", "payments", "raffles")
_TYPE_TO_PREF = {
    "market_result": "market_results",
    "referral_reward": "referrals",
    "vip_unlock": "vip",
    "deposit": "payments",
    "withdrawal": "payments",
    "raffle": "raffles",
}


class SendResult(str, Enum):
    SENT = "sent"
    RETRY = "retry"          # temporary problem: try again on a later tick
    PERMANENT = "permanent"  # e.g. the user blocked the bot: never retry


Sender = Callable[[int, str], SendResult]


# ---- message texts -------------------------------------------------------------------------
def result_text(symbol: str, direction: str, target: Any, status: str, stake: int, payout: int) -> str:
    call = f"{symbol} {direction.upper()} {price(target)}"
    if status == "won":
        return f"You won! Your {call} prediction paid ${format_demo(payout)} (stake ${format_demo(stake)})." + FOOTER
    if status == "lost":
        return f"Your {call} prediction did not win. Stake lost: ${format_demo(stake)}." + FOOTER
    return f"Your {call} market was voided. Your stake of ${format_demo(stake)} was refunded." + FOOTER


# ---- step 1: enqueue -----------------------------------------------------------------------
_INSERT = text(
    """insert into notifications(user_id, type, title, body, payload, dedupe_key)
       values (:u, :t, :title, :body, cast(:payload as jsonb), :k)
       on conflict (dedupe_key) do nothing"""
)


def _wants(db: Session, user_id: Any, notif_type: str) -> bool:
    column = _TYPE_TO_PREF[notif_type]            # fixed whitelist, never user input
    row = db.execute(
        text(f"select {column} from notification_preferences where user_id = :u"), {"u": user_id}
    ).scalar_one_or_none()
    return True if row is None else bool(row)


def _enqueue(db: Session, rows: list[dict[str, Any]], notif_type: str, title: str, key_prefix: str) -> int:
    made = 0
    for r in rows:
        if not _wants(db, r["user_id"], notif_type):
            continue
        res = db.execute(_INSERT, {"u": r["user_id"], "t": notif_type, "title": title, "body": r["body"],
                                   "payload": json.dumps(r.get("payload", {})), "k": f"{key_prefix}:{r['key']}"})
        made += res.rowcount or 0
    return made


def enqueue_results(db: Session) -> int:
    """WON bets only."""
    rows = db.execute(
        text(
            """select p.id, p.user_id, a.symbol, p.direction, p.target_price_snapshot as target, p.status,
                      p.stake, p.payout_amount
               from predictions p join markets m on m.id = p.market_id join assets a on a.id = m.asset_id
               join users u on u.id = p.user_id
               where p.status = 'won' and p.settled_at > now() - make_interval(hours => :h)
                 and u.status = 'active'
               order by p.settled_at limit 200"""
        ),
        {"h": RECENT_HOURS},
    ).mappings().all()
    items = [{"user_id": r["user_id"], "key": str(r["id"]),
              "body": result_text(r["symbol"], r["direction"], r["target"], r["status"], int(r["stake"]), int(r["payout_amount"])),
              "payload": {"prediction_id": str(r["id"]), "status": r["status"]}} for r in rows]
    return _enqueue(db, items, "market_result", "You won!", "pred")


def enqueue_rewards(db: Session) -> int:
    made = 0
    refs = db.execute(
        text(
            """select r.id, r.referrer_id as user_id, r.reward_amount from referrals r
               join users u on u.id = r.referrer_id
               where r.status = 'rewarded' and r.rewarded_at > now() - make_interval(hours => :h) and u.status = 'active'
               limit 200"""
        ),
        {"h": RECENT_HOURS},
    ).mappings().all()
    made += _enqueue(db, [{"user_id": r["user_id"], "key": str(r["id"]),
                           "body": f"A friend joined with your code and played. You earned ${format_demo(int(r['reward_amount']))}." + FOOTER}
                          for r in refs], "referral_reward", "Referral reward", "ref")
    vips = db.execute(
        text(
            """select s.id, s.user_id, t.name, t.reward from user_vip_status s
               join vip_tiers t on t.id = s.tier_id join users u on u.id = s.user_id
               where s.achieved_at > now() - make_interval(hours => :h) and u.status = 'active' limit 200"""
        ),
        {"h": RECENT_HOURS},
    ).mappings().all()
    made += _enqueue(db, [{"user_id": r["user_id"], "key": str(r["id"]),
                           "body": f"You reached {r['name']} VIP! Bonus: ${format_demo(int(r['reward']))}." + FOOTER}
                          for r in vips], "vip_unlock", "VIP unlocked", "vip")
    return made


def enqueue_payments(db: Session) -> int:
    """Deposits that were credited and withdrawals that were sent or rejected."""
    made = 0
    deposits = db.execute(
        text(
            """select d.id, d.user_id, d.usd_value, a.symbol
               from deposits d join assets a on a.id = d.asset_id join users u on u.id = d.user_id
               where d.status = 'credited' and d.usd_value is not null and u.status = 'active'
                 and d.created_at > now() - make_interval(hours => :h) limit 200"""
        ),
        {"h": RECENT_HOURS},
    ).mappings().all()
    made += _enqueue(db, [{"user_id": r["user_id"], "key": f"dep:{r['id']}",
                           "body": f"Deposit received: ${format_demo(int(r['usd_value']))} ({r['symbol']}) was added to your balance." + FOOTER,
                           "payload": {"deposit_id": str(r["id"])}} for r in deposits],
                     "deposit", "Deposit received", "pay")
    withdrawals = db.execute(
        text(
            """select w.id, w.user_id, w.status, w.amount, a.symbol
               from withdrawals w join assets a on a.id = w.asset_id join users u on u.id = w.user_id
               where w.status in ('sent','rejected') and u.status = 'active'
                 and w.updated_at > now() - make_interval(hours => :h) limit 200"""
        ),
        {"h": RECENT_HOURS},
    ).mappings().all()
    made += _enqueue(db, [{
        "user_id": r["user_id"], "key": f"wd:{r['id']}:{r['status']}",
        "body": (f"Your withdrawal of ${format_demo(int(r['amount']))} ({r['symbol']}) was sent." if r["status"] == "sent"
                 else f"Your withdrawal of ${format_demo(int(r['amount']))} was rejected and the amount returned to your balance.") + FOOTER,
        "payload": {"withdrawal_id": str(r["id"]), "status": r["status"]}} for r in withdrawals],
        "withdrawal", "Withdrawal update", "pay")
    return made


def broadcast(db: Session, notif_type: str, title: str, body: str, dedupe_key: str, limit: int = 5000) -> int:
    """Announcement for every active user who has that type switched on (for example a new raffle).
    Safe to call twice with the same dedupe_key."""
    if notif_type not in _TYPE_TO_PREF:
        raise AppError("invalid_type", "Unknown notification type.", 422)
    ids = [r[0] for r in db.execute(text("select id from users where status = 'active' limit :n"), {"n": limit}).all()]
    return _enqueue(db, [{"user_id": u, "key": f"{dedupe_key}:{u}", "body": body} for u in ids],
                    notif_type, title, "bc")


# ---- step 2: deliver -----------------------------------------------------------------------
def deliver_pending(db: Session, send: Sender, *, max_items: int = 15, budget_seconds: float = 8.0,
                    clock: Callable[[], float] = time.monotonic) -> dict[str, int]:
    started = clock()
    rows = db.execute(
        text(
            """select n.id, n.attempts, u.telegram_id, n.body from notifications n join users u on u.id = n.user_id
               where n.status = 'pending' and n.attempts < :max order by n.created_at
               limit :n for update of n skip locked"""
        ),
        {"max": MAX_ATTEMPTS, "n": max_items},
    ).mappings().all()
    out = {"sent": 0, "retry": 0, "failed": 0}
    for r in rows:
        if clock() - started > budget_seconds:
            break                                   # the rest stay pending for the next tick
        try:
            result = send(int(r["telegram_id"]), r["body"])
        except Exception as exc:  # noqa: BLE001 - a sender bug must not break the tick
            log.warning("notification sender error: %s", type(exc).__name__)
            result = SendResult.RETRY
        attempts = int(r["attempts"]) + 1
        if result is SendResult.SENT:
            db.execute(text("update notifications set status='sent', sent_at=now(), attempts=:a where id=:i"), {"a": attempts, "i": r["id"]})
            out["sent"] += 1
        elif result is SendResult.PERMANENT or attempts >= MAX_ATTEMPTS:
            db.execute(text("update notifications set status='failed', attempts=:a where id=:i"), {"a": attempts, "i": r["id"]})
            out["failed"] += 1
        else:
            db.execute(text("update notifications set attempts=:a where id=:i"), {"a": attempts, "i": r["id"]})
            out["retry"] += 1
    return out


def make_telegram_sender(bot_token: str, client: httpx.Client | None = None) -> Sender:
    """Build a sender for Telegram's sendMessage. The token only ever lives inside this closure."""
    quiet_http_loggers()      # httpx would otherwise log the URL, which contains the token
    http = client or httpx.Client(timeout=4.0)
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(chat_id: int, body: str) -> SendResult:
        try:
            r = http.post(url, json={"chat_id": chat_id, "text": body, "disable_web_page_preview": True})
        except httpx.HTTPError as exc:
            log.warning("telegram send failed: %s", type(exc).__name__)   # NOT the message: it can contain the URL
            return SendResult.RETRY
        if r.status_code == 200:
            return SendResult.SENT
        if r.status_code in (400, 403):               # chat not found / bot blocked / user deactivated
            return SendResult.PERMANENT
        log.warning("telegram send HTTP %s", r.status_code)
        return SendResult.RETRY                        # 429 and 5xx: later

    return send


def run_notifications(db: Session, send: Sender | None) -> dict[str, Any]:
    """Enqueue then deliver. Each part is isolated so a problem here never breaks settlement."""
    summary: dict[str, Any] = {"queued": 0}
    try:
        with db.begin_nested():
            summary["queued"] = enqueue_results(db) + enqueue_rewards(db) + enqueue_payments(db)
    except Exception:  # noqa: BLE001
        log.exception("enqueueing notifications failed")
        summary["enqueue_error"] = True
    if send is not None:
        try:
            with db.begin_nested():
                summary.update(deliver_pending(db, send))
        except Exception:  # noqa: BLE001
            log.exception("delivering notifications failed")
            summary["deliver_error"] = True
    return summary


# ---- in-app list (the bell) ----------------------------------------------------------------
def list_for_user(db: Session, user_id: Any, limit: int = 30) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    rows = db.execute(
        text("""select id, type, title, body, created_at, read_at from notifications
                where user_id = :u order by created_at desc limit :n"""),
        {"u": user_id, "n": limit},
    ).mappings().all()
    unread = db.execute(text("select count(*) from notifications where user_id = :u and read_at is null"),
                        {"u": user_id}).scalar_one()
    return {"items": [dict(r) for r in rows], "unread": int(unread)}


def mark_all_read(db: Session, user_id: Any) -> None:
    db.execute(text("update notifications set read_at = now() where user_id = :u and read_at is null"), {"u": user_id})


# ---- preferences ---------------------------------------------------------------------------
def get_preferences(db: Session, user_id: Any) -> dict[str, bool]:
    cols = ", ".join(PREFERENCE_COLUMNS)              # fixed whitelist
    row = db.execute(text(f"select {cols} from notification_preferences where user_id = :u"), {"u": user_id}).mappings().first()
    return {c: (True if row is None else bool(row[c])) for c in PREFERENCE_COLUMNS}


def update_preferences(db: Session, user_id: Any, changes: dict[str, bool]) -> dict[str, bool]:
    unknown = set(changes) - set(PREFERENCE_COLUMNS)
    if unknown:
        raise AppError("invalid_preference", "Unknown notification setting.", 422)
    current = get_preferences(db, user_id) | {k: bool(v) for k, v in changes.items()}
    cols = ", ".join(PREFERENCE_COLUMNS)
    marks = ", ".join(f":{c}" for c in PREFERENCE_COLUMNS)
    sets = ", ".join(f"{c} = :{c}" for c in PREFERENCE_COLUMNS)
    db.execute(
        text(f"""insert into notification_preferences(user_id, {cols}, updated_at)
                 values (:user_id, {marks}, now())
                 on conflict (user_id) do update set {sets}, updated_at = now()"""),
        {"user_id": user_id, **current},
    )
    return current