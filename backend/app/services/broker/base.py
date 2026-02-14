from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Optional


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    CONDITION = "condition"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class OrderRequest:
    ticker: str
    side: OrderSide
    quantity: int
    order_type: OrderType = OrderType.LIMIT
    price: Optional[Decimal] = None
    strategy_id: Optional[str] = None


@dataclass
class OrderResult:
    order_id: str
    ticker: str
    side: OrderSide
    quantity: int
    price: Decimal
    status: str  # 'submitted' | 'filled' | 'partial' | 'rejected'
    broker: str
    message: str = ""


@dataclass
class Position:
    ticker: str
    ticker_name: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    profit_rate: Decimal
    profit_amount: Decimal


@dataclass
class AccountBalance:
    total_asset: Decimal
    cash: Decimal
    stock_value: Decimal
    profit_rate: Decimal
    positions: list[Position] = field(default_factory=list)


class BaseBroker(ABC):
    """증권사 추상 클래스"""

    @abstractmethod
    async def connect(self) -> bool:
        """API 연결 및 토큰 발급"""
        ...

    @abstractmethod
    async def get_balance(self) -> AccountBalance:
        """계좌 잔고 조회"""
        ...

    @abstractmethod
    async def get_current_price(self, ticker: str) -> dict:
        """현재가 조회"""
        ...

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult:
        """주문 실행"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        ...

    @abstractmethod
    async def get_order_history(self, date: Optional[str] = None) -> list[dict]:
        """주문 내역 조회"""
        ...

    @abstractmethod
    async def subscribe_realtime(self, tickers: list[str], callback: Callable) -> None:
        """실시간 시세 구독 (WebSocket)"""
        ...
