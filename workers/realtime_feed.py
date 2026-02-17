"""KIS WebSocket 실시간 시세 수신 워커.

장중에 별도 Pod으로 실행되어 WebSocket 연결을 유지한다.
수신된 체결 데이터를 DB에 기록하고 손절/익절 트리거를 발생시킨다.

추가 기능:
- 1분 단위 시장 지수 + 투자자별 수급 스냅샷 저장
- 최근 10분간 외인/기관 순매수 추세 판단
"""

import asyncio
import json
import logging
import os
from collections import defaultdict, deque
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
        self._rest_token: str | None = None

        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://trading:trading@localhost:5432/trading",
        )
        self.engine = create_async_engine(db_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.rest_client = httpx.AsyncClient(timeout=30.0)

        # 최신 시세 캐시 (ticker -> price info)
        self.latest_prices: dict[str, dict] = {}
        # 배치 저장을 위한 틱 버퍼
        self._tick_buffer: list[dict] = []
        self._flush_interval = 10  # 10초마다 DB flush

        # 수급 추적용 (최근 10분 = 10개 스냅샷)
        self._supply_history: dict[str, deque] = {
            "KOSPI": deque(maxlen=10),
            "KOSDAQ": deque(maxlen=10),
        }

    @property
    def _base_url(self) -> str:
        if self.is_virtual:
            return "https://openapivts.koreainvestment.com:29443"
        return "https://openapi.koreainvestment.com:9443"

    async def _get_approval_key(self) -> str:
        """WebSocket 접속용 approval key 발급"""
        resp = await self.rest_client.post(
            f"{self._base_url}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.app_secret,
            },
        )
        resp.raise_for_status()
        return resp.json()["approval_key"]

    async def _ensure_rest_token(self) -> None:
        """REST API용 OAuth 토큰 발급"""
        if self._rest_token:
            return
        resp = await self.rest_client.post(
            f"{self._base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
        )
        resp.raise_for_status()
        self._rest_token = resp.json()["access_token"]

    def _build_headers(self, tr_id: str) -> dict:
        """REST API 헤더 구성"""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._rest_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }

    async def run(self, tickers: list[str]) -> None:
        """실시간 시세 수신 루프"""
        self.approval_key = await self._get_approval_key()
        url = self.WS_URL_VIRTUAL if self.is_virtual else self.WS_URL

        logger.info("WebSocket 연결: %s (종목 %d개)", url, len(tickers))

        # 주기적 태스크 시작
        flush_task = asyncio.create_task(self._periodic_flush())
        supply_task = asyncio.create_task(self._periodic_supply_snapshot())

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
            supply_task.cancel()
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
        """버퍼된 틱 데이터를 DB에 최신가로 업데이트"""
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

    # ================================================================
    # 수급 연속성 추적
    # ================================================================

    async def _periodic_supply_snapshot(self) -> None:
        """1분 단위로 시장 지수 + 투자자별 수급 스냅샷 저장"""
        while True:
            await asyncio.sleep(60)
            for market in ["KOSPI", "KOSDAQ"]:
                try:
                    snapshot = await self._fetch_supply_snapshot(market)
                    if snapshot:
                        self._supply_history[market].append(snapshot)
                        await self._save_supply_snapshot(snapshot)
                except Exception:
                    logger.exception("수급 스냅샷 실패: %s", market)

    async def _fetch_supply_snapshot(self, market: str) -> dict | None:
        """KIS API로 시장 지수 + 투자자별 수급 조회"""
        await self._ensure_rest_token()

        # 1) 시장 지수 조회
        index_code = "0001" if market == "KOSPI" else "1001"
        index_data = await self._fetch_market_index(index_code)
        if not index_data:
            return None

        # 2) 투자자별 매매동향 조회
        investor_data = await self._fetch_investor_trend(index_code)

        now = datetime.now(timezone.utc)

        # 추세 판단
        history = self._supply_history[market]
        foreign_trend = self._detect_trend(history, "foreign_net_buy")
        institution_trend = self._detect_trend(history, "institution_net_buy")

        return {
            "snapshot_time": now.isoformat(),
            "market": market,
            "index_value": index_data.get("index_value", 0),
            "index_change_rate": index_data.get("index_change_rate", 0),
            "foreign_net_buy": investor_data.get("foreign_net_buy", 0),
            "institution_net_buy": investor_data.get("institution_net_buy", 0),
            "individual_net_buy": investor_data.get("individual_net_buy", 0),
            "foreign_trend": foreign_trend,
            "institution_trend": institution_trend,
        }

    async def _fetch_market_index(self, index_code: str) -> dict | None:
        """KIS 업종 현재가 조회"""
        try:
            tr_id = "FHPUP02110000"
            headers = self._build_headers(tr_id)
            resp = await self.rest_client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "U",
                    "FID_INPUT_ISCD": index_code,
                },
            )
            resp.raise_for_status()
            output = resp.json().get("output", {})
            return {
                "index_value": float(output.get("bstp_nmix_prpr", 0)),
                "index_change_rate": float(output.get("bstp_nmix_prdy_ctrt", 0)),
            }
        except Exception:
            logger.debug("시장 지수 조회 실패: %s", index_code)
            return None

    async def _fetch_investor_trend(self, index_code: str) -> dict:
        """KIS 투자자별 매매동향 조회 (외인/기관/개인 순매수)"""
        try:
            tr_id = "FHPTJ04400000"
            headers = self._build_headers(tr_id)
            resp = await self.rest_client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "V",
                    "FID_INPUT_ISCD": index_code,
                },
            )
            resp.raise_for_status()
            output = resp.json().get("output", [])
            if not output:
                return {}

            # 첫 번째 항목이 최신 데이터
            latest = output[0] if isinstance(output, list) else output
            return {
                "foreign_net_buy": int(latest.get("frgn_ntby_qty", 0)),
                "institution_net_buy": int(latest.get("orgn_ntby_qty", 0)),
                "individual_net_buy": int(latest.get("prsn_ntby_qty", 0)),
            }
        except Exception:
            logger.debug("투자자 동향 조회 실패: %s", index_code)
            return {}

    @staticmethod
    def _detect_trend(history: deque, field: str) -> str:
        """최근 10분간 스냅샷에서 순매수 추세 판단.

        - rising: 최근 5개 이상 스냅샷에서 값이 연속 증가
        - falling: 최근 5개 이상 스냅샷에서 값이 연속 감소
        - flat: 그 외
        """
        if len(history) < 3:
            return "flat"

        values = [s.get(field, 0) for s in history]

        # 연속 증가/감소 카운트
        increasing = 0
        decreasing = 0
        for i in range(1, len(values)):
            if values[i] > values[i - 1]:
                increasing += 1
            elif values[i] < values[i - 1]:
                decreasing += 1

        total = len(values) - 1
        if increasing >= total * 0.6:
            return "rising"
        elif decreasing >= total * 0.6:
            return "falling"
        return "flat"

    async def _save_supply_snapshot(self, snapshot: dict) -> None:
        """수급 스냅샷을 DB에 저장"""
        try:
            async with self.async_session() as db:
                await db.execute(
                    text(
                        "INSERT INTO supply_snapshots "
                        "(snapshot_time, market, index_value, index_change_rate, "
                        "foreign_net_buy, institution_net_buy, individual_net_buy, "
                        "foreign_trend, institution_trend, details) "
                        "VALUES (:time, :market, :idx, :rate, "
                        ":foreign, :institution, :individual, "
                        ":f_trend, :i_trend, :details::jsonb)"
                    ),
                    {
                        "time": snapshot["snapshot_time"],
                        "market": snapshot["market"],
                        "idx": snapshot["index_value"],
                        "rate": snapshot["index_change_rate"],
                        "foreign": snapshot["foreign_net_buy"],
                        "institution": snapshot["institution_net_buy"],
                        "individual": snapshot["individual_net_buy"],
                        "f_trend": snapshot["foreign_trend"],
                        "i_trend": snapshot["institution_trend"],
                        "details": json.dumps(snapshot, ensure_ascii=False),
                    },
                )
                await db.commit()
                logger.debug("수급 스냅샷 저장: %s", snapshot["market"])
        except Exception:
            logger.exception("수급 스냅샷 DB 저장 실패")

    async def close(self) -> None:
        """리소스 정리"""
        await self.rest_client.aclose()
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
