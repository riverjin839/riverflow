"""증권사 계좌 연동 라우터 - 잔고 조회, 현재가, 주문 내역."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..core.broker_config import broker_settings
from ..core.security import verify_token
from ..services.broker.kis_broker import KISBroker

router = APIRouter(prefix="/api/broker", tags=["broker"])


def _get_broker() -> KISBroker:
    return KISBroker(broker_settings)


class PositionResponse(BaseModel):
    ticker: str
    ticker_name: str
    quantity: int
    avg_price: float
    current_price: float
    profit_rate: float
    profit_amount: float


class BalanceResponse(BaseModel):
    total_asset: float
    cash: float
    stock_value: float
    profit_rate: float
    positions: list[PositionResponse]
    is_virtual: bool


class PriceResponse(BaseModel):
    ticker: str
    current_price: int
    change_rate: float
    volume: int
    high: int
    low: int
    open: int


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(_: dict = Depends(verify_token)):
    """계좌 잔고 조회"""
    broker = _get_broker()
    try:
        balance = await broker.get_balance()
        return BalanceResponse(
            total_asset=float(balance.total_asset),
            cash=float(balance.cash),
            stock_value=float(balance.stock_value),
            profit_rate=float(balance.profit_rate),
            positions=[
                PositionResponse(
                    ticker=p.ticker,
                    ticker_name=p.ticker_name,
                    quantity=p.quantity,
                    avg_price=float(p.avg_price),
                    current_price=float(p.current_price),
                    profit_rate=float(p.profit_rate),
                    profit_amount=float(p.profit_amount),
                )
                for p in balance.positions
            ],
            is_virtual=broker_settings.KIS_IS_VIRTUAL,
        )
    finally:
        await broker.close()


@router.get("/price/{ticker}", response_model=PriceResponse)
async def get_price(
    ticker: str,
    _: dict = Depends(verify_token),
):
    """현재가 조회"""
    broker = _get_broker()
    try:
        price = await broker.get_current_price(ticker)
        return PriceResponse(**price)
    finally:
        await broker.close()


@router.get("/orders")
async def get_orders(
    date: str | None = Query(None, description="조회일자 YYYYMMDD"),
    _: dict = Depends(verify_token),
):
    """주문 내역 조회"""
    broker = _get_broker()
    try:
        orders = await broker.get_order_history(date)
        return {"orders": orders}
    finally:
        await broker.close()
