"""KIS WebSocket 실시간 시세 수신 워커.

장중에 별도 Pod으로 실행되어 WebSocket 연결을 유지한다.
수신된 체결 데이터를 DB에 기록하고 손절/익절 트리거를 발생시킨다.
"""

import asyncio
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone

import httpx
import websockets
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class KISRealtimeFeed:
    """KIS WebSocket 실시간 시세 수신"""

    WS_URL = "ws://ops.koreainvestment.com:21000"
    WS_URL_VIRTUAL = "ws://ops.koreainvestment.com:31000"

    def __init__(self):
        self.app_key = os.environ.get("KIS_APP_KEY", "")
        self.app_secret = os.environ.get("KIS_APP_SECRET", "")
        self.is_virtual = os.environ.get("KIS_IS_VIRTUAL", "true").lower() == "true"
        self.approval_key: str | None = None

        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://trading:trading@localhost:5432/trading",
        )
        self.engine = create_async_engine(db_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # 최신 시세 캐시 (ticker -> price info)
        self.latest_prices: dict[str, dict] = {}
        # 배치 저장을 위한 틱 버퍼
        self._tick_buffer: list[dict] = []
        self._flush_interval = 10  # 10초마다 DB flush

    async def _get_approval_key(self) -> str:
        """WebSocket 접속용 approval key 발급"""
        base_url = (
            "https://openapivts.koreainvestment.com:29443"
            if self.is_virtual
            else "https://openapi.koreainvestment.com:9443"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{base_url}/oauth2/Approval",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self.app_key,
                    "secretkey": self.app_secret,
                },
            )
            resp.raise_for_status()
            return resp.json()["approval_key"]

    async def run(self, tickers: list[str]) -> None:
        """실시간 시세 수신 루프"""
        self.approval_key = await self._get_approval_key()
        url = self.WS_URL_VIRTUAL if self.is_virtual else self.WS_URL

        logger.info("WebSocket 연결: %s (종목 %d개)", url, len(tickers))

        # 주기적 DB flush 태스크 시작
        flush_task = asyncio.create_task(self._periodic_flush())

        try:
            async with websockets.connect(url, ping_interval=30) as ws:
                # 시세 구독 등록
                for ticker in tickers:
                    subscribe_msg = {
                        "header": {
                            "approval_key": self.approval_key,
                            "custtype": "P",
                            "tr_type": "1",
                            "content-type": "utf-8",
                        },
                        "body": {
                            "input": {
                                "tr_id": "H0STCNT0",  # 주식체결
                                "tr_key": ticker,
                            }
                        },
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("구독 등록: %s", ticker)

                # 수신 루프
                async for message in ws:
                    data = self._parse_realtime(message)
                    if data:
                        await self._process_tick(data)
        finally:
            flush_task.cancel()
            # 잔여 버퍼 flush
            if self._tick_buffer:
                await self._flush_to_db()

    def _parse_realtime(self, message: str) -> dict | None:
        """실시간 체결 메시지 파싱"""
        try:
            if message.startswith("{"):
                return json.loads(message)

            # 파이프 구분 데이터 파싱 (KIS 실시간 데이터 형식)
            parts = message.split("|")
            if len(parts) >= 4:
                fields = parts[3].split("^")
                return {
                    "ticker": fields[0] if len(fields) > 0 else "",
                    "current_price": int(fields[2]) if len(fields) > 2 else 0,
                    "volume": int(fields[12]) if len(fields) > 12 else 0,
                    "change_rate": float(fields[5]) if len(fields) > 5 else 0,
                }
        except (ValueError, IndexError):
            logger.debug("파싱 실패: %s", message[:100])
        return None

    async def _process_tick(self, tick: dict) -> None:
        """실시간 체결 데이터 처리"""
        ticker = tick.get("ticker", "")
        if not ticker:
            return

        # 1. 메모리 캐시 업데이트 (최신가)
        self.latest_prices[ticker] = {
            "current_price": tick.get("current_price", 0),
            "volume": tick.get("volume", 0),
            "change_rate": tick.get("change_rate", 0),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # 2. 버퍼에 추가 (배치 DB 저장)
        self._tick_buffer.append(tick)

        logger.debug("tick: %s %s", ticker, tick.get("current_price"))

    async def _periodic_flush(self) -> None:
        """주기적으로 틱 버퍼를 DB에 flush"""
        while True:
            await asyncio.sleep(self._flush_interval)
            if self._tick_buffer:
                await self._flush_to_db()

    async def _flush_to_db(self) -> None:
        """버퍼된 틱 데이터를 DB에 최신가로 업데이트

        search_results 테이블의 최근 결과에 대해 현재가를 업데이트하여
        손절/익절 체커가 최신 가격을 참조할 수 있게 한다.
        """
        # 종목별 마지막 틱만 사용 (최신가)
        latest_by_ticker: dict[str, dict] = {}
        for tick in self._tick_buffer:
            t = tick.get("ticker", "")
            if t:
                latest_by_ticker[t] = tick
        self._tick_buffer.clear()

        if not latest_by_ticker:
            return

        try:
            async with self.async_session() as db:
                for ticker, tick in latest_by_ticker.items():
                    # search_results의 최근 결과에 현재가 업데이트
                    await db.execute(
                        text(
                            "UPDATE search_results "
                            "SET match_details = match_details || :price_data::jsonb "
                            "WHERE ticker = :ticker "
                            "AND matched_at >= NOW() - INTERVAL '1 day'"
                        ),
                        {
                            "ticker": ticker,
                            "price_data": json.dumps({
                                "latest_price": tick.get("current_price", 0),
                                "latest_volume": tick.get("volume", 0),
                            }),
                        },
                    )
                await db.commit()

            logger.debug("DB flush 완료: %d종목", len(latest_by_ticker))
        except Exception:
            logger.exception("DB flush 실패")

    async def close(self) -> None:
        """리소스 정리"""
        await self.engine.dispose()


async def main() -> None:
    """실시간 시세 워커 메인"""
    tickers_env = os.environ.get("WATCH_TICKERS", "")
    tickers = [t.strip() for t in tickers_env.split(",") if t.strip()]

    if not tickers:
        logger.warning("WATCH_TICKERS 환경변수가 비어있습니다. 대기 상태로 진입합니다.")
        while True:
            await asyncio.sleep(60)

    feed = KISRealtimeFeed()
    try:
        while True:
            try:
                await feed.run(tickers)
            except Exception:
                logger.exception("WebSocket 연결 끊김, 10초 후 재시도")
                await asyncio.sleep(10)
    finally:
        await feed.close()


if __name__ == "__main__":
    asyncio.run(main())
