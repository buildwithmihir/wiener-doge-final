// Shapes returned by the WienerDoge API. Money and prices arrive as TEXT so no precision is lost.

export interface Money {
  units: string // base units, 1 DEMO = 1,000,000
  demo: string // display amount, e.g. "12.5"
}

export interface Wallet {
  available: Money
  reserved: Money
  total: Money
}

export interface User {
  id: string
  display_name: string
  username: string | null
  roles: string[]
  is_admin: boolean
}

export interface Session {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  new_user: boolean
  user: User
  wallet: Wallet
}

export type MarketStatus = 'draft' | 'open' | 'paused' | 'closed' | 'settling' | 'settled' | 'voided'

export interface Market {
  id: string
  symbol: string
  asset_name: string
  duration_seconds: number
  target_price: string
  opens_at: string
  betting_closes_at: string
  closes_at: string
  status: MarketStatus
  payout_multiplier: string
  min_stake: Money
  max_stake: Money
  betting_closes_in_seconds: number
  closes_in_seconds: number
  paused_by_feed: boolean
  pause_reason: string | null
  last_price: string | null
  price_source: string | null
  price_updated_at: string | null
  feed_ok: boolean
  result: 'above' | 'below' | 'void' | null
  settle_price: string | null
  settled_at: string | null
  rule: string
  // Market interface me add:
  odds_above: string
  odds_below: string


}

export type PredictionStatus = 'open' | 'won' | 'lost' | 'refunded'
export interface AssetRow {
  symbol: string
  name: string
  last_price: string | null
  change_pct: string | null
  open_markets: number
}
export interface Prediction {
  id: string
  market_id: string
  symbol: string
  duration_seconds: number
  direction: 'above' | 'below'
  stake: Money
  target_price: string
  payout_multiplier: string
  potential_payout: Money
  status: PredictionStatus
  payout: Money
  created_at: string
  closes_at: string
  settled_at: string | null
  market_result: 'above' | 'below' | 'void' | null
  settle_price: string | null
}

export interface WalletEvent {
  id: string
  kind: string
  title: string
  created_at: string
  available_change: Money
  reserved_change: Money
  net_change: Money
  ref_type: string | null
  ref_id: string | null
  cursor: number
}

export interface PublicConfig {
  demo_mode: boolean
  payments_enabled: boolean
  currency: string
  settlement_rule: string
  durations_seconds: number[]
}

export type ChartRange = '1h' | '6h' | '24h' | '7d'

export interface ChartResponse {
  symbol: string
  range: ChartRange
  points: { t: string; price: string }[]
  change: { abs: string; pct: string } | null
  source: string | null
}

export interface VipTier {
  id: number
  name: string
  min_staked: Money
  reward: Money
  benefits: string[]
  unlocked: boolean
  achieved_at: string | null
  reward_paid: boolean
}

export interface VipResponse {
  total_staked: Money
  tiers: VipTier[]
  current: VipTier | null
  next: VipTier | null
  remaining_to_next: Money | null
}

export interface ProfileResponse {
  user: { id: string; display_name: string; username: string | null; member_since: string }
  stats: { settled: number; wins: number; open: number; staked: Money; accuracy_pct: number | null }
  vip: { current: VipTier | null }
  referral: {
    code: string
    total: number
    pending: number
    rewarded: number
    earned: Money
    reward_per_referral: Money
    already_referred: boolean
  }
  privacy: { leaderboard_alias: string | null; hide_on_leaderboard: boolean }
}

export type LeaderboardMetric = 'accuracy' | 'wagered'
export type LeaderboardPeriod = 'all' | 'weekly' | 'monthly'

export interface LeaderboardRow {
  rank: number
  alias: string
  settled: number
  wins: number
  staked: Money
  won_total: Money
  accuracy_pct: number | null
  is_me: boolean
}

export interface LeaderboardResponse {
  metric: LeaderboardMetric
  period: LeaderboardPeriod
  min_settled: number
  items: LeaderboardRow[]
  me: LeaderboardRow | null
}

export interface AdminMarket extends Market {
  admin_pause_reason: string | null
}

export interface AdminUserInfo {
  id: string
  telegram_id: number
  username: string | null
  display_name: string
  status: string
  created_at: string
  last_seen_at: string | null
  wallet: Wallet
}

export interface AuditItem {
  id: number
  actor_user_id: string | null
  actor_type: string
  action: string
  entity_type: string | null
  entity_id: string | null
  reason: string | null
  created_at: string
}

export interface NotificationPrefs {
  market_results: boolean
  market_closing: boolean
  referrals: boolean
  vip: boolean
}
