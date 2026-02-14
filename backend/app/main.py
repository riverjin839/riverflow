"""Trading System FastAPI 애플리케이션."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import ai, auth, auto_trade, briefing, broker, condition, journal, news

app = FastAPI(
    title="Trading System API",
    description="K8s 기반 트레이딩 시스템 백엔드",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS (로컬 개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://trading.local"],
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


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
