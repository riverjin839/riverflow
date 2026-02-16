"""뉴스 크롤러 서비스.

네이버 금융 등에서 증시 뉴스를 수집한다.
"""

import logging
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class NewsCrawler:
    """증시 뉴스 크롤러"""

    NAVER_FINANCE_URL = "https://finance.naver.com/news/mainnews.naver"
    NAVER_NEWS_BASE = "https://finance.naver.com"

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            },
            follow_redirects=True,
        )

    async def crawl_naver_finance(self) -> list[dict]:
        """네이버 금융 메인 뉴스 크롤링."""
        logger.info("네이버 금융 뉴스 크롤링 시작")
        articles: list[dict] = []

        try:
            resp = await self.client.get(self.NAVER_FINANCE_URL)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            news_list = soup.select("li.block1")

            for item in news_list:
                link_tag = item.select_one("a")
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{self.NAVER_NEWS_BASE}{href}"

                summary_tag = item.select_one(".summary")
                summary = summary_tag.get_text(strip=True) if summary_tag else ""

                source_tag = item.select_one(".press")
                source = source_tag.get_text(strip=True) if source_tag else "naver_finance"

                articles.append({
                    "title": title,
                    "content": summary,
                    "url": href,
                    "source": source,
                    "keywords": [],
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                })

            logger.info("네이버 금융 뉴스 %d건 크롤링 완료", len(articles))

        except Exception:
            logger.exception("네이버 금융 뉴스 크롤링 실패")

        return articles

    async def crawl_all(self) -> list[dict]:
        """전체 소스 크롤링"""
        results: list[dict] = []
        results.extend(await self.crawl_naver_finance())
        return results

    async def close(self) -> None:
        await self.client.aclose()
