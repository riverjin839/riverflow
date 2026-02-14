"""키움 브릿지 서버 경유 구현체.

키움 OpenAPI+는 Windows OCX 전용이므로, 별도 Windows 환경에서
브릿지 서버(Flask/FastAPI)를 띄우고 K8s에서 HTTP로 호출한다.

구조:
    [K8s Pod] --HTTP--> [Windows PC/VM]
                         ├── kiwoom-bridge (FastAPI)
                         └── 키움 OpenAPI+ (OCX)
"""

import logging
from decimal import Decimal
from typing import Callable, Optional

import httpx

from ...core.broker_config import BrokerSettings
from .base import (
    AccountBalance,
    BaseBroker,
    OrderRequest,
    OrderResult,
    OrderSide,
    Position,
)

logger = logging.getLogger(__name__)


class KiwoomBridgeBroker(BaseBroker):
    """키움 브릿지 서버 경유 구현"""

    def __init__(self, settings: BrokerSettings):
        self.bridge_url = settings.KIWOOM_BRIDGE_URL
        self.bridge_token = settings.KIWOOM_BRIDGE_TOKEN
        self.client = httpx.AsyncClient(timeout=30.0)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.bridge_token}"}

    async def connect(self) -> bool:
        """브릿지 서버 연결 확인"""
        resp = await self.client.get(
            f"{self.bridge_url}/api/health", headers=self._headers()
        )
        resp.raise_for_status()
        logger.info("키움 브릿지 서버 연결 확인 완료")
        return True

    async def get_balance(self) -> AccountBalance:
        """잔고 조회"""
        resp = await self.client.get(
            f"{self.bridge_url}/api/balance", headers=self._headers()
        )
        resp.raise_for_status()
        data = resp.json()

        positions = [
            Position(
                ticker=p["ticker"],
                ticker_name=p.get("ticker_name", ""),
                quantity=p["quantity"],
                avg_price=Decimal(str(p["avg_price"])),
                current_price=Decimal(str(p["current_price"])),
                profit_rate=Decimal(str(p.get("profit_rate", 0))),
                profit_amount=Decimal(str(p.get("profit_amount", 0))),
            )
            for p in data.get("positions", [])
        ]

        return AccountBalance(
            total_asset=Decimal(str(data["total_asset"])),
            cash=Decimal(str(data["cash"])),
            stock_value=Decimal(str(data["stock_value"])),
            profit_rate=Decimal(str(data.get("profit_rate", 0))),
            positions=positions,
        )

    async def get_current_price(self, ticker: str) -> dict:
        """현재가 조회"""
        resp = await self.client.get(
            f"{self.bridge_url}/api/price/{ticker}", headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """주문 실행"""
        resp = await self.client.post(
            f"{self.bridge_url}/api/order",
            json={
                "ticker": order.ticker,
                "side": order.side.value,
                "quantity": order.quantity,
                "order_type": order.order_type.value,
                "price": str(order.price) if order.price else None,
                "strategy_id": order.strategy_id,
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json()

        return OrderResult(
            order_id=data["order_id"],
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=Decimal(str(data.get("price", order.price or 0))),
            status=data.get("status", "submitted"),
            broker="kiwoom",
            message=data.get("message", ""),
        )

    async def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        resp = await self.client.post(
            f"{self.bridge_url}/api/order/{order_id}/cancel",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json().get("success", False)

    async def get_order_history(self, date: Optional[str] = None) -> list[dict]:
        """주문 내역 조회"""
        params = {"date": date} if date else {}
        resp = await self.client.get(
            f"{self.bridge_url}/api/orders",
            params=params,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json().get("orders", [])

    async def subscribe_realtime(self, tickers: list[str], callback: Callable) -> None:
        """실시간 시세 구독은 브릿지 서버 WebSocket으로 처리"""
        raise NotImplementedError(
            "키움 실시간 시세는 브릿지 서버의 WebSocket을 통해 구독합니다."
        )

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
