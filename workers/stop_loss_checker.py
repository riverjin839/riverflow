"""손절/익절 체크 워커.

CronJob으로 장중 1분마다 실행된다.
보유 종목의 수익률을 확인하고 손절/익절 조건에 해당하면 자동 매도한다.
"""

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.broker_config import broker_settings
from backend.app.services.auto_trader import AutoTradeConfig, AutoTrader
from backend.app.services.broker.kis_broker import KISBroker
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def check_stop_loss() -> None:
    """보유 종목 손절/익절 체크"""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    broker = KISBroker(broker_settings)
    notifier = Notifier()

    # TODO: 설정을 DB 또는 ConfigMap에서 읽어오기
    config = AutoTradeConfig(enabled=True, is_virtual=broker_settings.KIS_IS_VIRTUAL)

    async with async_session() as db:
        trader = AutoTrader(broker, config, db, notifier)

        try:
            results = await trader.check_stop_loss()
            if results:
                logger.info("손절/익절 실행: %d건", len(results))
            else:
                logger.debug("손절/익절 해당 없음")
        except Exception:
            logger.exception("손절/익절 체크 실패")

    await broker.close()
    await notifier.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_stop_loss())
