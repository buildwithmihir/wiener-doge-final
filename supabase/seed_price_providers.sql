-- Run ONCE in the Supabase SQL Editor (safe to re-run). Tells the worker where each price comes from.
--   SOL    -> CoinGecko, coin id "solana"
--   WIENER -> DexScreener, Solana mint (public contract address, not a secret)
-- WIENER stays "missing" (markets paused) until DexScreener shows a pool with enough liquidity.

update assets set provider_key = 'coingecko',   provider_ref = 'solana' where symbol = 'SOL';
update assets set provider_key = 'dexscreener', provider_ref = 'CceCXFy4UeXheTpf8sn1bpECxMQeH5BTyxQK4BdRMf2T' where symbol = 'WIENER';

-- The worker polls every ~10 minutes (every 1 minute near a market close). The default "stale after
-- 120 seconds" would mark every price stale between polls, so widen it.
update application_settings set value = to_jsonb(900) where key = 'price.stale_after_seconds';

select symbol, provider_key, provider_ref from assets where symbol in ('SOL','WIENER') order by symbol;
select key, value from application_settings where key like 'price.%' order by key;
