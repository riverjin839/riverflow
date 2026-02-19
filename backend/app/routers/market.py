"""시황 개요 - Yahoo Finance 기반 국내/해외 지수 + RSI 조회.

KIS API는 인증 토큰이 필요하고 모의투자 환경에서 지수 조회가 불안정하므로,
Yahoo Finance를 primary 소스로 사용한다.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..core.security import verify_token

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Yahoo Finance 심볼 매핑
INDICES = [
    # 국내
    {"name": "코스피", "symbol": "^KS11", "group": "domestic"},
    {"name": "코스닥", "symbol": "^KQ11", "group": "domestic"},
    {"name": "코스피200", "symbol": "^KS200", "group": "domestic"},
    # 해외
    {"name": "나스닥 종합", "symbol": "^IXIC", "group": "global"},
    {"name": "나스닥100 선물", "symbol": "NQ=F", "group": "global"},
    {"name": "S&P 500", "symbol": "^GSPC", "group": "global"},
    {"name": "다우존스", "symbol": "^DJI", "group": "global"},
    {"name": "필라델피아 반도체", "symbol": "^SOX", "group": "global"},
]

# 코스닥150 야간선물은 Yahoo에 없으므로 별도 처리
KOSDAQ_NIGHT_FUTURES = {"name": "코스닥150 야간선물", "code": "KQ150NF"}


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI 계산 (Wilder's smoothing method)."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    # 초기 평균
    avg_gain = sum(max(d, 0) for d in deltas[:period]) / period
    avg_loss = sum(abs(min(d, 0)) for d in deltas[:period]) / period
    # Wilder smoothing
    for d in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + abs(min(d, 0))) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _empty(name: str = "", code: str = "") -> dict:
    return {
        "name": name,
        "code": code,
        "value": 0,
        "change": 0,
        "change_rate": 0,
        "high": 0,
        "low": 0,
        "volume": 0,
        "rsi": None,
    }


async def _fetch_yahoo(client: httpx.AsyncClient, idx: dict) -> dict:
    """Yahoo Finance v8 chart API로 지수 데이터 + RSI 계산."""
    symbol = idx["symbol"]
    try:
        resp = await client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "1mo"},
            headers={"User-Agent": _UA},
        )
        resp.raise_for_status()
        body = resp.json()

        results = body.get("chart", {}).get("result")
        if not results:
            logger.warning("Yahoo 빈 결과: %s", symbol)
            return _empty(idx["name"], symbol)

        meta = results[0].get("meta", {})
        quotes = results[0].get("indicators", {}).get("quote", [{}])[0]

        # 종가 리스트 (RSI 계산용)
        closes_raw = quotes.get("close", [])
        closes = [c for c in closes_raw if c is not None]

        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
        change = round(price - prev, 2) if prev else 0
        rate = round(change / prev * 100, 2) if prev else 0

        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        vols = quotes.get("volume", [])

        # 마지막 유효값 추출
        today_high = next((h for h in reversed(highs) if h is not None), price)
        today_low = next((l for l in reversed(lows) if l is not None), price)
        today_vol = next((v for v in reversed(vols) if v is not None), 0)

        return {
            "name": idx["name"],
            "code": symbol,
            "value": round(price, 2),
            "change": change,
            "change_rate": rate,
            "high": round(today_high, 2),
            "low": round(today_low, 2),
            "volume": int(today_vol),
            "rsi": _calc_rsi(closes),
        }
    except Exception as e:
        logger.warning("Yahoo 조회 실패 (%s): %s", symbol, e)
        return _empty(idx["name"], symbol)


async def _fetch_naver_kosdaq_futures(client: httpx.AsyncClient) -> dict:
    """코스닥150 선물 시세 조회 (Naver Finance 다중 소스 시도)."""
    name = KOSDAQ_NIGHT_FUTURES["name"]
    code = KOSDAQ_NIGHT_FUTURES["code"]

    # 시도 1: Naver 모바일 API
    naver_endpoints = [
        "https://m.stock.naver.com/api/index/KOSDAQ150FUT/basic",
        "https://m.stock.naver.com/api/index/KQ150F/basic",
    ]
    for url in naver_endpoints:
        try:
            resp = await client.get(url, headers={"User-Agent": _UA})
            if resp.status_code == 200:
                d = resp.json()
                price_str = d.get("closePrice") or d.get("nowVal") or "0"
                price = float(str(price_str).replace(",", ""))
                if price > 0:
                    change_str = d.get("compareToPreviousClosePrice") or d.get("changeVal") or "0"
                    rate_str = d.get("fluctuationsRatio") or d.get("changeRate") or "0"
                    high_str = d.get("highPrice") or d.get("high") or "0"
                    low_str = d.get("lowPrice") or d.get("low") or "0"
                    return {
                        "name": name,
                        "code": code,
                        "value": price,
                        "change": float(str(change_str).replace(",", "")),
                        "change_rate": float(str(rate_str).replace(",", "")),
                        "high": float(str(high_str).replace(",", "")),
                        "low": float(str(low_str).replace(",", "")),
                        "volume": 0,
                        "rsi": None,
                    }
        except Exception as e:
            logger.debug("Naver 코스닥150선물 조회 실패 (%s): %s", url, e)

    # 시도 2: Naver 실시간 polling API (선물 코드: 106S3000)
    try:
        resp = await client.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": "SERVICE_ITEM:106S3000"},
            headers={"User-Agent": _UA},
        )
        if resp.status_code == 200:
            d = resp.json()
            areas = d.get("result", {}).get("areas", [])
            if areas:
                datas = areas[0].get("datas", [])
                if datas:
                    item = datas[0]
                    nv = float(item.get("nv", 0))
                    # Naver 선물 가격은 100으로 나누어야 할 수 있음
                    divisor = 100 if nv > 100000 else 1
                    return {
                        "name": name,
                        "code": code,
                        "value": round(nv / divisor, 2),
                        "change": round(float(item.get("cv", 0)) / divisor, 2),
                        "change_rate": float(item.get("cr", 0)),
                        "high": round(float(item.get("h", 0)) / divisor, 2),
                        "low": round(float(item.get("l", 0)) / divisor, 2),
                        "volume": int(item.get("aq", 0)),
                        "rsi": None,
                    }
    except Exception as e:
        logger.debug("Naver polling 코스닥150선물 조회 실패: %s", e)

    return _empty(name, code)


@router.get("/overview")
async def market_overview(_: dict = Depends(verify_token)):
    """국내/해외 주요 지수 시황 조회 (Yahoo Finance + RSI)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 모든 지수 + 코스닥 야간선물 병렬 조회
        tasks = [_fetch_yahoo(client, idx) for idx in INDICES]
        tasks.append(_fetch_naver_kosdaq_futures(client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        domestic: list[dict] = []
        global_list: list[dict] = []

        for i, idx in enumerate(INDICES):
            r = results[i]
            entry = r if isinstance(r, dict) else _empty(idx["name"], idx["symbol"])
            if idx["group"] == "domestic":
                domestic.append(entry)
            else:
                global_list.append(entry)

        # 코스닥150 야간선물 (마지막 결과)
        futures_r = results[-1]
        futures_entry = (
            futures_r
            if isinstance(futures_r, dict)
            else _empty(KOSDAQ_NIGHT_FUTURES["name"], KOSDAQ_NIGHT_FUTURES["code"])
        )
        domestic.append(futures_entry)

    return JSONResponse(
        content={
            "domestic": domestic,
            "global": global_list,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )
