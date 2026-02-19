"""시황 개요 - Naver Finance(primary) + Yahoo Finance(fallback) 기반 지수 + RSI.

K8s 클러스터 내부에서 Yahoo Finance API가 차단될 수 있으므로,
한국 네트워크에서 안정적인 Naver Finance를 primary로 사용한다.
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

# ── 국내 지수 (Naver Finance) ──
DOMESTIC = [
    {"name": "코스피", "naver": "KOSPI"},
    {"name": "코스닥", "naver": "KOSDAQ"},
    {"name": "코스피200", "naver": "KPI200"},
]

# ── 해외 지수 (Naver world stock + Yahoo fallback) ──
GLOBAL = [
    {"name": "나스닥 종합", "naver": "CCMP", "yahoo": "^IXIC"},
    {"name": "나스닥100 선물", "naver": None, "yahoo": "NQ=F"},
    {"name": "S&P 500", "naver": "SPX", "yahoo": "^GSPC"},
    {"name": "다우존스", "naver": "DJI", "yahoo": "^DJI"},
    {"name": "필라델피아 반도체", "naver": "SOX", "yahoo": "^SOX"},
]


# ── 공통 ──

def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI 계산 (Wilder's smoothing method)."""
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


def _nf(val) -> float:
    """Naver 숫자 파싱 (콤마, 문자열 처리)."""
    if val is None:
        return 0.0
    return float(str(val).replace(",", ""))


def _empty(name: str = "", code: str = "") -> dict:
    return {
        "name": name, "code": code,
        "value": 0, "change": 0, "change_rate": 0,
        "high": 0, "low": 0, "volume": 0, "rsi": None,
    }


# ── Naver Finance: 국내 지수 ──

async def _naver_domestic(client: httpx.AsyncClient, idx: dict) -> dict:
    """Naver 국내 지수 기본시세 + 히스토리(RSI)."""
    code = idx["naver"]
    name = idx["name"]
    headers = {"User-Agent": _UA}

    # 기본 시세
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/index/{code}/basic",
            headers=headers,
        )
        resp.raise_for_status()
        d = resp.json()
        price = _nf(d.get("closePrice"))
        if price <= 0:
            logger.warning("Naver domestic %s: price=0, raw=%s", code, d)
            return _empty(name, code)
        change = _nf(d.get("compareToPreviousClosePrice"))
        rate = _nf(d.get("fluctuationsRatio"))
        high = _nf(d.get("highPrice"))
        low = _nf(d.get("lowPrice"))
        volume = int(_nf(d.get("accumulatedTradingVolume", 0)))
    except Exception as e:
        logger.warning("Naver domestic %s 실패: %s", code, e)
        return _empty(name, code)

    # 히스토리 (RSI 계산)
    rsi = await _naver_domestic_rsi(client, code)

    return {
        "name": name, "code": code,
        "value": price, "change": change, "change_rate": rate,
        "high": high, "low": low, "volume": volume, "rsi": rsi,
    }


async def _naver_domestic_rsi(client: httpx.AsyncClient, code: str) -> float | None:
    """Naver 국내 지수 일봉 히스토리 → RSI 계산."""
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/index/{code}/price",
            params={"page": 1, "pageSize": 30},
            headers={"User-Agent": _UA},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Naver 응답 구조: list 또는 {"priceInfos": [...]}
        items = data if isinstance(data, list) else data.get("priceInfos", data.get("items", []))
        if not isinstance(items, list) or not items:
            return None
        closes = []
        for item in reversed(items):  # 오래된 순으로
            cp = item.get("closePrice") or item.get("cp")
            if cp is not None:
                closes.append(_nf(cp))
        return _calc_rsi(closes)
    except Exception as e:
        logger.debug("Naver domestic RSI %s: %s", code, e)
        return None


# ── Naver Finance: 해외 지수 ──

