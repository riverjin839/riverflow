"""뉴스 크롤링 워커.

CronJob으로 2시간마다 실행된다.
뉴스를 크롤링하고 임베딩을 생성하여 DB에 저장한다.
LLM으로 뉴스 영향도/테마/주도성을 분석하여 함께 저장한다.
"""

import asyncio
import logging
import os

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.services.crawler import NewsCrawler
from backend.app.services.embedding import EmbeddingService
from backend.app.services.llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def crawl_and_embed() -> None:
    """뉴스 크롤링 + LLM 분석 + 임베딩 생성 + DB 저장"""
    logger.info("뉴스 크롤링 시작")

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    crawler = NewsCrawler()
    embedding_svc = EmbeddingService()
    llm = LLMClient()

    try:
        articles = await crawler.crawl_all()
        logger.info("크롤링된 뉴스: %d건", len(articles))

        if not articles:
            logger.info("크롤링된 뉴스 없음. 종료.")
            return

        for article in articles:
            # 임베딩 생성
            text_for_embed = f"{article.get('title', '')} {article.get('content', '')}"
            try:
                embedding = await embedding_svc.embed(text_for_embed)
                article["embedding"] = embedding
            except Exception:
                logger.warning("임베딩 생성 실패: %s", article.get("title", "")[:50])
                article["embedding"] = None

            # LLM 뉴스 분석 (영향도/테마/주도성)
            try:
                analysis = await llm.analyze_news(
                    title=article.get("title", ""),
                    content=article.get("content", ""),
                )
                article["impact_score"] = analysis["impact_score"]
                article["theme"] = analysis["theme"]
                article["is_leading"] = analysis["is_leading"]
            except Exception:
                logger.warning("LLM 분석 실패: %s", article.get("title", "")[:50])
                article["impact_score"] = 1
                article["theme"] = ""
                article["is_leading"] = False

        # DB 저장
        async with async_session() as db:
            saved_count = 0
            for article in articles:
                # 중복 체크 (URL 기준)
                url = article.get("url", "")
                if url:
                    existing = await db.execute(
                        sql_text("SELECT id FROM news_articles WHERE url = :url"),
                        {"url": url},
                    )
                    if existing.fetchone():
                        logger.debug("중복 뉴스 스킵: %s", url)
                        continue

                embedding = article.get("embedding")
                await db.execute(
                    sql_text(
                        "INSERT INTO news_articles "
                        "(source, title, content, url, keywords, embedding, "
                        "impact_score, theme, is_leading) "
                        "VALUES (:source, :title, :content, :url, :keywords, :embedding, "
                        ":impact_score, :theme, :is_leading)"
                    ),
                    {
                        "source": article.get("source", ""),
                        "title": article.get("title", ""),
                        "content": article.get("content", ""),
                        "url": url,
                        "keywords": article.get("keywords", []),
                        "embedding": str(embedding) if embedding else None,
                        "impact_score": article.get("impact_score", 1),
                        "theme": article.get("theme", ""),
                        "is_leading": article.get("is_leading", False),
                    },
                )
                saved_count += 1

            await db.commit()
            logger.info("뉴스 %d건 DB 저장 완료", saved_count)

        logger.info("뉴스 크롤링 + LLM 분석 + 임베딩 완료")

    finally:
        await crawler.close()
        await embedding_svc.close()
        await llm.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(crawl_and_embed())
