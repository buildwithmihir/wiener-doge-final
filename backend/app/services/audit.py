"""Read side of the append-only audit log (admin only)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100


def list_audit(db: Session, limit: int = 50, before_id: int | None = None) -> tuple[list[dict], int | None]:
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    rows = db.execute(
        text(
            """select id, actor_user_id, actor_type, action, entity_type, entity_id, reason, created_at
               from audit_logs
               where cast(:before as bigint) is null or id < cast(:before as bigint)
               order by id desc limit :n"""
        ),
        {"before": before_id, "n": limit + 1},
    ).mappings().all()
    items = [dict(r) for r in rows[:limit]]
    return items, (items[-1]["id"] if len(rows) > limit and items else None)
