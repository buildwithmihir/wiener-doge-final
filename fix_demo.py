import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent

# ("s", old, new) = exact text replace      ("r", pattern, new) = regex replace
FILES = {
    # ---------------- frontend ----------------
    "frontend/src/components/Layout.tsx": [
        ("s", ">DEMO credits</span>", ">Balance</span>"),
    ],
    "frontend/src/components/MarketCard.tsx": [
        ("s", "Demo credits only \u00b7 no cash value \u00b7 settled from the price at close",
              "Settled from the price at close"),
    ],
    "frontend/src/components/StakeSheet.tsx": [
        ("s", "'Not enough demo credits.'", "'Not enough balance.'"),
        ("s", "simulated win {usd(placed.potential_payout)}", "potential win {usd(placed.potential_payout)}"),
        ("s", "Stake (DEMO credits)", "Stake ($)"),
        ("s", "Simulated win ({market.payout_multiplier}x)", "Potential win ({market.payout_multiplier}x)"),
        ("r", r'\n[ \t]*<p className="mt-3 text-center text-\[11px\] text-slate-500">\s*Demo credits only\. No cash value, not redeemable\. The payout is simulated\.\s*</p>', ""),
    ],
    "frontend/src/pages/admin/UsersAdmin.tsx": [
        ("s", " (demo credits)", ""),
    ],
    "frontend/src/pages/History.tsx": [
        ("s", "'Simulated win'", "'Potential win'"),
        ("s", 'subtitle="Your predictions. Demo credits only."', 'subtitle="Your predictions."'),
    ],
    "frontend/src/pages/Leaderboard.tsx": [
        ("s", "Demo-credit prediction rankings.", "Prediction rankings."),
    ],
    "frontend/src/pages/Profile.tsx": [
        ("s", "Sent by the bot. Messages only mention demo credits.", "Sent by the bot."),
        ("s", 'subtitle="Demo account. No real money, no cash value."', 'subtitle="Your account"'),
        ("s", "Balance (demo)", "Balance"),
        ("s", "demo credits when a friend joins", "as a bonus when a friend joins"),
    ],
    "frontend/src/pages/Vip.tsx": [
        ("s", "{usd(t.reward)}</span> demo credits", "{usd(t.reward)}</span>"),
        ("s", 'subtitle="Stake demo credits to level up. Rewards are demo credits too."',
              'subtitle="Stake to level up and earn bonuses."'),
        ("r", r'\n[ \t]*<p className="px-1 text-center text-xs text-slate-500">Demo credits only\. No cash value, not redeemable\.</p>', ""),
    ],
    "frontend/src/pages/Wallet.tsx": [
        ("s", "subtitle={live ? 'Your balance in $. Deposit or withdraw SOL or WIENER.' : 'Demo credits only. No cash value, not redeemable.'}",
              'subtitle="Your balance in $. Deposit or withdraw SOL or WIENER."'),
        ("s", '{!live && <Badge tone="demo">DEMO</Badge>}', ""),
        ("s", "Deposits and withdrawals are disabled in demo mode.", "Deposits and withdrawals are temporarily unavailable."),
    ],
    # ---------------- backend ----------------
    "backend/app/api/serialize.py": [
        ("s", "BELOW wins. Demo credits only.", "BELOW wins."),
    ],
    "backend/app/api/v1/system.py": [
        ("s", "Payments are off in this demo.", ""),
        ("s", '"currency": "DEMO credits (no cash value, not redeemable)",', '"currency": "USD",'),
    ],
    "backend/app/api/v1/payments.py": [
        ("s", "from app.services.ledger import parse_demo\n", ""),
    ],
    "backend/app/bot/handlers.py": [
        ("r", r'DEMO_NOTE = \(\n[^\n]*\n\)\n', ""),
        ("s", "create your account and get your starting DEMO credits.", "create your account."),
    ],
    "backend/app/bot/setup.py": [
        ("s", "Show your DEMO balance", "Show your balance"),
    ],
    "backend/app/core/errors.py": [
        ("s", '"Not enough demo credits."', '"Not enough balance."'),
        ("s", '"Deposits and withdrawals are disabled (demo mode)."', '"Deposits and withdrawals are currently unavailable."'),
    ],
    "backend/app/main.py": [
        ("s", 'API (demo credits only)"', 'API"'),
    ],
    "backend/app/services/ledger.py": [
        ("s", '"Welcome demo credits"', '"Welcome bonus"'),
        ("s", '"Prediction won: simulated winnings"', '"Prediction won"'),
    ],
    "backend/app/services/notifications.py": [
        ("s", 'FOOTER = "\\n\\nDemo credits only. No cash value."', 'FOOTER = ""'),
        ("s", "paid {format_demo(payout)} demo credits (stake {format_demo(stake)})", "paid ${format_demo(payout)} (stake ${format_demo(stake)})"),
        ("s", "Stake lost: {format_demo(stake)} demo credits.", "Stake lost: ${format_demo(stake)}."),
        ("s", "Your stake of {format_demo(stake)} demo credits was refunded.", "Your stake of ${format_demo(stake)} was refunded."),
        ("s", "You earned {format_demo(int(r['reward_amount']))} demo credits.", "You earned ${format_demo(int(r['reward_amount']))}."),
        ("s", "Bonus: {format_demo(int(r['reward']))} demo credits.", "Bonus: ${format_demo(int(r['reward']))}."),
    ],
}


def apply(rel, edits):
    path = ROOT / rel
    if not path.exists():
        print(f"\n!! MISSING FILE: {rel}")
        return 0
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    done = 0
    print(f"\n{rel}")
    for kind, old, new in edits:
        label = old.replace("\n", " ")[:55]
        if kind == "s":
            if old in text:
                text = text.replace(old, new)
                done += 1
                print(f"   ok    {label}")
            else:
                print(f"   skip  {label}  (not found / already done)")
        else:
            text, n = re.subn(old, new, text, flags=re.S)
            if n:
                done += 1
                print(f"   ok    {label}")
            else:
                print(f"   skip  {label}  (not found / already done)")
    if done:
        out = text.replace("\n", "\r\n") if crlf else text
        path.write_bytes(out.encode("utf-8"))
    if rel.endswith("handlers.py") and "DEMO_NOTE" in text:
        print("   !! DEMO_NOTE is still used somewhere in handlers.py: remove those uses by hand")
    return done


total = sum(apply(rel, edits) for rel, edits in FILES.items())
print(f"\nDone: {total} replacements made.")