async def _naver_global(client: httpx.AsyncClient, idx: dict) -> dict:
    """Naver 해외 지수 조회. 실패 시 Yahoo fallback."""
    name = idx["name"]
    naver_code = idx.get("naver")
    yahoo_sym = idx.get("yahoo", "")
    code = naver_code or yahoo_sym
    headers = {"User-Agent": _UA}

    # Naver 해외지수 API 시도 (여러 코드 패턴)
    if naver_code:
        for nc in [naver_code, f".{naver_code}"]:
            try:
                resp = await client.get(
                    f"https://m.stock.naver.com/api/worldstock/index/{nc}/basic",
                    headers=headers,
                )
                if resp.status_code == 200:
                    d = resp.json()
                    price = _nf(d.get("closePrice") or d.get("stockItemTotalInfos", [{}])[0].get("value") if isinstance(d.get("stockItemTotalInfos"), list) else d.get("closePrice"))
                    if not price:
                        price = _nf(d.get("closePrice"))
                    if price and price > 0:
                        change = _nf(d.get("compareToPreviousClosePrice"))
                        rate = _nf(d.get("fluctuationsRatio"))
                        high = _nf(d.get("highPrice"))
                        low = _nf(d.get("lowPrice"))
                        rsi = await _naver_global_rsi(client, nc)
                        return {
                            "name": name, "code": code,
                            "value": price, "change": change, "change_rate": rate,
                            "high": high, "low": low, "volume": 0, "rsi": rsi,
                        }
            except Exception as e:
                logger.debug("Naver global %s (%s): %s", name, nc, e)

    # Yahoo Finance fallback
    if yahoo_sym:
        r = await _yahoo_chart(client, yahoo_sym, name, code)
        if r["value"] > 0:
            return r

    return _empty(name, code)


async def _naver_global_rsi(client: httpx.AsyncClient, code: str) -> float | None:
    """Naver 해외 지수 히스토리 → RSI 계산."""
    try:
        resp = await client.get(
            f"https://m.stock.naver.com/api/worldstock/index/{code}/price",
            params={"page": 1, "pageSize": 30},
            headers={"User-Agent": _UA},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data if isinstance(data, list) else data.get("priceInfos", data.get("items", []))
        if not isinstance(items, list) or not items:
            return None
        closes = []
        for item in reversed(items):
            cp = item.get("closePrice") or item.get("cp")
            if cp is not None:
                closes.append(_nf(cp))
        return _calc_rsi(closes)
    except Exception as e:
        logger.debug("Naver global RSI %s: %s", code, e)
        return None


# ── Yahoo Finance (fallback) ──

async def _yahoo_chart(client: httpx.AsyncClient, symbol: str, name: str, code: str) -> dict:
    """Yahoo Finance v8 chart API (fallback)."""
    for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
        try:
            resp = await client.get(
                f"https://{host}/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1mo"},
                headers={"User-Agent": _UA},
                follow_redirects=True,
            )
            resp.raise_for_status()
            body = resp.json()
            results = body.get("chart", {}).get("result")
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
            vols = quotes.get("volume", [])

            return {
                "name": name, "code": code,
                "value": round(price, 2),
                "change": change,
                "change_rate": rate,
                "high": round(next((h for h in reversed(highs) if h), price), 2),
                "low": round(next((l for l in reversed(lows) if l), price), 2),
                "volume": int(next((v for v in reversed(vols) if v), 0)),
                "rsi": _calc_rsi(closes),
            }
        except Exception as e:
            logger.debug("Yahoo %s (%s): %s", symbol, host, e)

    return _empty(name, code)


# ── 코스닥150 야간선물 ──

