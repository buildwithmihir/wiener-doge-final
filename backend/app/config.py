"""Application settings loaded from environment variables / backend/.env.

Safe by default: dev auth is OFF unless explicitly enabled, and production mode
refuses to start with placeholder secrets, wildcard CORS, or dev auth on.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_PREFIXES = ("CHANGE_ME", "PASTE_", "YOUR_")


def _is_placeholder(value: str) -> bool:
    return not value or value.upper().startswith(PLACEHOLDER_PREFIXES)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # app
    app_env: Literal["development", "production", "test"] = "development"
    app_name: str = "WienerDoge"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # database
    database_url: str = ""
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)

    # auth
    jwt_secret: str = ""
    jwt_expire_minutes: int = Field(default=60, ge=5, le=1440)
    dev_auth_enabled: bool = False

    # telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_initdata_max_age_seconds: int = Field(default=3600, ge=30, le=86400)
    mini_app_url: str = ""
    admin_telegram_ids: str = ""

    # web
    cors_origins: str = "http://localhost:5173"

    # price provider
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""
    coingecko_sol_id: str = "solana"
    dexscreener_base_url: str = "https://api.dexscreener.com"
    dex_min_liquidity_usd: int = 20000        # a pool thinner than this is not trusted for settlement
    dex_max_divergence_bps: int = 1000        # two deep pools disagreeing by more than 10% => no price
    wiener_mint_address: str = ""
    price_poll_seconds: int = Field(default=60, ge=15, le=3600)

    # worker / scheduler
    worker_enabled: bool = True
    # Shared secret the scheduler sends in the X-Tick-Secret header to call /internal/tick
    tick_secret: str = ""

    # ---- derived helpers -------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_telegram_id_set(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return ids

    # ---- validation ------------------------------------------------------
    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        problems: list[str] = []

        if self.database_url and not self.database_url.startswith("postgresql+psycopg://"):
            problems.append("DATABASE_URL must start with 'postgresql+psycopg://'")

        if "*" in self.cors_origins_list:
            problems.append("CORS_ORIGINS must not contain '*'")

        try:
            _ = self.admin_telegram_id_set
        except ValueError:
            problems.append("ADMIN_TELEGRAM_IDS must be comma-separated integers")

        if len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be at least 32 characters")

        if self.is_production:
            if self.dev_auth_enabled:
                problems.append("DEV_AUTH_ENABLED must be false in production")
            if _is_placeholder(self.jwt_secret):
                problems.append("JWT_SECRET is still a placeholder")
            if _is_placeholder(self.telegram_bot_token):
                problems.append("TELEGRAM_BOT_TOKEN is missing or a placeholder")
            if len(self.tick_secret) < 32 or _is_placeholder(self.tick_secret):
                problems.append("TICK_SECRET must be at least 32 characters in production")
            if _is_placeholder(self.telegram_webhook_secret):
                problems.append("TELEGRAM_WEBHOOK_SECRET is missing or a placeholder")
            if not self.database_url or "YOUR_DB_PASSWORD" in self.database_url:
                problems.append("DATABASE_URL is missing or a placeholder")
            if not self.mini_app_url.startswith("https://"):
                problems.append("MINI_APP_URL must be an https URL in production")
            if any(not o.startswith("https://") for o in self.cors_origins_list):
                problems.append("CORS_ORIGINS must all be https in production")

        if problems:
            raise ValueError("Invalid configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
