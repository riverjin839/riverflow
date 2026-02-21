"""뉴스 검색 라우터."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.news import NewsArticle
from ..services.embedding import EmbeddingService

router = APIRouter(prefix="/api/news", tags=["news"])

_INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "change-me-internal")


def verify_internal_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """내부 서비스(브릿지, 워커) 전용 API Key 검증"""
    if x_api_key != _INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class NewsIngestRequest(BaseModel):
    source: str
    title: str
    content: str = ""
    url: str = ""
    keywords: list[str] = []


class NewsResponse(BaseModel):
    id: int
    source: str | None = None
    title: str | None = None
    url: str | None = None
    keywords: list[str] | None = None
    impact_score: int = 0
    theme: str | None = None
    is_leading: bool = False
    crawled_at: datetime  # str이면 Pydantic v2에서 datetime 직렬화 실패

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
    try:
        query = select(NewsArticle)
        if impact_min is not None:
            query = query.where(NewsArticle.impact_score >= impact_min)
        result = await db.execute(
            query.order_by(NewsArticle.crawled_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()
    except Exception:
        await db.rollback()
        return []


@router.post("/ingest", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_internal_key)])
async def ingest_news(req: NewsIngestRequest, db: AsyncSession = Depends(get_db)):
    """내부 서비스에서 수집한 뉴스를 DB에 저장.

    중복 URL이면 409를 반환하고, URL이 없으면 무조건 삽입.
    """
    if req.url:
        row = await db.execute(
            text("SELECT id FROM news_articles WHERE url = :url"),
            {"url": req.url},
        )
        if row.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate URL")

    await db.execute(
        text(
            "INSERT INTO news_articles (source, title, content, url, keywords, crawled_at) "
            "VALUES (:source, :title, :content, :url, :keywords, :crawled_at)"
        ),
        {
            "source": req.source,
            "title": req.title,
            "content": req.content,
            "url": req.url,
            "keywords": req.keywords,
            "crawled_at": datetime.now(timezone.utc),
        },
    )
    await db.commit()
    return {"status": "ok"}


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
            "1 - (embedding <=> CAST(:vec AS vector)) AS similarity "
            "FROM news_articles "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:vec AS vector) "
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
