"""Trading System FastAPI 애플리케이션."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.database import async_session
from .core.migration import run_migrations
from .routers import (
    ai,
    alert,
    auth,
    auto_trade,
    briefing,
    broker,
    condition,
    journal,
    market,
    news,
    sector,
    settings,
    supply,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 마이그레이션 + 브로커 설정 로드."""
    async with async_session() as session:
        try:
            await run_migrations(session)
        except Exception as e:
            logger.error("마이그레이션 실패: %s", e)

        try:
            from .routers.settings import load_broker_settings_from_db
            await load_broker_settings_from_db(session)
        except Exception as e:
            logger.warning("브로커 설정 로드 실패: %s", e)

    yield


app = FastAPI(
    title="Trading System API",
    description="K8s 기반 트레이딩 시스템 백엔드",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://trading.local",
        "https://trading.local",
        "http://trading.local:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(journal.router)
app.include_router(briefing.router)
app.include_router(news.router)
app.include_router(ai.router)
app.include_router(broker.router)
app.include_router(condition.router)
app.include_router(auto_trade.router)
app.include_router(sector.router)
app.include_router(alert.router)
app.include_router(supply.router)
app.include_router(market.router)
app.include_router(settings.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
