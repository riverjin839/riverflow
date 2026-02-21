"""AI 라우터 - RAG 챗봇 + 문서관리 + 종목추천 + 매매 피드백."""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import verify_token
from ..models.journal import TradeJournal
from ..models.document import UserDocument
from ..models.chat import ChatMessage
from ..services.llm_client import LLMClient
from ..services.embedding import EmbeddingService
from ..services.doc_ingestor import extract_text_from_pdf, ingest_document

router = APIRouter(prefix="/api/ai", tags=["ai"])
logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ── 시스템 프롬프트 ──

CHAT_SYSTEM_PROMPT = """당신은 Riverflow AI - 한국 증시 전문 투자 어시스턴트입니다.

역할:
- 사용자의 투자 원칙과 학습 자료를 기반으로 맞춤형 투자 조언 제공
- 코스피/코스닥 종목 분석 (차트, 거래대금, 테마, 재료, 재무상태)
- 매수/매도 타이밍 추천
- 시장 상황 분석 및 브리핑

규칙:
- 한국어로 답변
- 근거 기반 분석 (데이터, 차트 패턴, 수급 등)
- 리스크 관리 항상 언급
- 투자 판단의 최종 결정은 사용자에게 있음을 명시
- 구체적 수치와 함께 답변"""

RECOMMEND_SYSTEM_PROMPT = """당신은 한국 증시 전문 애널리스트입니다.

주어진 종목의 시세 데이터와 사용자의 투자 원칙/학습 자료를 분석하여 매수/매도/관망 의견을 제시하세요.

분석 항목:
1. 현재가 및 등락률 분석
2. 거래량 분석 (평소 대비)
3. 기술적 분석 (RSI 등)
4. 사용자 학습 자료 기반 관점

출력 형식:
- 종목명 (종목코드)
- 현재 상태 요약
- 매수/매도/관망 의견
- 근거 (3줄 이내)
- 목표가 / 손절가 제안
- 리스크 요인"""


# ══════════════════════════════════════
# 1. 문서 관리 (업로드 / 목록 / 삭제)
# ══════════════════════════════════════

