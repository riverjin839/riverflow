"""섹터 분석 라우터."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.broker_config import broker_settings
from ..core.database import get_db
from ..core.security import verify_token
from ..services.broker.kis_broker import KISBroker
from ..services.condition_engine import ConditionEngine

router = APIRouter(prefix="/api/sectors", tags=["sectors"])


class TopStock(BaseModel):
    ticker: str | None = None
    name: str | None = None
    change_rate: float | None = None
    volume_ratio: float | None = None
    price: float | None = None


class SectorAnalysisItem(BaseModel):
    sector_name: str
    market: str
    stock_count: int
    top3_avg_change_rate: float
    sector_volume_ratio: float
    is_leading: bool
    leader_ticker: str
    leader_name: str
    leader_change_rate: float
    top_stocks: list[TopStock]


class SectorAnalysisResponse(BaseModel):
    total: int
    leading_count: int
    sectors: list[SectorAnalysisItem]


@router.post("/analyze", response_model=SectorAnalysisResponse)
async def analyze_sectors(
    markets: list[str] = Query(default=["KOSPI", "KOSDAQ"]),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """섹터 강세 분석 실행 (KIS API 실시간 조회)"""
    broker = KISBroker(broker_settings)
    engine = ConditionEngine(broker, db)
    try:
        results = await engine.analyze_sectors(markets)
    finally:
        await broker.close()

    return SectorAnalysisResponse(
        total=len(results),
        leading_count=sum(1 for r in results if r["is_leading"]),
        sectors=[SectorAnalysisItem(**r) for r in results[:20]],
    )


@router.get("/latest", response_model=list[dict])
async def get_latest_sectors(
    limit: int = Query(default=20, le=50),
    leading_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """최근 섹터 분석 결과 조회 (DB)"""
    query = (
        "SELECT id, sector_code, sector_name, market, "
        "top3_avg_change_rate, sector_volume_ratio, is_leading, "
        "leader_ticker, leader_name, leader_change_rate, "
        "details, analyzed_at "
        "FROM sector_analysis "
    )
    if leading_only:
        query += "WHERE is_leading = true "
    query += "ORDER BY analyzed_at DESC LIMIT :limit"

    try:
        result = await db.execute(text(query), {"limit": limit})
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        await db.rollback()
        return []
