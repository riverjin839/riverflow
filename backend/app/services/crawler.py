"""뉴스 크롤러 서비스.

네이버 금융, 한경, 매경 등에서 증시 뉴스를 수집한다.
"""

import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class NewsCrawler:
    """증시 뉴스 크롤러"""

    SOURCES = {
        "naver_finance": "https://finance.naver.com/news/mainnews.naver",
        "hankyung": "https://www.hankyung.com/finance",
    }

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "TradingSystem/1.0"},
        )

    async def crawl_naver_finance(self) -> list[dict]:
        """네이버 금융 뉴스 크롤링.

        실제 구현 시 BeautifulSoup 등으로 HTML을 파싱한다.
        """
        # TODO: 실제 크롤링 구현
        logger.info("네이버 금융 뉴스 크롤링 시작")
        return []

    async def crawl_all(self) -> list[dict]:
        """전체 소스 크롤링"""
        results = []
        results.extend(await self.crawl_naver_finance())
        return results

    async def close(self) -> None:
        await self.client.aclose()
