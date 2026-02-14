"""KIS WebSocket 실시간 시세 수신 워커.

장중에 별도 Pod으로 실행되어 WebSocket 연결을 유지한다.
수신된 체결 데이터를 DB에 기록하고 손절/익절 트리거를 발생시킨다.
"""

import asyncio
import json
import logging
import os

import httpx
import websockets

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
        # TODO: DB에 최신가 업데이트
        # TODO: 손절/익절 체크 트리거
        # TODO: SSE로 프론트엔드 전송
        logger.debug("tick: %s %s", tick.get("ticker"), tick.get("current_price"))


async def main() -> None:
    """실시간 시세 워커 메인"""
    tickers_env = os.environ.get("WATCH_TICKERS", "")
    tickers = [t.strip() for t in tickers_env.split(",") if t.strip()]

    if not tickers:
        logger.warning("WATCH_TICKERS 환경변수가 비어있습니다. 대기 상태로 진입합니다.")
        while True:
            await asyncio.sleep(60)

    feed = KISRealtimeFeed()
    while True:
        try:
            await feed.run(tickers)
        except Exception:
            logger.exception("WebSocket 연결 끊김, 10초 후 재시도")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
