"""Post-deploy smoke test. Run from YOUR computer, from the backend folder:

    python scripts\\smoke.py https://YOUR-API.onrender.com

Optional: set TICK_SECRET in your terminal first to also test the scheduler endpoint
(it is read from the environment and never printed):
    set TICK_SECRET=...      (Windows CMD)

It only calls public/read endpoints plus the tick. It never prints secrets.
"""
from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> int:
    local = len(sys.argv) == 2 and sys.argv[1].startswith("http://localhost")   # for testing on your own computer
    if len(sys.argv) != 2 or not (sys.argv[1].startswith("https://") or local):
        print("Usage: python scripts\\smoke.py https://YOUR-API-HOST")
        return 2
    base = sys.argv[1].rstrip("/") + "/api/v1"
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))
        failures += 0 if ok else 1

    with httpx.Client(timeout=90) as c:      # first call may wake a sleeping free server (~1 min)
        r = c.get(f"{base}/health")
        check("API is up", r.status_code == 200 and r.json().get("status") == "ok", f"HTTP {r.status_code}")

        r = c.get(f"{base}/health/db")
        check("database reachable", r.status_code == 200 and r.json().get("database") is True)

        r = c.get(f"{base}/config")
        cfg = r.json() if r.status_code == 200 else {}
        check("demo mode on, payments off", cfg.get("demo_mode") is True and cfg.get("payments_enabled") is False)

        r = c.get(f"{base}/markets?status=open&limit=5")
        check("markets endpoint", r.status_code == 200, f"{len(r.json().get('items', []))} open market(s)" if r.status_code == 200 else f"HTTP {r.status_code}")

        r = c.post(f"{base}/auth/dev", json={"telegram_id": 1, "display_name": "x"})
        check("dev login is OFF in production", r.status_code in (404, 403, 405), f"HTTP {r.status_code}")

        r = c.get(f"{base}/admin/reconcile")
        check("admin endpoints need a login", r.status_code == 401, f"HTTP {r.status_code}")

        r = c.post(f"{base}/internal/tick")
        check("tick refuses calls without the secret", r.status_code in (401, 404), f"HTTP {r.status_code}")

        secret = os.environ.get("TICK_SECRET", "")
        if secret:
            r = c.post(f"{base}/internal/tick", headers={"X-Tick-Secret": secret})
            ok = r.status_code == 200
            check("tick with the secret works", ok, f"HTTP {r.status_code}")
            if ok:
                body = r.json()
                print("     feed:", json.dumps(body.get("feed")), "| provider errors:", json.dumps(body.get("provider_errors", {})))
        else:
            print("SKIP tick with the secret (TICK_SECRET not set in this terminal)")

    print("\nALL SMOKE CHECKS PASSED" if failures == 0 else f"\n{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
