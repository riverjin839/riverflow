"""시황 개요 - Naver Finance 기반 국내/해외 지수 + RSI + 차트.

국내: m.stock.naver.com/api/index/ (basic + price history)
해외: finance.naver.com/world/worldDayListJson (일봉 JSON)
Fallback: Yahoo Finance v8 chart API
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..core.security import verify_token

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA}

# ── 국내 지수 ──
DOMESTIC = [
    {"name": "코스피", "code": "KOSPI", "link": "https://m.stock.naver.com/domestic/index/KOSPI/total"},
    {"name": "코스닥", "code": "KOSDAQ", "link": "https://m.stock.naver.com/domestic/index/KOSDAQ/total"},
    {"name": "코스피200", "code": "KPI200", "link": "https://m.stock.naver.com/domestic/index/KPI200/total"},
]

# ── 해외 지수 (Naver world symbol: EXCHANGE@CODE) ──
GLOBAL = [
    {"name": "나스닥 종합", "naver": "NAS@IXIC", "yahoo": "^IXIC", "link": "https://m.stock.naver.com/worldstock/index/CCMP/total"},
    {"name": "나스닥100 선물", "naver": None, "yahoo": "NQ=F", "link": "https://finance.yahoo.com/quote/NQ=F"},
    {"name": "S&P 500", "naver": "SPI@SPX", "yahoo": "^GSPC", "link": "https://m.stock.naver.com/worldstock/index/SPX/total"},
    {"name": "다우존스", "naver": "DJI@DJI", "yahoo": "^DJI", "link": "https://m.stock.naver.com/worldstock/index/DJI/total"},
    {"name": "필라델피아 반도체", "naver": "PHL@SOX", "yahoo": "^SOX", "link": "https://m.stock.naver.com/worldstock/index/SOX/total"},
]


# ══════════════════════════════════════
# 공통 유틸
# ══════════════════════════════════════

def _nf(val) -> float:
    """Naver 숫자 파싱."""
    if val is None:
        return 0.0
    return float(str(val).replace(",", ""))


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


def _empty(name: str = "", code: str = "", link: str = "") -> dict:
    return {
        "name": name, "code": code, "link": link,
        "value": 0, "change": 0, "change_rate": 0,
        "high": 0, "low": 0, "volume": 0, "rsi": None,
    }


# ══════════════════════════════════════
# Naver: 국내 지수
# ══════════════════════════════════════

async def _naver_domestic(client: httpx.AsyncClient, idx: dict) -> dict:
    code = idx["code"]
    name = idx["name"]
    link = idx["link"]

    # 기본 시세
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/index/{code}/basic",
            headers=_HEADERS,
        )
        resp.raise_for_status()
        d = resp.json()
        price = _nf(d.get("closePrice"))
        if price <= 0:
            return _empty(name, code, link)

        change = _nf(d.get("compareToPreviousClosePrice"))
        rate = _nf(d.get("fluctuationsRatio"))

        # 고가/저가: 여러 필드명 시도
        high = _nf(d.get("highPrice") or d.get("todayHighPrice") or d.get("dayHighPrice"))
        low = _nf(d.get("lowPrice") or d.get("todayLowPrice") or d.get("dayLowPrice"))
        volume = int(_nf(d.get("accumulatedTradingVolume", 0)))
    except Exception as e:
        logger.warning("Naver domestic %s: %s", code, e)
        return _empty(name, code, link)

    # 고가/저가 보충: price history에서 오늘 데이터 가져오기
    history = await _naver_domestic_history(client, code, 30)
    rsi = _calc_rsi([h["close"] for h in history]) if len(history) > 14 else None

    if (high == 0 or low == 0) and history:
        latest = history[-1]
        high = high or latest.get("high", 0)
        low = low or latest.get("low", 0)

    return {
        "name": name, "code": code, "link": link,
        "value": price, "change": change, "change_rate": rate,
        "high": high, "low": low, "volume": volume, "rsi": rsi,
    }


async def _naver_domestic_history(client: httpx.AsyncClient, code: str, count: int = 30) -> list[dict]:
    """Naver 국내 지수 일봉 히스토리. [{date, open, high, low, close, volume}, ...]"""
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/index/{code}/price",
            params={"page": 1, "pageSize": count},
            headers=_HEADERS,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data if isinstance(data, list) else data.get("priceInfos", data.get("items", []))
        if not isinstance(items, list):
            return []

        result = []
        for item in reversed(items):
            close = _nf(item.get("closePrice") or item.get("cp"))
            if close <= 0:
                continue
            result.append({
                "date": item.get("localTradedAt", item.get("dt", "")),
                "open": _nf(item.get("openPrice") or item.get("op", 0)),
                "high": _nf(item.get("highPrice") or item.get("hp", 0)),
                "low": _nf(item.get("lowPrice") or item.get("lp", 0)),
                "close": close,
                "volume": int(_nf(item.get("accumulatedTradingVolume") or item.get("aq", 0))),
            })
        return result
    except Exception as e:
        logger.debug("Naver domestic history %s: %s", code, e)
        return []


# ══════════════════════════════════════
# Naver: 해외 지수 (worldDayListJson)
# ══════════════════════════════════════

async def _naver_global(client: httpx.AsyncClient, idx: dict) -> dict:
    name = idx["name"]
    naver_sym = idx.get("naver")
    yahoo_sym = idx.get("yahoo", "")
    link = idx.get("link", "")
    code = naver_sym or yahoo_sym

    # Naver classic world JSON API
    if naver_sym:
        history = await _naver_world_history(client, naver_sym, 30)
        if history:
            latest = history[-1]
            closes = [h["close"] for h in history]
            rsi = _calc_rsi(closes)
            prev_close = history[-2]["close"] if len(history) >= 2 else latest["close"]
            change = round(latest["close"] - prev_close, 2)
            rate = round(change / prev_close * 100, 2) if prev_close else 0
            return {
                "name": name, "code": code, "link": link,
                "value": latest["close"],
                "change": change,
                "change_rate": rate,
                "high": latest.get("high", 0),
                "low": latest.get("low", 0),
                "volume": latest.get("volume", 0),
                "rsi": rsi,
            }

    # Yahoo fallback
    if yahoo_sym:
        r = await _yahoo_chart(client, yahoo_sym, name, code, link)
        if r["value"] > 0:
            return r

    return _empty(name, code, link)


async def _naver_world_history(client: httpx.AsyncClient, symbol: str, count: int = 30) -> list[dict]:
    """Naver 해외 지수 일봉 데이터 (worldDayListJson)."""
    try:
        resp = await client.get(
            "https://finance.naver.com/world/worldDayListJson.naver",
            params={"symbol": symbol, "fdtc": "0", "page": 1},
            headers=_HEADERS,
        )
        if resp.status_code != 200:
            logger.debug("Naver world history %s: HTTP %d", symbol, resp.status_code)
            return []

        items = resp.json()
        if not isinstance(items, list):
            return []

        result = []
        for item in reversed(items[:count]):
            close = _nf(item.get("clos"))
            if close <= 0:
                continue
            result.append({
                "date": item.get("xymd", ""),
                "open": _nf(item.get("open", 0)),
                "high": _nf(item.get("high", 0)),
                "low": _nf(item.get("low", 0)),
                "close": close,
                "volume": int(_nf(item.get("gvol", 0))),
            })
        return result
    except Exception as e:
        logger.debug("Naver world history %s: %s", symbol, e)
        return []


# ══════════════════════════════════════
# 코스닥150 야간선물
# ══════════════════════════════════════

async def _kosdaq_night_futures(client: httpx.AsyncClient) -> dict:
    name = "코스닥150 야간선물"
    code = "KQ150NF"
    link = "https://finance.naver.com/sise/sise_index.naver?code=KQ150"

    # Naver 모바일 API
    for ep in ["KOSDAQ150FUT", "KQ150F"]:
        try:
            resp = await client.get(
                f"https://m.stock.naver.com/api/index/{ep}/basic",
                headers=_HEADERS,
            )
            if resp.status_code == 200:
                d = resp.json()
                price = _nf(d.get("closePrice"))
                if price > 0:
                    return {
                        "name": name, "code": code, "link": link,
                        "value": price,
                        "change": _nf(d.get("compareToPreviousClosePrice")),
                        "change_rate": _nf(d.get("fluctuationsRatio")),
                        "high": _nf(d.get("highPrice")),
                        "low": _nf(d.get("lowPrice")),
                        "volume": 0, "rsi": None,
                    }
        except Exception as e:
            logger.debug("Naver KQ150 futures (%s): %s", ep, e)

    # Naver polling API
    try:
        resp = await client.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": "SERVICE_ITEM:106S3000"},
            headers=_HEADERS,
        )
        if resp.status_code == 200:
            areas = resp.json().get("result", {}).get("areas", [])
            if areas and areas[0].get("datas"):
                item = areas[0]["datas"][0]
                nv = float(item.get("nv", 0))
                divisor = 100 if nv > 100000 else 1
                return {
                    "name": name, "code": code, "link": link,
                    "value": round(nv / divisor, 2),
                    "change": round(float(item.get("cv", 0)) / divisor, 2),
                    "change_rate": float(item.get("cr", 0)),
                    "high": round(float(item.get("h", 0)) / divisor, 2),
                    "low": round(float(item.get("l", 0)) / divisor, 2),
                    "volume": int(item.get("aq", 0)), "rsi": None,
                }
    except Exception as e:
        logger.debug("Naver polling KQ150: %s", e)

    return _empty(name, code, link)


# ══════════════════════════════════════
# Yahoo Finance (fallback)
# ══════════════════════════════════════

async def _yahoo_chart(client: httpx.AsyncClient, symbol: str, name: str, code: str, link: str) -> dict:
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        try:
            resp = await client.get(
                f"https://{host}/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1mo"},
                headers=_HEADERS, follow_redirects=True,
            )
            resp.raise_for_status()
            results = resp.json().get("chart", {}).get("result")
            if not results:
                continue
            meta = results[0].get("meta", {})
            quotes = results[0].get("indicators", {}).get("quote", [{}])[0]
            closes = [c for c in quotes.get("close", []) if c is not None]
            price = meta.get("regularMarketPrice", 0)
            prev = meta.get("previousClose") or meta.get("chartPreviousClose") or price
            change = round(price - prev, 2) if prev else 0
            rate = round(change / prev * 100, 2) if prev else 0
            highs = quotes.get("high", [])
            lows = quotes.get("low", [])
            return {
                "name": name, "code": code, "link": link,
                "value": round(price, 2), "change": change, "change_rate": rate,
                "high": round(next((h for h in reversed(highs) if h), price), 2),
                "low": round(next((l for l in reversed(lows) if l), price), 2),
                "volume": int(next((v for v in reversed(quotes.get("volume", [])) if v), 0)),
                "rsi": _calc_rsi(closes),
            }
        except Exception as e:
            logger.debug("Yahoo %s (%s): %s", symbol, host, e)
    return _empty(name, code, link)


async def _yahoo_history(client: httpx.AsyncClient, symbol: str, count: int = 30) -> list[dict]:
    """Yahoo Finance v8 chart → 일봉 히스토리."""
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        try:
            resp = await client.get(
                f"https://{host}/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "3mo"},
                headers=_HEADERS, follow_redirects=True,
            )
            resp.raise_for_status()
            results = resp.json().get("chart", {}).get("result")
            if not results:
                continue
            timestamps = results[0].get("timestamp", [])
            quotes = results[0].get("indicators", {}).get("quote", [{}])[0]
            result = []
            for i, ts in enumerate(timestamps):
                c = quotes.get("close", [None] * len(timestamps))[i]
                if c is None:
                    continue
                result.append({
                    "date": datetime.fromtimestamp(ts).strftime("%Y%m%d"),
                    "open": round(quotes.get("open", [0] * len(timestamps))[i] or 0, 2),
                    "high": round(quotes.get("high", [0] * len(timestamps))[i] or 0, 2),
                    "low": round(quotes.get("low", [0] * len(timestamps))[i] or 0, 2),
                    "close": round(c, 2),
                    "volume": int(quotes.get("volume", [0] * len(timestamps))[i] or 0),
                })
            return result[-count:]
        except Exception as e:
            logger.debug("Yahoo history %s (%s): %s", symbol, host, e)
    return []


# ══════════════════════════════════════
# 커스텀 종목 조회
# ══════════════════════════════════════

async def _naver_stock_quote(client: httpx.AsyncClient, ticker: str) -> dict | None:
    """Naver Finance 개별 종목 시세 조회 (6자리 종목코드)."""
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/stock/{ticker}/basic",
            headers=_HEADERS,
        )
        if resp.status_code != 200:
            return None
        d = resp.json()
        price = _nf(d.get("closePrice"))
        if price <= 0:
            return None
        name = d.get("stockName", ticker)

        # RSI from history
        hist_resp = await client.get(
            f"https://m.stock.naver.com/api/stock/{ticker}/price",
            params={"page": 1, "pageSize": 30},
            headers=_HEADERS,
        )
        rsi = None
        if hist_resp.status_code == 200:
            hist_data = hist_resp.json()
            items = hist_data if isinstance(hist_data, list) else hist_data.get("priceInfos", hist_data.get("items", []))
            if isinstance(items, list) and items:
                closes = [_nf(i.get("closePrice") or i.get("cp")) for i in reversed(items) if i.get("closePrice") or i.get("cp")]
                rsi = _calc_rsi(closes)

        return {
            "name": name, "code": ticker,
            "link": f"https://m.stock.naver.com/domestic/stock/{ticker}/total",
            "value": price,
            "change": _nf(d.get("compareToPreviousClosePrice")),
            "change_rate": _nf(d.get("fluctuationsRatio")),
            "high": _nf(d.get("highPrice") or d.get("todayHighPrice")),
            "low": _nf(d.get("lowPrice") or d.get("todayLowPrice")),
            "volume": int(_nf(d.get("accumulatedTradingVolume", 0))),
            "rsi": rsi,
        }
    except Exception as e:
        logger.debug("Naver stock %s: %s", ticker, e)
        return None


# ══════════════════════════════════════
# API 엔드포인트
# ══════════════════════════════════════

@router.get("/overview")
async def market_overview(_: dict = Depends(verify_token)):
    """국내/해외 주요 지수 시황 조회."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        tasks: list = []
        for idx in DOMESTIC:
            tasks.append(_naver_domestic(client, idx))
        tasks.append(_kosdaq_night_futures(client))
        for idx in GLOBAL:
            tasks.append(_naver_global(client, idx))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        n_dom = len(DOMESTIC)
        domestic: list[dict] = []
        for i in range(n_dom):
            r = results[i]
            domestic.append(r if isinstance(r, dict) else _empty(DOMESTIC[i]["name"], DOMESTIC[i]["code"], DOMESTIC[i]["link"]))
        fut = results[n_dom]
        domestic.append(fut if isinstance(fut, dict) else _empty("코스닥150 야간선물", "KQ150NF"))

        global_list: list[dict] = []
        for i, idx in enumerate(GLOBAL):
            r = results[n_dom + 1 + i]
            global_list.append(r if isinstance(r, dict) else _empty(idx["name"], idx.get("naver") or idx.get("yahoo", ""), idx.get("link", "")))

    return JSONResponse(
        content={"domestic": domestic, "global": global_list, "updated_at": datetime.now(timezone.utc).isoformat()},
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/chart")
async def market_chart(
    code: str = Query(..., description="지수/종목 코드 (KOSPI, NAS@IXIC, 005930 등)"),
    type: str = Query("domestic", description="domestic / global / stock"),
    days: int = Query(30, ge=5, le=90),
    _: dict = Depends(verify_token),
):
    """차트용 히스토리 데이터 조회."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        if type == "domestic":
            prices = await _naver_domestic_history(client, code, days)
        elif type == "global":
            prices = await _naver_world_history(client, code, days)
            if not prices:
                # Naver 실패 시 Yahoo fallback (code에서 yahoo symbol 찾기)
                yahoo_sym = code
                for g in GLOBAL:
                    if g.get("naver") == code:
                        yahoo_sym = g.get("yahoo", code)
                        break
                prices = await _yahoo_history(client, yahoo_sym, days)
        elif type == "stock":
            prices = await _naver_domestic_history(client, code, days)
            if not prices:
                # 개별 종목 히스토리
                try:
                    resp = await client.get(
                        f"https://m.stock.naver.com/api/stock/{code}/price",
                        params={"page": 1, "pageSize": days},
                        headers=_HEADERS,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data if isinstance(data, list) else data.get("priceInfos", data.get("items", []))
                        if isinstance(items, list):
                            prices = []
                            for item in reversed(items):
                                c = _nf(item.get("closePrice") or item.get("cp"))
                                if c > 0:
                                    prices.append({
                                        "date": item.get("localTradedAt", ""),
                                        "open": _nf(item.get("openPrice") or item.get("op", 0)),
                                        "high": _nf(item.get("highPrice") or item.get("hp", 0)),
                                        "low": _nf(item.get("lowPrice") or item.get("lp", 0)),
                                        "close": c,
                                        "volume": int(_nf(item.get("accumulatedTradingVolume") or item.get("aq", 0))),
                                    })
                except Exception:
                    prices = []
        else:
            prices = []

    return {"code": code, "type": type, "prices": prices}


@router.get("/quote")
async def market_quote(
    code: str = Query(..., description="종목코드 (예: 005930, 035720)"),
    _: dict = Depends(verify_token),
):
    """개별 종목 시세 조회 (커스텀 카드용)."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        result = await _naver_stock_quote(client, code)
        if result:
            return result
    return {"error": f"종목 '{code}'을 찾을 수 없습니다", "code": code}


@router.get("/check")
async def market_check(_: dict = Depends(verify_token)):
    """데이터 소스 연결 진단."""
    sources = {
        "naver_domestic": "https://m.stock.naver.com/api/index/KOSPI/basic",
        "naver_world_json": "https://finance.naver.com/world/worldDayListJson.naver?symbol=NAS@IXIC&fdtc=0&page=1",
        "naver_polling": "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI",
        "yahoo_v8": "https://query1.finance.yahoo.com/v8/finance/chart/^KS11?interval=1d&range=5d",
    }
    report: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for label, url in sources.items():
            try:
                resp = await client.get(url, headers=_HEADERS)
                report[label] = {"status": resp.status_code, "ok": resp.status_code == 200, "preview": resp.text[:300]}
            except Exception as e:
                report[label] = {"status": 0, "ok": False, "error": str(e)}
    return report
