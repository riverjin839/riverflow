"""조건 검색 CRUD + 실행 라우터."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.broker_config import broker_settings
from ..core.database import get_db
from ..core.security import verify_token
from ..models.condition import SearchCondition, SearchResult
from ..services.broker.kis_broker import KISBroker
from ..services.condition_engine import ConditionEngine

router = APIRouter(prefix="/api/conditions", tags=["conditions"])


class ConditionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    conditions: dict
    auto_trade: bool = False
    auto_trade_config: Optional[dict] = None


class ConditionResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    conditions: dict
    is_active: bool
    auto_trade: bool
    auto_trade_config: Optional[dict]

    model_config = {"from_attributes": True}


class ScanResultItem(BaseModel):
    ticker: str
    name: str | None = None
    price: float | None = None
    volume: int | None = None
    change_rate: float | None = None
    volume_ratio: float | None = None


class ScanResponse(BaseModel):
    condition_id: int
    matched_count: int
    results: list[ScanResultItem]


@router.get("/", response_model=list[ConditionResponse])
async def list_conditions(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 목록 조회"""
    result = await db.execute(
        select(SearchCondition).order_by(SearchCondition.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=ConditionResponse, status_code=201)
async def create_condition(
    req: ConditionCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 생성"""
    condition = SearchCondition(**req.model_dump())
    db.add(condition)
    await db.commit()
    await db.refresh(condition)
    return condition


@router.get("/{condition_id}", response_model=ConditionResponse)
async def get_condition(
    condition_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 상세 조회"""
    condition = await db.get(SearchCondition, condition_id)
    if not condition:
        raise HTTPException(status_code=404, detail="조건식을 찾을 수 없습니다")
    return condition


@router.put("/{condition_id}", response_model=ConditionResponse)
async def update_condition(
    condition_id: int,
    req: ConditionCreate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 수정"""
    condition = await db.get(SearchCondition, condition_id)
    if not condition:
        raise HTTPException(status_code=404, detail="조건식을 찾을 수 없습니다")

    for key, value in req.model_dump().items():
        setattr(condition, key, value)

    await db.commit()
    await db.refresh(condition)
    return condition


@router.delete("/{condition_id}", status_code=204)
async def delete_condition(
    condition_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 삭제"""
    condition = await db.get(SearchCondition, condition_id)
    if not condition:
        raise HTTPException(status_code=404, detail="조건식을 찾을 수 없습니다")
    await db.delete(condition)
    await db.commit()


@router.post("/{condition_id}/scan", response_model=ScanResponse)
async def scan_condition(
    condition_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건식 실행 (전 종목 스캔)"""
    condition = await db.get(SearchCondition, condition_id)
    if not condition:
        raise HTTPException(status_code=404, detail="조건식을 찾을 수 없습니다")

    broker = KISBroker(broker_settings)
    engine = ConditionEngine(broker, db)
    try:
        results = await engine.scan(condition.conditions)
        await engine.save_results(condition_id, results)
    finally:
        await broker.close()

    return ScanResponse(
        condition_id=condition_id,
        matched_count=len(results),
        results=[ScanResultItem(**r) for r in results],
    )


@router.get("/{condition_id}/results")
async def get_scan_results(
    condition_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """조건 검색 결과 조회"""
    result = await db.execute(
        select(SearchResult)
        .where(SearchResult.condition_id == condition_id)
        .order_by(SearchResult.matched_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "ticker_name": r.ticker_name,
            "price_at_match": float(r.price_at_match) if r.price_at_match else None,
            "volume_at_match": r.volume_at_match,
            "matched_at": str(r.matched_at),
            "saved": r.saved,
            "traded": r.traded,
        }
        for r in rows
    ]
