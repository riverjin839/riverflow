"""장후 리뷰 워커.

CronJob으로 매일 16:00 KST에 실행된다.
당일 매매 내역을 분석하고 리뷰를 생성한다.
"""

import asyncio
import logging
import os
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.llm_client import LLMClient
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def generate_daily_review() -> None:
    """장후 리뷰 생성"""
    logger.info("장후 리뷰 생성 시작")

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    llm = LLMClient()
    notifier = Notifier()

    try:
        async with async_session() as db:
            # 1. 당일 매매 내역 조회
            result = await db.execute(
                text(
                    "SELECT ticker, side, quantity, price, status, strategy_note, created_at "
                    "FROM auto_trade_orders "
                    "WHERE created_at::date = CURRENT_DATE "
                    "ORDER BY created_at"
                )
            )
            orders = result.fetchall()

            # 2. 당일 매매일지 조회
            journal_result = await db.execute(
                text(
                    "SELECT ticker, ticker_name, buy_price, sell_price, quantity, "
                    "profit_rate, buy_reason "
                    "FROM trade_journal "
                    "WHERE trade_date = CURRENT_DATE"
                )
            )
            journals = journal_result.fetchall()

            if not orders and not journals:
                logger.info("오늘 매매 내역 없음. 리뷰 생략.")
                return

            # 3. LLM 프롬프트 구성
            trade_summary = f"날짜: {date.today().isoformat()}\n\n"

            if orders:
                trade_summary += "## 자동매매 주문\n"
                for o in orders:
                    trade_summary += (
                        f"- {o[0]} {o[1]} {o[2]}주 @ {o[3]}원 "
                        f"(상태: {o[4]}, 사유: {o[5]})\n"
                    )

            if journals:
                trade_summary += "\n## 매매일지\n"
                for j in journals:
                    profit = f"{j[5]}%" if j[5] else "미확정"
                    trade_summary += (
                        f"- {j[0]}({j[1]}) 매수 {j[2]}원 -> 매도 {j[3]}원, "
                        f"{j[4]}주, 수익률 {profit}, 사유: {j[6]}\n"
                    )

            review = await llm.generate(
                prompt=f"다음 매매 내역을 분석하여 장후 리뷰를 작성해주세요:\n\n{trade_summary}",
                system=(
                    "당신은 증권 트레이딩 코치입니다. "
                    "매매 내역을 분석하여 잘한 점, 개선할 점, 내일 전략을 제안하세요. "
                    "간결하고 실용적으로 작성하세요."
                ),
            )

            # 4. DB 저장
            await db.execute(
                text(
                    "INSERT INTO market_briefing (briefing_type, raw_data, summary) "
                    "VALUES ('daily_review', :raw_data::jsonb, :summary)"
                ),
                {
                    "raw_data": f'{{"order_count": {len(orders)}, "journal_count": {len(journals)}}}',
                    "summary": review,
                },
            )
            await db.commit()

            # 5. 텔레그램 발송
            await notifier.send(f"[장후 리뷰]\n{review}")

            logger.info("장후 리뷰 생성 완료")

    finally:
        await llm.close()
        await notifier.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(generate_daily_review())
