# WienerDoge: security and legal notes (read before you share the link with anyone)

Not legal advice. I am not a lawyer. Nothing here has had a professional security audit or a penetration test.

## 1. What this app is, and the line it must not cross
WienerDoge is a **demo**. Credits are **DEMO credits: no cash value, not redeemable, not transferable**. Every screen,
bot message and API response says so, and the header shows a permanent DEMO badge.

How the demo-only rule is enforced (not just promised):
- The database has deposit/withdrawal tables, but a database rule blocks any row while the setting `payments.enabled` is false.
- There are **no deposit or withdrawal API endpoints**. A test (`test_api_db`) fails if one ever appears.
- The app stores **no private keys, seed phrases or wallet connections**, and the bot asks for none.
- Credits move only through an append-only double-entry ledger (triggers block edits and deletes). `ledger_reconcile()` and the admin "Ledger integrity" check prove the books balance.

**Do not change this into a real-money, token, prize or "redeem for anything of value" product without a lawyer.**
The moment credits can be bought, sold, withdrawn, traded, or exchanged for prizes, cash, tokens or anything else of value,
this stops being a harmless demo and can become regulated gambling, betting or a securities/derivatives issue depending on
where you and your users are. India in particular has strict, changing rules on online games and betting; I have not
researched current law for this build and you must not rely on me for it. Things that quietly cross the line:
selling or gifting credits for money, leaderboard prizes of value, "airdrops" tied to credits, or promising future value.
I will not help wire real deposits, withdrawals or key storage into this project.

Also read Telegram's and CoinGecko's / DexScreener's terms of use for your use case (a public bot, price display).
CoinGecko's free Demo plan is intended for personal/low-volume use; check what your usage requires.

## 2. Secrets: the rules
- Bot token, `DATABASE_URL`, `JWT_SECRET`, `TICK_SECRET`, `TELEGRAM_WEBHOOK_SECRET`, CoinGecko key: only in Render's dashboard and your local `backend\.env`. Never in Git, chat, screenshots or the frontend. `.env` is in `.gitignore`; check `git status` before every push.
- The production config refuses to start with placeholder or short secrets, or with dev login switched on.
- **Found and fixed during build:** the HTTP library logged request URLs at INFO level, and Telegram's API puts the bot token in the URL, so the token would have appeared in Render's logs. Those loggers are now silenced, and a test checks the token never reaches the logs.
- If anything leaks: @BotFather `/revoke` for the bot token; regenerate the others; see `DEPLOY.md`.

## 3. What is protected, and how
| Area | Control |
|---|---|
| Login | Telegram `initData` HMAC verified server-side with the bot token, with a max age; the JWT carries only the user id; roles and ban status are re-read from the database on every request |
| Admin | Server checks the role on every admin call (the UI only hides buttons); every admin action needs a written reason and is audit-logged |
| Money | Integers only (1 DEMO = 1,000,000 units), no floats; idempotency keys stop double-taps and retries from charging twice; the database refuses overdrafts |
| Settlement | Uses a real, fresh, non-anomalous price snapshot taken after close; if none arrives in time the market is voided and every stake refunded; never invents a price |
| Database access | Row-level security denies everything to browser roles; only the backend connects |
| Webhooks / scheduler | Telegram webhook checks its secret header; `/internal/tick` is off (404) until `TICK_SECRET` is 32+ chars, then needs the secret header |
| Abuse | Rate limits on login, predictions, admin and referral calls; every input field has a length cap and the bot webhook caps body size (there is no global request-size limit); the bot never echoes user text |

## 4. Known gaps and limits (be honest with yourself about these)
1. **Rate limiting is in memory, per process.** That is correct only while the API runs as **one** instance (Render Free is one). If you scale out or move to serverless, add a shared store (e.g. a database or Redis).
2. **WIENER is a thin on-chain token.** The provider ignores pools under the liquidity floor and refuses conflicting pools, but a determined actor can still move a small pool around close time. Treat WIENER markets as entertainment, never as a trustworthy price. Keep them paused unless the feed is healthy. The abnormal-move check (15% between checks) is a safety net, not a guarantee.
3. **One price source per asset** (CoinGecko for SOL, DexScreener for WIENER). If it is wrong, settlement is wrong. There is no second-source cross-check for SOL.
4. **Free-tier hosting is not production hosting.** Render Free can restart or sleep, and its own docs say not to use it for production. A restart means a missed tick or a delayed message, not lost money: settlement is idempotent and late-safe.
5. **Notifications are at-least-once.** A crash at the wrong moment can send one message twice. Users who blocked the bot are marked failed and not retried.
6. **JWTs last 60 minutes and cannot be revoked individually.** Banning a user works immediately anyway, because status is re-read on every request.
7. **Dependencies are not pinned** (`requirements.txt` uses `>=`). After your first successful deploy, run `pip freeze` and pin what works. Run `npm audit` and `pip-audit` yourself; I could not run them from here.
8. **Backups.** Check Supabase's backup policy for your plan; do not assume you have point-in-time recovery on the free plan.
9. **Telegram's script** (`telegram-web-app.js`) is loaded from telegram.org by design; the Mini App cannot work without it.
10. **Everything was tested by me in a sandbox with mocked or local services.** Real Telegram login, live CoinGecko/DexScreener, and real hosting are unverified until you run `DEPLOY.md` step 9.

## 5. Before inviting anyone
- [ ] `DEPLOY.md` step 9 smoke test passes, and `SOL: healthy`.
- [ ] You placed a prediction as a normal user, waited for settlement, and saw the result and the Telegram message.
- [ ] Admin -> System shows "All checks pass".
- [ ] Repo is private; `git log` and the GitHub files contain no secrets.
- [ ] You read section 1 again, and nobody is told credits are worth anything.
