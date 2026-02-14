"""자체 조건 검색 엔진.

KIS API는 HTS 조건검색을 직접 지원하지 않으므로
전 종목을 스캔하여 사용자 정의 조건에 맞는 종목을 필터링한다.
"""

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .broker.base import BaseBroker

logger = logging.getLogger(__name__)


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

        실제 구현 시 KIS의 업종별 시세 조회 API를 호출하고,
        필요한 재무 데이터는 DB 캐시에서 보강한다.
        """
        # TODO: KIS API 업종별 시세 조회 구현
        # 현재는 빈 리스트 반환 (구현 예정)
        logger.info("시장 데이터 조회: %s", markets)
        return []

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
                    "VALUES (:cid, :ticker, :name, :price, :volume, :details)"
                ),
                {
                    "cid": condition_id,
                    "ticker": r.get("ticker", ""),
                    "name": r.get("name", ""),
                    "price": r.get("price", 0),
                    "volume": r.get("volume", 0),
                    "details": r,
                },
            )
            count += 1
        await self.db.commit()
        return count
