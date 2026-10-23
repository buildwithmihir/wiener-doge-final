"""WienerDoge API entry point.   Run locally:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, growth, markets, predictions, system, telegram, wallet
from app.core.logging_safety import quiet_http_loggers
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import setup_rate_limiting


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    registry = getattr(app.state, "registry", None)
    if registry is not None:
        registry.close_all()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    quiet_http_loggers()
    app = FastAPI(
        title=f"{settings.app_name} API (demo credits only)",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,                      # we use a Bearer header, not cookies
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        max_age=600,
    )
    setup_rate_limiting(app)
    register_exception_handlers(app)
    for module in (system, auth, wallet, markets, predictions, growth, admin, telegram):
        app.include_router(module.router, prefix=settings.api_prefix)
    return app


app = create_app()
