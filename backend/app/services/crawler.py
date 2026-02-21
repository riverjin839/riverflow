"""뉴스 크롤러 서비스.

네이버 금융, 네이버 카페 등에서 증시 뉴스를 수집한다.
"""

import logging
import os
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

    async def crawl_naver_cafe(self, club_id: str, menu_id: str) -> list[dict]:
        """네이버 카페 게시판 크롤링 (Playwright 헤드리스 브라우저).

        로그인이 필요한 게시판을 위해 Playwright를 사용한다.
        NID_AUT / NID_SES 쿠키를 환경 변수로 주입해 인증을 유지한다.

        환경 변수:
            NAVER_NID_AUT: 네이버 로그인 쿠키 NID_AUT 값
            NAVER_NID_SES: 네이버 로그인 쿠키 NID_SES 값

        Args:
            club_id: 카페 ID (숫자 문자열, 예: "10050146")
            menu_id: 게시판 메뉴 ID (숫자 문자열, 예: "5")

        Returns:
            뉴스 dict 리스트. 각 항목은 news_articles 스키마와 동일한 키를 가진다.
        """
        from playwright.async_api import async_playwright  # 런타임 임포트

        nid_aut = os.environ.get("NAVER_NID_AUT", "")
        nid_ses = os.environ.get("NAVER_NID_SES", "")
        articles: list[dict] = []

        logger.info("네이버 카페 크롤링 시작 (club=%s, menu=%s)", club_id, menu_id)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="ko-KR",
            )

            # 네이버 로그인 쿠키 주입
            if nid_aut and nid_ses:
                await context.add_cookies([
                    {"name": "NID_AUT", "value": nid_aut, "domain": ".naver.com", "path": "/"},
                    {"name": "NID_SES", "value": nid_ses, "domain": ".naver.com", "path": "/"},
                ])
                logger.info("네이버 로그인 쿠키 주입 완료")
            else:
                logger.warning("NAVER_NID_AUT / NAVER_NID_SES 미설정 — 비로그인 상태로 크롤링")

            page = await context.new_page()

            # 네이버 카페 게시글 목록 URL
            list_url = (
                f"https://cafe.naver.com/ArticleList.nhn"
                f"?search.clubid={club_id}&search.menuid={menu_id}&search.boardtype=L"
            )
            await page.goto(list_url, wait_until="domcontentloaded", timeout=30_000)

            # 네이버 카페는 iframe(cafe_main) 안에 실제 콘텐츠가 있음
            try:
                cafe_frame = page.frame("cafe_main")
                if cafe_frame is None:
                    # 최신 카페 UI는 iframe 없이 렌더링될 수 있음
                    cafe_frame = page
                await cafe_frame.wait_for_selector("table.board-list, .article-board", timeout=15_000)
            except Exception:
                logger.warning("카페 게시판 셀렉터 대기 실패 — 파싱 시도 계속")
                cafe_frame = page

            html = await cafe_frame.content()
            soup = BeautifulSoup(html, "html.parser")

            # 게시글 행 파싱 (PC 클래식/최신 UI 공통)
            rows = soup.select("table.board-list tbody tr, .article-board tbody tr")
            for row in rows:
                title_tag = row.select_one("a.article, td.td_article a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                if not title:
                    continue

                href = title_tag.get("href", "")
                if href and not href.startswith("http"):
                    href = f"https://cafe.naver.com{href}"

                author_tag = row.select_one("td.td_name .m-tcol-c, .p-nick")
                author = author_tag.get_text(strip=True) if author_tag else ""

                date_tag = row.select_one("td.td_date, .td_date")
                date_str = date_tag.get_text(strip=True) if date_tag else ""

                articles.append({
                    "title": title,
                    "content": f"작성자: {author} | 날짜: {date_str}",
                    "url": href,
                    "source": f"naver_cafe_{club_id}",
                    "keywords": [],
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                })

            await browser.close()

        logger.info("네이버 카페 크롤링 완료: %d건 (club=%s)", len(articles), club_id)
        return articles

    async def crawl_all(self) -> list[dict]:
        """전체 소스 크롤링"""
        results: list[dict] = []
        results.extend(await self.crawl_naver_finance())
        return results

    async def close(self) -> None:
        await self.client.aclose()
