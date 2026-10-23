"""Request models (strict validation) + response cleaner.

Money is always an integer in base units (1 DEMO = 1,000,000). Prices are Decimal in, STRING out
(FastAPI's default encoder would turn Decimal into float, so responses go through clean())."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_BASE_UNITS = 10**15
DURATIONS = {86400, 172800, 604800, 2592000}


def clean(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "f") if obj == obj.to_integral_value() or True else str(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TelegramLogin(Strict):
    init_data: str = Field(min_length=10, max_length=4096)


class DevLogin(Strict):
    telegram_id: int = Field(gt=0, lt=10**13)
    display_name: str = Field(default="Dev User", min_length=1, max_length=64)
    username: str | None = Field(default=None, max_length=32)
    start_param: str | None = Field(default=None, max_length=64)


class PredictionIn(Strict):
    market_id: uuid.UUID
    direction: Literal["above", "below"]
    stake: int = Field(gt=0, le=MAX_BASE_UNITS, description="base units, 1 DEMO = 1,000,000")
    idempotency_key: str = Field(min_length=8, max_length=120, pattern=r"^[A-Za-z0-9_\-:.]+$")


class SettingsIn(Strict):
    leaderboard_alias: str | None = Field(default=None, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_ .\-]+$")
    hide_on_leaderboard: bool | None = None


class Reasoned(Strict):
    reason: str = Field(min_length=3, max_length=500)


class AdjustIn(Reasoned):
    amount: int = Field(ne=0, ge=-MAX_BASE_UNITS, le=MAX_BASE_UNITS)
    idempotency_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_\-:.]+$")


class UserStatusIn(Reasoned):
    status: Literal["active", "suspended", "banned"]


class RoleIn(Reasoned):
    role: Literal["moderator", "admin"]
    grant: bool


class MarketCreate(Reasoned):
    symbol: str = Field(min_length=1, max_length=16)
    duration_seconds: int
    target_price: Decimal = Field(gt=0, max_digits=38, decimal_places=12)
    opens_at: datetime
    betting_cutoff_seconds: int = Field(default=600, ge=0, le=86400)
    payout_bps: int = Field(default=18000, gt=10000, le=100000)
    min_stake: int = Field(default=1_000_000, gt=0, le=MAX_BASE_UNITS)
    max_stake: int = Field(default=1_000_000_000, gt=0, le=MAX_BASE_UNITS)
    open_now: bool = False

    @field_validator("duration_seconds")
    @classmethod
    def _dur(cls, v: int) -> int:
        if v not in DURATIONS:
            raise ValueError("duration must be 86400 (24h), 172800 (48h), 604800 (7d) or 2592000 (30d)")
        return v

    @field_validator("opens_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class MarketEdit(Reasoned):
    """Only allowed while the market is still a draft (DB enforces immutability afterwards)."""
    target_price: Decimal | None = Field(default=None, gt=0, max_digits=38, decimal_places=12)
    payout_bps: int | None = Field(default=None, gt=10000, le=100000)
    min_stake: int | None = Field(default=None, gt=0, le=MAX_BASE_UNITS)
    max_stake: int | None = Field(default=None, gt=0, le=MAX_BASE_UNITS)


class MarketStatusIn(Reasoned):
    action: Literal["open", "pause", "reopen", "close"]


class SettleIn(Reasoned):
    snapshot_id: int = Field(gt=0)


class AssetIn(Reasoned):
    is_active: bool | None = None
    is_prediction_asset: bool | None = None
    provider_ref: str | None = Field(default=None, max_length=200, pattern=r"^(id:[a-z0-9\-]+|contract:[a-z0-9\-]+:[A-Za-z0-9]+)$")


class SettingIn(Reasoned):
    value: Any


class VipTierIn(Reasoned):
    min_staked: int | None = Field(default=None, ge=0, le=MAX_BASE_UNITS)
    reward: int | None = Field(default=None, ge=0, le=MAX_BASE_UNITS)
    is_active: bool | None = None
    benefits: list[str] | None = Field(default=None, max_length=10)