async def _kosdaq_night_futures(client: httpx.AsyncClient) -> dict:
    """코스닥150 야간선물 시세 조회."""
    name = "코스닥150 야간선물"
    code = "KQ150NF"
    headers = {"User-Agent": _UA}

    # 시도 1: Naver 모바일 API
    for endpoint in ["KOSDAQ150FUT", "KQ150F"]:
        try:
            resp = await client.get(
                f"https://m.stock.naver.com/api/index/{endpoint}/basic",
                headers=headers,
            )
            if resp.status_code == 200:
                d = resp.json()
                price = _nf(d.get("closePrice"))
                if price > 0:
                    return {
                        "name": name, "code": code,
                        "value": price,
                        "change": _nf(d.get("compareToPreviousClosePrice")),
                        "change_rate": _nf(d.get("fluctuationsRatio")),
                        "high": _nf(d.get("highPrice")),
                        "low": _nf(d.get("lowPrice")),
                        "volume": 0, "rsi": None,
                    }
        except Exception as e:
            logger.debug("Naver KQ150 futures (%s): %s", endpoint, e)

    # 시도 2: Naver polling API
    try:
        resp = await client.get(
            "https://polling.finance.naver.com/api/realtime",
            params={"query": "SERVICE_ITEM:106S3000"},
            headers=headers,
        )
        if resp.status_code == 200:
            d = resp.json()
            areas = d.get("result", {}).get("areas", [])
            if areas and areas[0].get("datas"):
                item = areas[0]["datas"][0]
                nv = float(item.get("nv", 0))
                divisor = 100 if nv > 100000 else 1
                return {
                    "name": name, "code": code,
                    "value": round(nv / divisor, 2),
                    "change": round(float(item.get("cv", 0)) / divisor, 2),
                    "change_rate": float(item.get("cr", 0)),
                    "high": round(float(item.get("h", 0)) / divisor, 2),
                    "low": round(float(item.get("l", 0)) / divisor, 2),
                    "volume": int(item.get("aq", 0)),
                    "rsi": None,
                }
    except Exception as e:
        logger.debug("Naver polling KQ150 futures: %s", e)

    return _empty(name, code)


# ── API 엔드포인트 ──

@router.get("/overview")
async def market_overview(_: dict = Depends(verify_token)):
    """국내/해외 주요 지수 시황 조회."""
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        tasks: list = []
        # 국내 (Naver)
        for idx in DOMESTIC:
            tasks.append(_naver_domestic(client, idx))
        # 코스닥 야간선물
        tasks.append(_kosdaq_night_futures(client))
        # 해외 (Naver → Yahoo fallback)
        for idx in GLOBAL:
            tasks.append(_naver_global(client, idx))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        n_dom = len(DOMESTIC)
        domestic: list[dict] = []
        for i in range(n_dom):
            r = results[i]
            domestic.append(r if isinstance(r, dict) else _empty(DOMESTIC[i]["name"], DOMESTIC[i]["naver"]))

        # 코스닥 야간선물
        fut = results[n_dom]
        domestic.append(fut if isinstance(fut, dict) else _empty("코스닥150 야간선물", "KQ150NF"))

        global_list: list[dict] = []
        for i, idx in enumerate(GLOBAL):
            r = results[n_dom + 1 + i]
            global_list.append(r if isinstance(r, dict) else _empty(idx["name"], idx.get("naver") or idx.get("yahoo", "")))

    return JSONResponse(
        content={
            "domestic": domestic,
            "global": global_list,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.get("/check")
async def market_check(_: dict = Depends(verify_token)):
    """데이터 소스 연결 진단. 어떤 API가 작동하는지 확인."""
    sources = {
        "naver_domestic": "https://m.stock.naver.com/api/index/KOSPI/basic",
        "naver_global": "https://m.stock.naver.com/api/worldstock/index/CCMP/basic",
        "naver_polling": "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI",
        "yahoo_v8": "https://query1.finance.yahoo.com/v8/finance/chart/^KS11?interval=1d&range=5d",
    }
    report: dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for label, url in sources.items():
            try:
                resp = await client.get(url, headers={"User-Agent": _UA})
                body_preview = resp.text[:500]
                report[label] = {
                    "status": resp.status_code,
                    "ok": resp.status_code == 200,
                    "body_preview": body_preview,
                }
            except Exception as e:
                report[label] = {"status": 0, "ok": False, "error": str(e)}
    return report
