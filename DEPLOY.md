# WienerDoge: free deployment guide (Windows CMD)

Final setup: **Supabase** (database) + **Render Free** (API) + **Vercel Hobby** (frontend) + **cron-job.org** (scheduler).
Everything is demo credits only. Nothing here handles real money.

> **Secrets rule.** Bot token, DATABASE_URL, JWT_SECRET, TICK_SECRET, TELEGRAM_WEBHOOK_SECRET go ONLY into
> Render's dashboard and your local `backend\.env`. Never into Git, never into a chat, never into the frontend.

Free-tier facts below were checked on 2026-10-20. They change, so re-check if something behaves differently.

---

## 0. What you need
GitHub account, Supabase project (you already have one), Render account, Vercel account, cron-job.org account,
a Telegram bot from @BotFather (token), and a free CoinGecko Demo API key.

## 1. Supabase (database)
1. Supabase Dashboard -> SQL Editor. Run these files **in this order** (paste the whole file, press Run):
   1. `supabase\migrations\0001_init_schema.sql` (skip if already applied)
   2. `supabase\migrations\0002_growth_functions.sql`
   3. `supabase\seed_price_providers.sql`
2. Check: `select count(*) from vip_tiers;` -> 4, and `select * from ledger_reconcile();` -> no rows.
3. Project Settings -> Database -> Connection string -> **Transaction pooler** (port 6543). Copy it.
4. Change the beginning from `postgresql://` to `postgresql+psycopg://` and add `?sslmode=require` at the end.
   This is your `DATABASE_URL`. Keep it private.

## 2. Make 3 secrets (on your computer)
Run this **three times** and save the three outputs in a password manager or a private note:
```
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
They are: `JWT_SECRET`, `TICK_SECRET`, `TELEGRAM_WEBHOOK_SECRET`. All three must be different.

## 3. GitHub (private repo)
```
cd %USERPROFILE%\Desktop\wienerdoge
git init
git add .
git status
```
Read the `git status` list. **If you see any `.env` file, STOP** (the `.gitignore` should prevent it). Then:
```
git commit -m "WienerDoge demo"
```
Create a **private** repo on GitHub, and push with the commands GitHub shows you.

## 4. Render (API)
Easiest manual way: Render -> New -> Web Service -> connect your repo, then:

| Field | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | **Free** |
| Health Check Path | `/api/v1/health` |

(Or: New -> Blueprint, which reads `render.yaml`. It is untested, so use the manual way if it complains.)

Environment variables (Render -> Environment):

| Key | Value |
|---|---|
| `APP_ENV` | `production` |
| `PYTHON_VERSION` | `3.13.5` (Render's new default is newer than what was tested here) |
| `DEV_AUTH_ENABLED` | `false` |
| `DATABASE_URL` | from step 1 |
| `JWT_SECRET` / `TICK_SECRET` / `TELEGRAM_WEBHOOK_SECRET` | from step 2 |
| `TELEGRAM_BOT_TOKEN` | from @BotFather |
| `COINGECKO_API_KEY` | your CoinGecko Demo key |
| `ADMIN_TELEGRAM_IDS` | your numeric Telegram id (becomes admin on first login) |
| `MINI_APP_URL` | temporary: `https://placeholder.vercel.app` (fix in step 6) |
| `CORS_ORIGINS` | temporary: `https://placeholder.vercel.app` (fix in step 6) |

Deploy. If the service crashes at boot, open the Logs: the message `Invalid configuration: ...` lists exactly which
settings are wrong (it never prints their values). Fix them and redeploy.
Your API address is `https://<service-name>.onrender.com`.

Honest notes: the free instance sleeps after 15 min without traffic (step 8 prevents that), has 750 free hours per
month (one always-on service uses ~744, so run only this one service), Render's docs do not state its CPU/RAM (watch
the first deploy's logs), and Render may restart it at any time. Render itself says free instances are not for production.

## 5. Vercel (frontend)
Vercel -> Add New -> Project -> import the repo:
- **Root Directory:** `frontend`, Framework: Vite
- Environment variable: `VITE_API_URL` = `https://<service-name>.onrender.com/api/v1`
  (it is baked in at build time, so set it BEFORE the first deploy; if you change it later, redeploy)

Your app address is `https://<project>.vercel.app`.

## 6. Connect the two
Render -> Environment: set `MINI_APP_URL` and `CORS_ORIGINS` to your exact Vercel address
(`https://<project>.vercel.app`, no trailing slash, no path). Save: Render redeploys.

## 7. Telegram bot
Create `backend\.env` on your computer (copy `backend\.env.example`) with the same `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_WEBHOOK_SECRET`, `MINI_APP_URL` and `APP_ENV=development`. Then:
```
cd %USERPROFILE%\Desktop\wienerdoge\backend
pip install -r requirements.txt
python -m app.bot.setup --webhook-url https://<service-name>.onrender.com/api/v1/telegram/webhook
```
It registers the webhook, the command list and the "Play" menu button. It never prints your token.

## 8. cron-job.org (scheduler, also keeps Render awake)
Create a job:
- URL: `https://<service-name>.onrender.com/api/v1/internal/tick`
- Method: **POST**; Header: `X-Tick-Secret` = your `TICK_SECRET`
- Schedule: **every 1 minute**; enable failure notifications by email
Why every minute: the worker polls prices adaptively (every ~10 min, every 1 min near a market close) and settles
markets on each tick. The calls also stop Render from sleeping and keep Supabase from pausing.
Limits: cron-job.org times out after 30 s and disables a job after more than 25 failures.

## 9. Smoke test (from your computer)
```
cd %USERPROFILE%\Desktop\wienerdoge\backend
set TICK_SECRET=PASTE_YOUR_TICK_SECRET_HERE
python scripts\smoke.py https://<service-name>.onrender.com
```
Expect 8 PASS lines and `ALL SMOKE CHECKS PASSED`. The last line shows the price feed: `SOL: healthy` means CoinGecko
works. `WIENER: missing` means DexScreener has no pool with enough liquidity (that is the safety gate, not a bug).
The first call can take about a minute if the server was asleep.

## 10. First use
1. Open the bot in Telegram -> `/start` -> **Play**. Log in. Your id is in `ADMIN_TELEGRAM_IDS`, so Profile shows "Admin panel".
2. Admin -> Markets -> create a SOL 24h market (target near the current price).
3. Place a small prediction from the Markets tab; check History.
4. Create WIENER markets only when the smoke test shows `WIENER: healthy`.

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Render crashes: `Invalid configuration` | a secret is missing/short or a placeholder; read the listed names |
| App says "Could not load" / network error in Telegram | `CORS_ORIGINS` does not exactly match the Vercel address, or `VITE_API_URL` is wrong (redeploy Vercel after changing it) |
| Login fails inside Telegram | `TELEGRAM_BOT_TOKEN` on Render differs from the bot you opened |
| Bot does not answer | webhook not set (redo step 7) or Render asleep/restarting; check the cron job is running |
| `database reachable` FAIL | `DATABASE_URL` must start with `postgresql+psycopg://`; use the pooler string; Supabase project might be paused (open it in the dashboard) |
| Markets never settle | cron job disabled after failures (check its history); price feed not healthy |

## If a secret leaks
Bot token: @BotFather -> /revoke, put the new token in Render and `backend\.env`, rerun step 7.
Other secrets: generate new values (step 2), update Render and cron-job.org. Changing `JWT_SECRET` logs everyone out.
