"""뉴스 크롤링 워커.

CronJob으로 2시간마다 실행된다.
뉴스를 크롤링하고 임베딩을 생성하여 DB에 저장한다.
"""

import asyncio
import logging

from backend.app.services.crawler import NewsCrawler
from backend.app.services.embedding import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def crawl_and_embed() -> None:
    """뉴스 크롤링 + 임베딩 생성"""
    logger.info("뉴스 크롤링 시작")

    crawler = NewsCrawler()
    embedding_svc = EmbeddingService()

    try:
        articles = await crawler.crawl_all()
        logger.info("크롤링된 뉴스: %d건", len(articles))

        for article in articles:
            text = f"{article.get('title', '')} {article.get('content', '')}"
            embedding = await embedding_svc.embed(text)
            article["embedding"] = embedding

        # TODO: DB 저장
        logger.info("뉴스 크롤링 + 임베딩 완료")

    finally:
        await crawler.close()
        await embedding_svc.close()


if __name__ == "__main__":
    asyncio.run(crawl_and_embed())
