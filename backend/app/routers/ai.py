"""AI 피드백 라우터 - RAG 기반 매매 피드백."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.journal import TradeJournal
from ..services.llm_client import LLMClient

router = APIRouter(prefix="/api/ai", tags=["ai"])


class FeedbackRequest(BaseModel):
    journal_id: int


class FeedbackResponse(BaseModel):
    journal_id: int
    feedback: str


@router.post("/feedback", response_model=FeedbackResponse)
async def generate_feedback(
    req: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """매매일지에 대한 AI 피드백 생성"""
    journal = await db.get(TradeJournal, req.journal_id)
    if not journal:
        raise HTTPException(status_code=404, detail="매매일지를 찾을 수 없습니다")

    llm = LLMClient()
    try:
        prompt = (
            f"다음 매매 기록을 분석하고 피드백을 제공해주세요:\n"
            f"종목: {journal.ticker} ({journal.ticker_name})\n"
            f"매수가: {journal.buy_price}\n"
            f"매도가: {journal.sell_price}\n"
            f"수익률: {journal.profit_rate}%\n"
            f"매수 사유: {journal.buy_reason}\n"
        )
        feedback = await llm.generate(
            prompt=prompt,
            system="당신은 주식 매매 전문 코치입니다. 매매 기록을 분석하고 개선점을 제안하세요.",
        )
    finally:
        await llm.close()

    journal.ai_feedback = feedback
    await db.commit()

    return FeedbackResponse(journal_id=journal.id, feedback=feedback)
