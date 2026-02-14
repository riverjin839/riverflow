"""조건 검색 스캐너 워커.

CronJob으로 장중 5분마다 실행된다.
활성화된 조건식을 순회하며 전 종목을 스캔하고,
자동매매가 연결된 조건식은 매수 신호를 발생시킨다.
"""

import asyncio
import logging
import os

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.broker_config import broker_settings
from backend.app.models.condition import SearchCondition
from backend.app.services.auto_trader import AutoTradeConfig, AutoTrader
from backend.app.services.broker.kis_broker import KISBroker
from backend.app.services.condition_engine import ConditionEngine
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def run_scan() -> None:
    """조건 검색 + 자동매매 실행"""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    broker = KISBroker(broker_settings)
    notifier = Notifier()

    async with async_session() as db:
        # 활성화된 조건식 조회
        result = await db.execute(
            select(SearchCondition).where(SearchCondition.is_active.is_(True))
        )
        conditions = result.scalars().all()
        logger.info("활성 조건식: %d개", len(conditions))

        condition_engine = ConditionEngine(broker, db)

        for cond in conditions:
            try:
                matched = await condition_engine.scan(cond.conditions)
                logger.info("조건식 [%s]: %d개 매칭", cond.name, len(matched))

                if matched:
                    await condition_engine.save_results(cond.id, matched)

                # 자동매매 연결된 경우
                if cond.auto_trade and matched:
                    trade_config = AutoTradeConfig(
                        enabled=True,
                        is_virtual=broker_settings.KIS_IS_VIRTUAL,
                        **(cond.auto_trade_config or {}),
                    )
                    trader = AutoTrader(broker, trade_config, db, notifier)

                    for stock in matched[:1]:  # 첫 번째 종목만 자동매수
                        try:
                            await trader.execute_buy(
                                stock["ticker"],
                                f"조건식 [{cond.name}] 매칭",
                            )
                        except Exception:
                            logger.exception(
                                "자동매수 실패: %s", stock.get("ticker")
                            )

            except Exception:
                logger.exception("조건식 [%s] 스캔 실패", cond.name)

    await broker.close()
    await notifier.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_scan())
