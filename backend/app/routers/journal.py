"""매매일지 CRUD 라우터."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.journal import TradeJournal

router = APIRouter(prefix="/api/journal", tags=["journal"])


class JournalCreate(BaseModel):
    trade_date: date
    ticker: str
    ticker_name: Optional[str] = None
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    quantity: Optional[int] = None
    profit_rate: Optional[float] = None
    buy_reason: Optional[str] = None
    tags: Optional[list[str]] = None


class JournalResponse(BaseModel):
    id: int
    trade_date: date
    ticker: str
    ticker_name: Optional[str]
    buy_price: Optional[float]
    sell_price: Optional[float]
    quantity: Optional[int]
    profit_rate: Optional[float]
    buy_reason: Optional[str]
    ai_feedback: Optional[str]
    tags: Optional[list[str]]

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[JournalResponse])
async def list_journals(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """매매일지 목록 조회"""
    result = await db.execute(
        select(TradeJournal)
        .order_by(TradeJournal.trade_date.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/", response_model=JournalResponse, status_code=201)
async def create_journal(
    req: JournalCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """매매일지 작성"""
    journal = TradeJournal(**req.model_dump())
    db.add(journal)
    await db.commit()
    await db.refresh(journal)
    return journal


@router.get("/{journal_id}", response_model=JournalResponse)
async def get_journal(
    journal_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """매매일지 상세 조회"""
    journal = await db.get(TradeJournal, journal_id)
    if not journal:
        raise HTTPException(status_code=404, detail="매매일지를 찾을 수 없습니다")
    return journal


@router.delete("/{journal_id}", status_code=204)
async def delete_journal(
    journal_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """매매일지 삭제"""
    journal = await db.get(TradeJournal, journal_id)
    if not journal:
        raise HTTPException(status_code=404, detail="매매일지를 찾을 수 없습니다")
    await db.delete(journal)
    await db.commit()
