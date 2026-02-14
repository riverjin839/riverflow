"""자동매매 실행 엔진.

안전장치가 핵심이다. 모든 주문은 다중 체크를 통과해야 실행된다.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .broker.base import BaseBroker, OrderRequest, OrderResult, OrderSide, OrderType
from .notifier import Notifier

logger = logging.getLogger(__name__)


class TradingError(Exception):
    """자동매매 관련 기본 예외"""


class TradingDisabledError(TradingError):
    pass


class TradingHoursError(TradingError):
    pass


class DailyLimitError(TradingError):
    pass


class PositionLimitError(TradingError):
    pass


class InsufficientFundsError(TradingError):
    pass


@dataclass
class AutoTradeConfig:
    """자동매매 안전 설정"""

    enabled: bool = False
    is_virtual: bool = True  # 기본값: 모의투자

    # 주문 제한
    max_quantity_per_order: int = 10
    max_amount_per_order: Decimal = Decimal("500000")
    max_daily_amount: Decimal = Decimal("2000000")
    max_daily_orders: int = 10
    max_positions: int = 5

    # 손절/익절
    stop_loss_rate: Decimal = Decimal("-3.0")
    take_profit_rate: Decimal = Decimal("5.0")
    trailing_stop: bool = False
    trailing_stop_rate: Decimal = Decimal("2.0")

    # 시간 제한
    trade_start_time: str = "09:05"
    trade_end_time: str = "15:15"
    no_trade_first_minutes: int = 5


class AutoTrader:
    """자동매매 실행 엔진"""

    def __init__(
        self,
        broker: BaseBroker,
        config: AutoTradeConfig,
        db: AsyncSession,
        notifier: Notifier,
    ):
        self.broker = broker
        self.config = config
        self.db = db
        self.notifier = notifier
        self.daily_order_count = 0
        self.daily_order_amount = Decimal("0")

    def _is_trading_hours(self) -> bool:
        """현재 시각이 매매 가능 시간인지 확인 (KST 기준)"""
        now = datetime.now(timezone.utc)
        # UTC+9 = KST
        kst_hour = (now.hour + 9) % 24
        kst_minute = now.minute

        start_parts = self.config.trade_start_time.split(":")
        end_parts = self.config.trade_end_time.split(":")
        start = time(int(start_parts[0]), int(start_parts[1]))
        end = time(int(end_parts[0]), int(end_parts[1]))
        current = time(kst_hour, kst_minute)

        return start <= current <= end

    async def execute_buy(self, ticker: str, reason: str) -> OrderResult:
        """매수 실행 (모든 안전장치 통과 후)"""

        # 1. 기본 체크
        if not self.config.enabled:
            raise TradingDisabledError("자동매매가 비활성화 상태")

        if not self._is_trading_hours():
            raise TradingHoursError("매매 가능 시간이 아님")

        # 2. 일일 한도 체크
        if self.daily_order_count >= self.config.max_daily_orders:
            await self.notifier.alert(
                f"일일 주문 횟수 한도 도달: {self.daily_order_count}"
            )
            raise DailyLimitError("일일 주문 횟수 초과")

        if self.daily_order_amount >= self.config.max_daily_amount:
            await self.notifier.alert(
                f"일일 주문 금액 한도 도달: {self.daily_order_amount}"
            )
            raise DailyLimitError("일일 주문 금액 초과")

        # 3. 보유 종목 수 체크
        balance = await self.broker.get_balance()
        if len(balance.positions) >= self.config.max_positions:
            raise PositionLimitError("최대 보유 종목 수 초과")

        # 4. 현재가 조회 및 주문 금액 계산
        price_info = await self.broker.get_current_price(ticker)
        current_price = Decimal(str(price_info["current_price"]))

        max_qty_by_amount = int(self.config.max_amount_per_order / current_price)
        quantity = min(self.config.max_quantity_per_order, max_qty_by_amount)

        if quantity <= 0:
            raise InsufficientFundsError("주문 가능 수량 없음")

        order_amount = current_price * quantity

        # 5. 주문 실행
        order = OrderRequest(
            ticker=ticker,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=current_price,
            strategy_id=reason,
        )

        result = await self.broker.place_order(order)

        # 6. 기록 및 알림
        self.daily_order_count += 1
        self.daily_order_amount += order_amount

        await self._save_order_record(result, reason)

        mode = "모의투자" if self.config.is_virtual else "실전"
        await self.notifier.send(
            f"[매수 주문]\n"
            f"종목: {ticker}\n"
            f"수량: {quantity}주\n"
            f"가격: {current_price:,}원\n"
            f"사유: {reason}\n"
            f"모드: {mode}"
        )

        return result

    async def execute_sell(self, ticker: str, reason: str) -> OrderResult:
        """매도 실행"""
        if not self.config.enabled:
            raise TradingDisabledError("자동매매가 비활성화 상태")

        # 보유 종목에서 수량 확인
        balance = await self.broker.get_balance()
        position = None
        for p in balance.positions:
            if p.ticker == ticker:
                position = p
                break

        if position is None or position.quantity <= 0:
            raise InsufficientFundsError(f"{ticker}: 보유 수량 없음")

        price_info = await self.broker.get_current_price(ticker)
        current_price = Decimal(str(price_info["current_price"]))

        order = OrderRequest(
            ticker=ticker,
            side=OrderSide.SELL,
            quantity=position.quantity,
            order_type=OrderType.LIMIT,
            price=current_price,
            strategy_id=reason,
        )

        result = await self.broker.place_order(order)

        await self._save_order_record(result, reason)

        mode = "모의투자" if self.config.is_virtual else "실전"
        await self.notifier.send(
            f"[매도 주문]\n"
            f"종목: {ticker}\n"
            f"수량: {position.quantity}주\n"
            f"가격: {current_price:,}원\n"
            f"사유: {reason}\n"
            f"모드: {mode}"
        )

        return result

    async def check_stop_loss(self) -> list[OrderResult]:
        """보유 종목 손절/익절 체크"""
        results = []
        balance = await self.broker.get_balance()

        for position in balance.positions:
            profit_rate = position.profit_rate

            if profit_rate <= self.config.stop_loss_rate:
                result = await self.execute_sell(
                    position.ticker,
                    f"손절 발동: {profit_rate}% (기준: {self.config.stop_loss_rate}%)",
                )
                results.append(result)

            elif profit_rate >= self.config.take_profit_rate:
                result = await self.execute_sell(
                    position.ticker,
                    f"익절 발동: {profit_rate}% (기준: {self.config.take_profit_rate}%)",
                )
                results.append(result)

        return results

    async def _save_order_record(self, result: OrderResult, reason: str) -> None:
        """주문 기록을 DB에 저장"""
        await self.db.execute(
            text(
                "INSERT INTO auto_trade_orders "
                "(order_id, ticker, side, quantity, price, status, broker, strategy_note) "
                "VALUES (:oid, :ticker, :side, :qty, :price, :status, :broker, :note)"
            ),
            {
                "oid": result.order_id,
                "ticker": result.ticker,
                "side": result.side.value,
                "qty": result.quantity,
                "price": float(result.price),
                "status": result.status,
                "broker": result.broker,
                "note": reason,
            },
        )
        await self.db.commit()

    def reset_daily_counters(self) -> None:
        """일일 카운터 초기화 (매일 장 시작 전 호출)"""
        self.daily_order_count = 0
        self.daily_order_amount = Decimal("0")