class DocumentResponse(BaseModel):
    id: int
    doc_type: str | None
    title: str | None
    content_preview: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="general"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """문서 업로드 (PDF, TXT 등) → 청킹 + 임베딩 후 저장."""
    if not file.filename:
        raise HTTPException(400, "파일명이 없습니다")

    content_bytes = await file.read()
    if len(content_bytes) > 20 * 1024 * 1024:  # 20MB 제한
        raise HTTPException(400, "파일 크기가 20MB를 초과합니다")

    filename = file.filename.lower()

    # 텍스트 추출
    if filename.endswith(".pdf"):
        try:
            text_content = extract_text_from_pdf(content_bytes)
        except Exception as e:
            raise HTTPException(400, f"PDF 파싱 실패: {e}")
    elif filename.endswith((".txt", ".md", ".csv")):
        text_content = content_bytes.decode("utf-8", errors="replace")
    else:
        raise HTTPException(400, "지원하지 않는 파일 형식입니다 (PDF, TXT, MD, CSV 지원)")

    if not text_content.strip():
        raise HTTPException(400, "파일에서 텍스트를 추출할 수 없습니다")

    title = file.filename
    chunk_count = await ingest_document(db, title, text_content, doc_type)

    return {
        "message": f"'{title}' 업로드 완료",
        "chunks": chunk_count,
        "total_chars": len(text_content),
    }


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """업로드된 문서 목록 조회."""
    result = await db.execute(
        select(UserDocument)
        .order_by(UserDocument.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    docs = result.scalars().all()
    return [
        DocumentResponse(
            id=d.id,
            doc_type=d.doc_type,
            title=d.title,
            content_preview=(d.content[:100] + "...") if d.content and len(d.content) > 100 else d.content,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """문서 삭제."""
    doc = await db.get(UserDocument, doc_id)
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다")
    await db.delete(doc)
    await db.commit()


@router.delete("/documents", status_code=204)
async def delete_documents_by_title(
    title: str = Query(..., description="삭제할 문서 제목 (청크 포함 일괄 삭제)"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """같은 제목의 문서 청크 일괄 삭제."""
    # 제목이 "파일명 [1/N]" 패턴이므로 원본 제목으로 LIKE 검색
    base_title = title.split(" [")[0]
    result = await db.execute(
        text("DELETE FROM user_documents WHERE title LIKE :pattern"),
        {"pattern": f"{base_title}%"},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "삭제할 문서가 없습니다")


# ══════════════════════════════════════
# 2. RAG 챗봇
# ══════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sources: list[str]


async def _retrieve_context(
    db: AsyncSession,
    query: str,
    embedding_svc: EmbeddingService,
    top_k: int = 5,
) -> list[dict]:
    """쿼리와 유사한 문서 청크를 벡터 검색으로 가져오기."""
    try:
        vec = await embedding_svc.embed(query)
        result = await db.execute(
            text(
                "SELECT id, title, content, "
                "1 - (embedding <=> :vec::vector) AS similarity "
                "FROM user_documents "
                "WHERE embedding IS NOT NULL "
                "ORDER BY embedding <=> :vec::vector "
                "LIMIT :k"
            ),
            {"vec": str(vec), "k": top_k},
        )
        rows = result.fetchall()
        return [
            {"title": r.title, "content": r.content, "similarity": round(float(r.similarity), 3)}
            for r in rows
            if r.similarity > 0.3  # 유사도 임계값
        ]
    except Exception as e:
        logger.warning("벡터 검색 실패: %s", e)
        return []


async def _fetch_stock_data(ticker: str) -> dict | None:
    """Naver Finance에서 개별 종목 시세 가져오기."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{ticker}/basic",
                headers={"User-Agent": _UA, "Referer": "https://m.stock.naver.com/"},
            )
            if resp.status_code != 200:
                return None
            d = resp.json()
            price = float(str(d.get("closePrice", "0")).replace(",", ""))
            if price <= 0:
                return None
            return {
                "name": d.get("stockName", ticker),
                "price": price,
                "change": float(str(d.get("compareToPreviousClosePrice", "0")).replace(",", "")),
                "change_rate": float(str(d.get("fluctuationsRatio", "0")).replace(",", "")),
                "high": float(str(d.get("highPrice", "0")).replace(",", "")),
                "low": float(str(d.get("lowPrice", "0")).replace(",", "")),
                "volume": int(float(str(d.get("accumulatedTradingVolume", "0")).replace(",", ""))),
                "market_cap": d.get("marketCap", ""),
                "per": d.get("per", ""),
                "pbr": d.get("pbr", ""),
                "eps": d.get("eps", ""),
            }
    except Exception as e:
        logger.warning("종목 시세 조회 실패 %s: %s", ticker, e)
        return None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """RAG 기반 AI 채팅."""
    session_id = req.session_id or str(uuid.uuid4())[:8]

    # 1. 이전 대화 기록 로드 (최근 10개)
    prev_msgs = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
    )
    history = list(reversed(prev_msgs.scalars().all()))

    # 2. RAG: 유사 문서 검색
    embedding_svc = EmbeddingService()
    sources: list[str] = []
    try:
        context_docs = await _retrieve_context(db, req.message, embedding_svc)
        sources = [d["title"] for d in context_docs]
    except Exception:
        context_docs = []
    finally:
        await embedding_svc.close()

    # 3. 종목코드 감지 시 시세 자동 조회
    stock_info = ""
    ticker_match = re.findall(r"\b(\d{6})\b", req.message)
    for ticker in ticker_match[:3]:
        data = await _fetch_stock_data(ticker)
        if data:
            stock_info += (
                f"\n[종목 시세: {data['name']}({ticker})]\n"
                f"현재가: {data['price']:,.0f}원 ({data['change_rate']:+.2f}%)\n"
                f"고가: {data['high']:,.0f} / 저가: {data['low']:,.0f}\n"
                f"거래량: {data['volume']:,}\n"
                f"PER: {data['per']} / PBR: {data['pbr']}\n"
            )

    # 4. 프롬프트 구성
    context_text = ""
    if context_docs:
        context_text = "\n\n[참고 자료]\n"
        for d in context_docs:
            context_text += f"--- {d['title']} (유사도: {d['similarity']}) ---\n{d['content']}\n\n"

    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    # 이전 대화
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    # 현재 메시지 + 컨텍스트
    user_prompt = req.message
    if context_text or stock_info:
        user_prompt += "\n\n" + stock_info + context_text

    messages.append({"role": "user", "content": user_prompt})

    # 5. LLM 호출
    llm = LLMClient()
    try:
        reply = await llm.chat(messages)
    except Exception as e:
        logger.error("LLM 호출 실패: %s", e)
        reply = f"AI 응답 생성에 실패했습니다. Ollama 서버 상태를 확인해주세요. (오류: {e})"
    finally:
        await llm.close()

    # 6. 대화 히스토리 저장
    db.add(ChatMessage(session_id=session_id, role="user", content=req.message))
    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
    await db.commit()

    return ChatResponse(reply=reply, session_id=session_id, sources=sources)


@router.get("/chat/sessions")
async def list_chat_sessions(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """채팅 세션 목록."""
    result = await db.execute(
        text(
            "SELECT session_id, MIN(content) AS first_message, "
            "MIN(created_at) AS started_at, COUNT(*) AS msg_count "
            "FROM chat_messages WHERE role = 'user' "
            "GROUP BY session_id "
            "ORDER BY MAX(created_at) DESC "
            "LIMIT 20"
        )
    )
    rows = result.fetchall()
    return [
        {
            "session_id": r.session_id,
            "preview": r.first_message[:50] if r.first_message else "",
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "msg_count": r.msg_count,
        }
        for r in rows
    ]


@router.get("/chat/history")
async def get_chat_history(
    session_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """특정 세션의 대화 히스토리."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    msgs = result.scalars().all()
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in msgs
    ]


@router.delete("/chat/{session_id}", status_code=204)
async def delete_chat_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """채팅 세션 삭제."""
    await db.execute(
        text("DELETE FROM chat_messages WHERE session_id = :sid"),
        {"sid": session_id},
    )
    await db.commit()


# ══════════════════════════════════════
# 3. 종목 추천
# ══════════════════════════════════════

class RecommendRequest(BaseModel):
    ticker: str
    ticker_name: Optional[str] = None


class RecommendResponse(BaseModel):
    ticker: str
    ticker_name: str
    analysis: str
    sources: list[str]


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_stock(
    req: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """종목 분석 및 매수/매도 추천."""
    # 1. 시세 데이터 가져오기
    stock_data = await _fetch_stock_data(req.ticker)
    if not stock_data:
        raise HTTPException(400, f"종목 '{req.ticker}' 시세를 조회할 수 없습니다")

    ticker_name = req.ticker_name or stock_data["name"]

    # 2. 차트 히스토리 (RSI 계산용)
    chart_info = ""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://m.stock.naver.com/api/stock/{req.ticker}/price",
                params={"page": 1, "pageSize": 30},
                headers={"User-Agent": _UA, "Referer": "https://m.stock.naver.com/"},
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("priceInfos", data.get("items", []))
                if isinstance(items, list) and items:
                    closes = []
                    for item in reversed(items):
                        c = float(str(item.get("closePrice", "0")).replace(",", ""))
                        if c > 0:
                            closes.append(c)
                    if len(closes) >= 15:
                        rsi = _calc_rsi(closes)
                        chart_info = f"RSI(14): {rsi:.1f}\n" if rsi else ""
                    # 최근 5일 종가
                    recent = closes[-5:] if len(closes) >= 5 else closes
                    chart_info += "최근 5일 종가: " + ", ".join(f"{c:,.0f}" for c in recent) + "\n"
    except Exception:
        pass

    # 3. RAG: 관련 문서 검색
    embedding_svc = EmbeddingService()
    sources: list[str] = []
    context_text = ""
    try:
        query = f"{ticker_name} {stock_data.get('name', '')} 투자 분석"
        context_docs = await _retrieve_context(db, query, embedding_svc)
        sources = [d["title"] for d in context_docs]
        if context_docs:
            context_text = "\n[사용자 학습 자료]\n"
            for d in context_docs:
                context_text += f"- {d['content'][:300]}\n"
    except Exception:
        pass
    finally:
        await embedding_svc.close()

    # 4. 프롬프트 구성
    prompt = (
        f"종목: {ticker_name} ({req.ticker})\n"
        f"현재가: {stock_data['price']:,.0f}원\n"
        f"등락률: {stock_data['change_rate']:+.2f}%\n"
        f"고가: {stock_data['high']:,.0f} / 저가: {stock_data['low']:,.0f}\n"
        f"거래량: {stock_data['volume']:,}\n"
        f"PER: {stock_data['per']} / PBR: {stock_data['pbr']}\n"
        f"{chart_info}"
        f"{context_text}\n"
        f"위 데이터를 종합 분석하여 매수/매도/관망 의견을 제시해주세요."
    )

    # 5. LLM 호출
    llm = LLMClient()
    try:
        analysis = await llm.generate(prompt=prompt, system=RECOMMEND_SYSTEM_PROMPT)
    except Exception as e:
        logger.error("추천 LLM 호출 실패: %s", e)
        analysis = f"분석 생성에 실패했습니다. (오류: {e})"
    finally:
        await llm.close()

    return RecommendResponse(
        ticker=req.ticker,
        ticker_name=ticker_name,
        analysis=analysis,
        sources=sources,
    )


# ══════════════════════════════════════
# 4. 매매일지 AI 피드백 (기존)
# ══════════════════════════════════════

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


# ── 유틸 ──

def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(d, 0) for d in deltas[:period]) / period
    avg_loss = sum(abs(min(d, 0)) for d in deltas[:period]) / period
    for d in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + abs(min(d, 0))) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 1)
