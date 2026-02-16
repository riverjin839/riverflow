"""장전 시황 브리핑 워커.

CronJob으로 매일 08:30 KST에 실행된다.
전일 시장 데이터를 요약하여 DB에 저장하고 텔레그램으로 발송한다.
"""

import asyncio
import json
import logging
import os

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.broker_config import broker_settings
from backend.app.services.llm_client import LLMClient
from backend.app.services.notifier import Notifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def fetch_market_indices() -> dict:
    """KIS API로 주요 지수 전일 데이터 조회"""
    base_url = (
        "https://openapivts.koreainvestment.com:29443"
        if broker_settings.KIS_IS_VIRTUAL
        else "https://openapi.koreainvestment.com:9443"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 토큰 발급
        token_resp = await client.post(
            f"{base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": broker_settings.KIS_APP_KEY,
                "appsecret": broker_settings.KIS_APP_SECRET,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": broker_settings.KIS_APP_KEY,
            "appsecret": broker_settings.KIS_APP_SECRET,
            "tr_id": "FHPUP02100000",
        }

        indices = {}
        for name, code in [("KOSPI", "0001"), ("KOSDAQ", "1001")]:
            try:
                resp = await client.get(
                    f"{base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price",
                    headers=headers,
                    params={
                        "FID_COND_MRKT_DIV_CODE": "U",
                        "FID_INPUT_ISCD": code,
                    },
                )
                resp.raise_for_status()
                output = resp.json().get("output", {})
                indices[name] = {
                    "price": output.get("bstp_nmix_prpr", ""),
                    "change": output.get("bstp_nmix_prdy_vrss", ""),
                    "change_rate": output.get("bstp_nmix_prdy_ctrt", ""),
                    "volume": output.get("acml_vol", ""),
                }
            except Exception:
                logger.warning("%s 지수 조회 실패", name)

        return indices


async def generate_morning_briefing() -> None:
    """장전 시황 브리핑 생성"""
    logger.info("장전 시황 브리핑 생성 시작")

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://trading:trading@localhost:5432/trading",
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    llm = LLMClient()
    notifier = Notifier()

    try:
        # 1. 전일 시장 데이터 조회
        market_data = {}
        try:
            market_data = await fetch_market_indices()
            logger.info("시장 지수 데이터 조회 완료: %s", list(market_data.keys()))
        except Exception:
            logger.exception("시장 지수 조회 실패, 일반 브리핑으로 진행")

        # 2. LLM으로 요약 생성
        if market_data:
            data_text = ""
            for name, info in market_data.items():
                data_text += (
                    f"{name}: {info.get('price', 'N/A')}pt "
                    f"(전일대비 {info.get('change', 'N/A')}, "
                    f"{info.get('change_rate', 'N/A')}%)\n"
                )
            prompt = (
                f"다음 전일 시장 데이터를 바탕으로 오늘의 한국 증시 시황 브리핑을 작성해주세요.\n\n"
                f"{data_text}\n"
                f"KOSPI, KOSDAQ 지수 전망, 주요 이슈, 관심 섹터를 포함해주세요."
            )
        else:
            prompt = (
                "오늘의 한국 증시 시황 브리핑을 작성해주세요. "
                "KOSPI, KOSDAQ 지수 전망, 주요 이슈, 관심 섹터를 포함해주세요."
            )

        summary = await llm.generate(
            prompt=prompt,
            system="당신은 증권 애널리스트입니다. 간결하고 핵심적인 시황 브리핑을 작성하세요.",
        )

        # 3. DB 저장
        async with async_session() as db:
            await db.execute(
                text(
                    "INSERT INTO market_briefing (briefing_type, raw_data, summary) "
                    "VALUES ('morning', :raw_data::jsonb, :summary)"
                ),
                {
                    "raw_data": json.dumps(market_data, ensure_ascii=False),
                    "summary": summary,
                },
            )
            await db.commit()

        # 4. 텔레그램 발송
        await notifier.send(f"[장전 브리핑]\n{summary}")
        logger.info("장전 시황 브리핑 완료")

    finally:
        await llm.close()
        await notifier.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(generate_morning_briefing())
