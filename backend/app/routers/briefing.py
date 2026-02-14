"""시황 브리핑 라우터."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.briefing import MarketBriefing

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


class BriefingResponse(BaseModel):
    id: int
    briefing_type: str
    summary: str | None
    raw_data: dict | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/latest", response_model=list[BriefingResponse])
async def get_latest_briefings(
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """최신 브리핑 조회"""
    result = await db.execute(
        select(MarketBriefing)
        .order_by(MarketBriefing.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
