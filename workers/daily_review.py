"""장후 리뷰 워커.

CronJob으로 매일 16:00 KST에 실행된다.
당일 매매 내역을 분석하고 리뷰를 생성한다.
"""

import asyncio
import logging

from backend.app.services.llm_client import LLMClient
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def generate_daily_review() -> None:
    """장후 리뷰 생성"""
    logger.info("장후 리뷰 생성 시작")

    llm = LLMClient()
    notifier = Notifier()

    try:
        # TODO: 당일 매매 내역 조회
        # TODO: LLM으로 리뷰 생성
        # TODO: DB 저장 + 텔레그램 발송

        logger.info("장후 리뷰 생성 완료")

    finally:
        await llm.close()
        await notifier.close()


if __name__ == "__main__":
    asyncio.run(generate_daily_review())
