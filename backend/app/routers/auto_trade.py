"""자동매매 설정/상태/이력 라우터."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.order import AutoTradeOrder
from ..services.auto_trader import AutoTradeConfig

router = APIRouter(prefix="/api/auto-trade", tags=["auto-trade"])

# 런타임 설정 (메모리 보관, 재시작 시 초기화)
_config = AutoTradeConfig()


class AutoTradeConfigRequest(BaseModel):
    enabled: bool = False
    is_virtual: bool = True
    max_quantity_per_order: int = 10
    max_amount_per_order: float = 500000
    max_daily_amount: float = 2000000
    max_daily_orders: int = 10
    max_positions: int = 5
    stop_loss_rate: float = -3.0
    take_profit_rate: float = 5.0
    trailing_stop: bool = False
    trailing_stop_rate: float = 2.0
    trade_start_time: str = "09:05"
    trade_end_time: str = "15:15"


class AutoTradeConfigResponse(BaseModel):
    enabled: bool
    is_virtual: bool
    max_quantity_per_order: int
    max_amount_per_order: float
    max_daily_amount: float
    max_daily_orders: int
    max_positions: int
    stop_loss_rate: float
    take_profit_rate: float
    trailing_stop: bool
    trailing_stop_rate: float
    trade_start_time: str
    trade_end_time: str


class AutoTradeStatus(BaseModel):
    enabled: bool
    is_virtual: bool
    daily_order_count: int
    daily_order_amount: float
    max_daily_orders: int
    max_daily_amount: float


class OrderHistoryItem(BaseModel):
    id: int
    order_id: str | None
    ticker: str
    side: str
    quantity: int
    price: float
    status: str
    broker: str
    strategy_note: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/config", response_model=AutoTradeConfigResponse)
async def get_config(_: dict = Depends(verify_token)):
    """현재 자동매매 설정 조회"""
    return AutoTradeConfigResponse(
        enabled=_config.enabled,
        is_virtual=_config.is_virtual,
        max_quantity_per_order=_config.max_quantity_per_order,
        max_amount_per_order=float(_config.max_amount_per_order),
        max_daily_amount=float(_config.max_daily_amount),
        max_daily_orders=_config.max_daily_orders,
        max_positions=_config.max_positions,
        stop_loss_rate=float(_config.stop_loss_rate),
        take_profit_rate=float(_config.take_profit_rate),
        trailing_stop=_config.trailing_stop,
        trailing_stop_rate=float(_config.trailing_stop_rate),
        trade_start_time=_config.trade_start_time,
        trade_end_time=_config.trade_end_time,
    )


@router.put("/config", response_model=AutoTradeConfigResponse)
async def update_config(
    req: AutoTradeConfigRequest,
    _: dict = Depends(verify_token),
):
    """자동매매 설정 변경"""
    global _config
    _config = AutoTradeConfig(
        enabled=req.enabled,
        is_virtual=req.is_virtual,
        max_quantity_per_order=req.max_quantity_per_order,
        max_amount_per_order=Decimal(str(req.max_amount_per_order)),
        max_daily_amount=Decimal(str(req.max_daily_amount)),
        max_daily_orders=req.max_daily_orders,
        max_positions=req.max_positions,
        stop_loss_rate=Decimal(str(req.stop_loss_rate)),
        take_profit_rate=Decimal(str(req.take_profit_rate)),
        trailing_stop=req.trailing_stop,
        trailing_stop_rate=Decimal(str(req.trailing_stop_rate)),
        trade_start_time=req.trade_start_time,
        trade_end_time=req.trade_end_time,
    )
    return await get_config(_)


@router.get("/status", response_model=AutoTradeStatus)
async def get_status(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """오늘 자동매매 현황"""
    result = await db.execute(
        text(
            "SELECT COUNT(*), COALESCE(SUM(price * quantity), 0) "
            "FROM auto_trade_orders "
            "WHERE created_at::date = CURRENT_DATE"
        )
    )
    row = result.fetchone()
    daily_count = row[0] if row else 0
    daily_amount = float(row[1]) if row else 0.0

    return AutoTradeStatus(
        enabled=_config.enabled,
        is_virtual=_config.is_virtual,
        daily_order_count=daily_count,
        daily_order_amount=daily_amount,
        max_daily_orders=_config.max_daily_orders,
        max_daily_amount=float(_config.max_daily_amount),
    )


@router.get("/orders", response_model=list[OrderHistoryItem])
async def list_orders(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """자동매매 주문 이력 조회"""
    result = await db.execute(
        select(AutoTradeOrder)
        .order_by(AutoTradeOrder.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        OrderHistoryItem(
            id=r.id,
            order_id=r.order_id,
            ticker=r.ticker,
            side=r.side,
            quantity=r.quantity,
            price=float(r.price),
            status=r.status,
            broker=r.broker,
            strategy_note=r.strategy_note,
            created_at=str(r.created_at),
        )
        for r in rows
    ]
