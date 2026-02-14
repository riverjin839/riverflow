"""장전 시황 브리핑 워커.

CronJob으로 매일 08:30 KST에 실행된다.
전일 시장 데이터를 요약하여 DB에 저장하고 텔레그램으로 발송한다.
"""

import asyncio
import logging
import sys

from backend.app.core.config import settings
from backend.app.services.llm_client import LLMClient
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def generate_morning_briefing() -> None:
    """장전 시황 브리핑 생성"""
    logger.info("장전 시황 브리핑 생성 시작")

    llm = LLMClient()
    notifier = Notifier()

    try:
        # TODO: 전일 시장 데이터 조회 (KIS API 또는 크롤링)
        # TODO: LLM으로 요약 생성
        # TODO: DB 저장
        # TODO: 텔레그램 발송

        prompt = (
            "오늘의 한국 증시 시황 브리핑을 작성해주세요. "
            "KOSPI, KOSDAQ 지수 전망, 주요 이슈, 관심 섹터를 포함해주세요."
        )
        summary = await llm.generate(
            prompt=prompt,
            system="당신은 증권 애널리스트입니다. 간결하고 핵심적인 시황 브리핑을 작성하세요.",
        )

        await notifier.send(f"[장전 브리핑]\n{summary}")
        logger.info("장전 시황 브리핑 완료")

    finally:
        await llm.close()
        await notifier.close()


if __name__ == "__main__":
    asyncio.run(generate_morning_briefing())
