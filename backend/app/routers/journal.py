"""매매일지 CRUD 라우터."""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.broker_config import broker_settings
from ..core.database import get_db
from ..core.security import verify_token
from ..models.journal import TradeJournal
from ..services.broker.kis_broker import KISBroker

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


@router.get("", response_model=list[JournalResponse])
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


@router.post("", response_model=JournalResponse, status_code=201)
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


# ── KIS 체결내역 가져오기 ──

@router.get("/kis-trades")
async def get_kis_trades(
    start_date: str = Query(..., description="시작일 YYYYMMDD"),
    end_date: str = Query(..., description="종료일 YYYYMMDD"),
    _: dict = Depends(verify_token),
):
    """KIS 계좌 체결내역 조회 (일지 등록 전 미리보기)."""
    if not broker_settings.KIS_APP_KEY:
        raise HTTPException(status_code=400, detail="KIS API 키가 설정되지 않았습니다")

    broker = KISBroker(broker_settings)
    try:
        # 일별로 조회 (KIS API는 하루 단위)
        all_trades: list[dict] = []
        current = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")

        while current <= end:
            dt_str = current.strftime("%Y%m%d")
            try:
                trades = await broker.get_order_history(dt_str)
                for t in trades:
                    # 체결 수량이 0이면 미체결 → 스킵
                    tot_qty = int(t.get("tot_ccld_qty", 0))
                    if tot_qty <= 0:
                        continue
                    all_trades.append({
                        "order_date": t.get("ord_dt", dt_str),
                        "ticker": t.get("pdno", ""),
                        "ticker_name": t.get("prdt_name", ""),
                        "side": "BUY" if t.get("sll_buy_dvsn_cd") == "02" else "SELL",
                        "quantity": tot_qty,
                        "price": float(t.get("avg_prvs", 0) or t.get("tot_ccld_amt", 0)) / max(tot_qty, 1),
                        "total_amount": int(t.get("tot_ccld_amt", 0)),
                        "order_id": t.get("odno", ""),
                    })
            except Exception:
                pass  # 해당 날짜 조회 실패 시 스킵
            from datetime import timedelta
            current += timedelta(days=1)

        return {"trades": all_trades, "is_virtual": broker_settings.KIS_IS_VIRTUAL}
    finally:
        await broker.close()


class KISImportRequest(BaseModel):
    trades: list[dict]  # [{ticker, ticker_name, side, quantity, price, order_date}, ...]


@router.post("/import-kis", response_model=list[JournalResponse], status_code=201)
async def import_kis_trades(
    req: KISImportRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """KIS 체결내역을 매매일지로 일괄 등록."""
    journals = []
    for t in req.trades:
        trade_date = date.fromisoformat(
            t.get("order_date", "")[:4] + "-" +
            t.get("order_date", "")[4:6] + "-" +
            t.get("order_date", "")[6:8]
        ) if t.get("order_date") else date.today()

        side = t.get("side", "BUY")
        price = float(t.get("price", 0))
        journal = TradeJournal(
            trade_date=trade_date,
            ticker=t.get("ticker", ""),
            ticker_name=t.get("ticker_name"),
            buy_price=price if side == "BUY" else None,
            sell_price=price if side == "SELL" else None,
            quantity=int(t.get("quantity", 0)),
            buy_reason=f"[KIS 자동등록] {side} {t.get('ticker_name', '')}",
            tags=["KIS자동", "매수" if side == "BUY" else "매도"],
        )
        db.add(journal)
        journals.append(journal)

    await db.commit()
    for j in journals:
        await db.refresh(j)
    return journals
