"""뉴스 검색 라우터."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.news import NewsArticle
from ..services.embedding import EmbeddingService

router = APIRouter(prefix="/api/news", tags=["news"])


class NewsResponse(BaseModel):
    id: int
    source: str | None = None
    title: str | None = None
    url: str | None = None
    keywords: list[str] | None = None
    impact_score: int = 0
    theme: str | None = None
    is_leading: bool = False
    crawled_at: str

    model_config = {"from_attributes": True}


@router.get("", response_model=list[NewsResponse])
async def list_news(
    skip: int = 0,
    limit: int = 20,
    impact_min: int | None = Query(default=None, description="최소 영향도 필터"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """뉴스 목록 조회 (impact_min으로 영향도 필터링 가능)"""
    query = select(NewsArticle)
    if impact_min is not None:
        query = query.where(NewsArticle.impact_score >= impact_min)
    result = await db.execute(
        query.order_by(NewsArticle.crawled_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/search")
async def search_news(
    q: str = Query(..., description="검색어"),
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """벡터 유사도 기반 뉴스 검색"""
    embedding_svc = EmbeddingService()
    try:
        query_vec = await embedding_svc.embed(q)
    finally:
        await embedding_svc.close()

    result = await db.execute(
        text(
            "SELECT id, title, url, source, "
            "1 - (embedding <=> :vec::vector) AS similarity "
            "FROM news_articles "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> :vec::vector "
            "LIMIT :lim"
        ),
        {"vec": str(query_vec), "lim": limit},
    )
    rows = result.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "url": r[2],
            "source": r[3],
            "similarity": round(float(r[4]), 4),
        }
        for r in rows
    ]
