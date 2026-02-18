"""시황 개요 라우터 - 국내/해외 주요 지수 조회."""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends

from ..core.broker_config import broker_settings
from ..core.security import verify_token

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger(__name__)

# KIS API 업종 코드 매핑
DOMESTIC_INDICES = [
    {"name": "코스피", "code": "0001", "market": "U"},
    {"name": "코스닥", "code": "1001", "market": "U"},
    {"name": "코스피200", "code": "0028", "market": "U"},
    {"name": "KRX300", "code": "0347", "market": "U"},
]

# KIS 해외 지수 코드 (해외지수시세 API)
GLOBAL_INDICES = [
    {"name": "나스닥 종합", "code": "COMP", "exchange": "NAS"},
    {"name": "나스닥100 선물", "code": "NQ=F", "exchange": "NAS"},
    {"name": "S&P 500", "code": "SPX", "exchange": "NYS"},
    {"name": "다우존스", "code": "DJI", "exchange": "NYS"},
    {"name": "필라델피아 반도체", "code": "SOX", "exchange": "NYS"},
]


async def _fetch_domestic_index(client: httpx.AsyncClient, headers: dict, idx: dict) -> dict | None:
    """KIS 국내 업종 현재가 조회"""
    try:
        resp = await client.get(
            f"{_base_url()}/uapi/domestic-stock/v1/quotations/inquire-index-price",
            headers={**headers, "tr_id": "FHPUP02110000"},
            params={"FID_COND_MRKT_DIV_CODE": idx["market"], "FID_INPUT_ISCD": idx["code"]},
        )
        resp.raise_for_status()
        o = resp.json().get("output", {})
        return {
            "name": idx["name"],
            "code": idx["code"],
            "value": float(o.get("bstp_nmix_prpr", 0)),
            "change": float(o.get("bstp_nmix_prdy_vrss", 0)),
            "change_rate": float(o.get("bstp_nmix_prdy_ctrt", 0)),
            "high": float(o.get("bstp_nmix_hgpr", 0)),
            "low": float(o.get("bstp_nmix_lwpr", 0)),
            "volume": int(float(o.get("acml_vol", 0))),
        }
    except Exception:
        logger.debug("국내 지수 조회 실패: %s", idx["name"])
        return None


async def _fetch_global_index(client: httpx.AsyncClient, headers: dict, idx: dict) -> dict | None:
    """KIS 해외 지수 현재가 조회"""
    try:
        resp = await client.get(
            f"{_base_url()}/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
            headers={**headers, "tr_id": "FHKST03030100"},
            params={
                "FID_COND_MRKT_DIV_CODE": "N",
                "FID_INPUT_ISCD": idx["code"],
                "FID_INPUT_DATE_1": datetime.now().strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": datetime.now().strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        resp.raise_for_status()
        output = resp.json().get("output2", [])
        if not output:
            # 대안: 간단히 해외주식 현재가 시세 API 시도
            return _fallback_global(idx)
        latest = output[0]
        value = float(latest.get("ovrs_nmix_prpr", 0))
        prev = float(latest.get("ovrs_nmix_prdy_clpr", value))
        change = value - prev
        rate = (change / prev * 100) if prev else 0
        return {
            "name": idx["name"],
            "code": idx["code"],
            "value": value,
            "change": round(change, 2),
            "change_rate": round(rate, 2),
            "high": float(latest.get("ovrs_nmix_hgpr", 0)),
            "low": float(latest.get("ovrs_nmix_lwpr", 0)),
            "volume": 0,
        }
    except Exception:
        logger.debug("해외 지수 조회 실패: %s", idx["name"])
        return _fallback_global(idx)


def _fallback_global(idx: dict) -> dict:
    """API 실패 시 빈 데이터 반환"""
    return {
        "name": idx["name"],
        "code": idx["code"],
        "value": 0,
        "change": 0,
        "change_rate": 0,
        "high": 0,
        "low": 0,
        "volume": 0,
    }


def _base_url() -> str:
    if broker_settings.KIS_IS_VIRTUAL:
        return "https://openapivts.koreainvestment.com:29443"
    return "https://openapi.koreainvestment.com:9443"


async def _get_token(client: httpx.AsyncClient) -> str:
    """KIS OAuth 토큰 발급"""
    resp = await client.post(
        f"{_base_url()}/oauth2/tokenP",
        json={
            "grant_type": "client_credentials",
            "appkey": broker_settings.KIS_APP_KEY,
            "appsecret": broker_settings.KIS_APP_SECRET,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@router.get("/overview")
async def market_overview(_: dict = Depends(verify_token)):
    """국내/해외 주요 지수 시황 조회"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            token = await _get_token(client)
        except Exception:
            logger.exception("KIS 토큰 발급 실패")
            return {
                "domestic": [_fallback_global(i) for i in DOMESTIC_INDICES],
                "global": [_fallback_global(i) for i in GLOBAL_INDICES],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": broker_settings.KIS_APP_KEY,
            "appsecret": broker_settings.KIS_APP_SECRET,
        }

        domestic = []
        for idx in DOMESTIC_INDICES:
            result = await _fetch_domestic_index(client, headers, idx)
            domestic.append(result or _fallback_global(idx))

        global_indices = []
        for idx in GLOBAL_INDICES:
            result = await _fetch_global_index(client, headers, idx)
            global_indices.append(result or _fallback_global(idx))

    return {
        "domestic": domestic,
        "global": global_indices,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
