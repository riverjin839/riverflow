"""과열 경고 라우터."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.broker_config import broker_settings
from ..core.database import get_db
from ..core.security import verify_token
from ..services.broker.kis_broker import KISBroker
from ..services.condition_engine import ConditionEngine

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class OverheatAlertItem(BaseModel):
    ticker: str
    name: str | None = None
    market: str | None = None
    price: int | None = None
    change_rate: float | None = None
    volume_ratio: float | None = None
    turnover_rate: float | None = None
    disparity_20d: float | None = None
    overheat_warnings: list[str] = []
    is_overheated: bool = False


class OverheatAlertResponse(BaseModel):
    total: int
    alerts: list[OverheatAlertItem]


@router.post("/overheat", response_model=OverheatAlertResponse)
async def check_overheat(
    markets: list[str] = Query(default=["KOSPI", "KOSDAQ"]),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """단기 과열 종목 감지"""
    broker = KISBroker(broker_settings)
    engine = ConditionEngine(broker, db)
    try:
        alerts = await engine.check_overheat_alerts(markets)
    finally:
        await broker.close()

    return OverheatAlertResponse(
        total=len(alerts),
        alerts=[OverheatAlertItem(**a) for a in alerts[:50]],
    )
