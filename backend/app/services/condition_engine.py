"""자체 조건 검색 엔진.

KIS API는 HTS 조건검색을 직접 지원하지 않으므로
전 종목을 스캔하여 사용자 정의 조건에 맞는 종목을 필터링한다.
"""

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .broker.base import BaseBroker

logger = logging.getLogger(__name__)

# KIS 업종 코드 매핑
MARKET_SECTOR_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
}


class ConditionEngine:
    """자체 조건 검색 엔진"""

    def __init__(self, broker: BaseBroker, db: AsyncSession):
        self.broker = broker
        self.db = db

    async def scan(self, condition: dict) -> list[dict]:
        """
        전 종목 스캔하여 조건에 맞는 종목 반환.

        데이터 소스:
        1. KIS API: 현재가, 거래량, 등락률 (실시간)
        2. PostgreSQL: 캐시된 재무 데이터 (일 1회 갱신)
        3. 계산 필드: 이동평균선, 거래량 비율 등
        """
        markets = condition.get("market", ["KOSPI", "KOSDAQ"])
        all_stocks = await self._fetch_market_data(markets)

        matched = []
        for stock in all_stocks:
            if self._evaluate_filters(stock, condition.get("filters", [])):
                matched.append(stock)

        sort_key = condition.get("sort_by", "volume_ratio")
        reverse = condition.get("sort_order", "desc") == "desc"
        matched.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)

        return matched[: condition.get("max_results", 20)]

    async def _fetch_market_data(self, markets: list[str]) -> list[dict]:
        """KIS 업종별 시세 API를 활용하여 전 종목 시세 조회.

        KIS의 국내주식 업종기간별시세(일봉) API가 아닌
        업종별 전종목 시세 조회 API를 사용하여 실시간 데이터를 가져온다.
        """
        logger.info("시장 데이터 조회: %s", markets)
        all_stocks: list[dict] = []

        await self.broker._ensure_token()

        for market in markets:
            sector_code = MARKET_SECTOR_CODES.get(market)
            if not sector_code:
                logger.warning("알 수 없는 시장 코드: %s", market)
                continue

            try:
                stocks = await self._fetch_sector_stocks(sector_code, market)
                all_stocks.extend(stocks)
            except Exception:
                logger.exception("시장 %s 데이터 조회 실패", market)

        logger.info("전체 종목 %d개 조회 완료", len(all_stocks))
        return all_stocks

    async def _fetch_sector_stocks(self, sector_code: str, market: str) -> list[dict]:
        """KIS 업종별 전종목 시세 조회 (거래량 상위)"""
        tr_id = "FHPST01710000"  # 국내주식 업종별 시세
        headers = self.broker._build_headers(tr_id)

        resp = await self.broker.client.get(
            f"{self.broker.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=headers,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": sector_code,
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "",
                "FID_TRGT_EXLS_CLS_CODE": "",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
                "FID_INPUT_DATE_1": "",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        stocks = []
        for item in data.get("output", []):
            ticker = item.get("mksc_shrn_iscd", "")
            if not ticker:
                continue

            current_price = int(item.get("stck_prpr", 0))
            volume = int(item.get("acml_vol", 0))
            change_rate = float(item.get("prdy_ctrt", 0))
            prev_volume = int(item.get("prdy_vol", 1)) or 1

            stocks.append({
                "ticker": ticker,
                "name": item.get("hts_kor_isnm", ""),
                "market": market,
                "price": current_price,
                "volume": volume,
                "change_rate": change_rate,
                "high": int(item.get("stck_hgpr", 0)),
                "low": int(item.get("stck_lwpr", 0)),
                "open": int(item.get("stck_oprc", 0)),
                "volume_ratio": round(volume / prev_volume, 2) if prev_volume else 0,
                "market_cap": int(item.get("stck_avls", 0)),
            })

        return stocks

    def _evaluate_filters(self, stock: dict, filters: list[dict]) -> bool:
        """모든 필터 조건을 만족하는지 평가"""
        for f in filters:
            value = stock.get(f["field"])
            if value is None:
                return False

            op = f["operator"]
            target = f["value"]

            if op == ">=" and value < target:
                return False
            elif op == "<=" and value > target:
                return False
            elif op == ">" and value <= target:
                return False
            elif op == "<" and value >= target:
                return False
            elif op == "between":
                if not (target[0] <= value <= target[1]):
                    return False
            elif op == "==" and value != target:
                return False

        return True

    async def save_results(self, condition_id: int, results: list[dict]) -> int:
        """검색 결과를 DB에 저장하고 저장된 건수를 반환"""
        count = 0
        for r in results:
            await self.db.execute(
                text(
                    "INSERT INTO search_results "
                    "(condition_id, ticker, ticker_name, price_at_match, volume_at_match, match_details) "
                    "VALUES (:cid, :ticker, :name, :price, :volume, :details::jsonb)"
                ),
                {
                    "cid": condition_id,
                    "ticker": r.get("ticker", ""),
                    "name": r.get("name", ""),
                    "price": r.get("price", 0),
                    "volume": r.get("volume", 0),
                    "details": json.dumps(r, ensure_ascii=False),
                },
            )
            count += 1
        await self.db.commit()
        return count
