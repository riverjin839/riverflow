"""자체 조건 검색 엔진.

KIS API는 HTS 조건검색을 직접 지원하지 않으므로
전 종목을 스캔하여 사용자 정의 조건에 맞는 종목을 필터링한다.

추가 기능:
- 섹터 강세 분석 및 대장주 포착
- 단기 과열 경고 (이격도, 급등, 회전율)
"""

import json
import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .broker.base import BaseBroker

logger = logging.getLogger(__name__)

# KIS 업종 코드 매핑
MARKET_SECTOR_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
}

# KIS 세부 업종 코드 (주요 섹터)
SECTOR_CODES = {
    "반도체": "0028",
    "IT": "0027",
    "자동차": "0015",
    "화학": "0010",
    "철강": "0012",
    "바이오": "0033",
    "금융": "0019",
    "건설": "0014",
    "유통": "0017",
    "미디어": "0030",
    "2차전지": "0035",
    "조선": "0013",
    "방산": "0016",
    "음식료": "0008",
}


class ConditionEngine:
    """자체 조건 검색 엔진"""

    def __init__(self, broker: BaseBroker, db: AsyncSession):
        self.broker = broker
        self.db = db

    # ================================================================
    # 기본 스캔
    # ================================================================

    async def scan(self, condition: dict) -> list[dict]:
        """전 종목 스캔하여 조건에 맞는 종목 반환."""
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
        """KIS 업종별 시세 API를 활용하여 전 종목 시세 조회."""
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
        """KIS 업종별 전종목 시세 조회"""
        tr_id = "FHPST01710000"
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
            trade_amount = int(item.get("acml_tr_pbmn", 0))  # 거래대금
            prev_trade_amount = int(item.get("prdy_tr_pbmn", 1)) or 1
            sector_name = item.get("bstp_kor_isnm", "")
            listed_shares = int(item.get("lstn_stcn", 1)) or 1

            stocks.append({
                "ticker": ticker,
                "name": item.get("hts_kor_isnm", ""),
                "market": market,
                "sector": sector_name,
                "price": current_price,
                "volume": volume,
                "change_rate": change_rate,
                "high": int(item.get("stck_hgpr", 0)),
                "low": int(item.get("stck_lwpr", 0)),
                "open": int(item.get("stck_oprc", 0)),
                "volume_ratio": round(volume / prev_volume, 2) if prev_volume else 0,
                "market_cap": int(item.get("stck_avls", 0)),
                "trade_amount": trade_amount,
                "trade_amount_ratio": round(trade_amount / prev_trade_amount, 2) if prev_trade_amount else 0,
                "turnover_rate": round(volume / listed_shares * 100, 2) if listed_shares else 0,
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

    # ================================================================
    # Task 2: 섹터 강세 분석 및 대장주 포착
    # ================================================================

    async def analyze_sectors(self, markets: list[str] | None = None) -> list[dict]:
        """섹터별 강세도를 분석하여 주도 섹터와 대장주를 반환.

        주도 섹터 조건:
        - 상위 3개 종목 평균 상승률 > 3%
        - 섹터 거래대금 전일비 > 200%
        """
        markets = markets or ["KOSPI", "KOSDAQ"]
        all_stocks = await self._fetch_market_data(markets)

        # 섹터별 종목 그룹핑
        sector_groups: dict[str, list[dict]] = defaultdict(list)
        for stock in all_stocks:
            sector = stock.get("sector", "기타")
            if sector:
                sector_groups[sector].append(stock)

        sector_results = []
        for sector_name, stocks in sector_groups.items():
            if len(stocks) < 3:
                continue

            # 등락률 기준 정렬
            sorted_by_change = sorted(stocks, key=lambda x: x.get("change_rate", 0), reverse=True)

            # 상위 3종목 평균 상승률
            top3 = sorted_by_change[:3]
            top3_avg = sum(s.get("change_rate", 0) for s in top3) / 3

            # 섹터 거래대금 합산 전일비
            total_trade_amount = sum(s.get("trade_amount", 0) for s in stocks)
            total_prev_trade_amount = sum(
                s.get("trade_amount", 0) / max(s.get("trade_amount_ratio", 1), 0.01)
                for s in stocks
            )
            sector_volume_ratio = (
                round(total_trade_amount / total_prev_trade_amount * 100, 2)
                if total_prev_trade_amount > 0 else 0
            )

            # 대장주 = 등락률 1위
            leader = top3[0]

            is_leading = top3_avg > 3.0 and sector_volume_ratio > 200.0

            result = {
                "sector_name": sector_name,
                "sector_code": "",
                "market": stocks[0].get("market", ""),
                "stock_count": len(stocks),
                "top3_avg_change_rate": round(top3_avg, 4),
                "sector_volume_ratio": sector_volume_ratio,
                "is_leading": is_leading,
                "leader_ticker": leader.get("ticker", ""),
                "leader_name": leader.get("name", ""),
                "leader_change_rate": leader.get("change_rate", 0),
                "top_stocks": [
                    {
                        "ticker": s.get("ticker"),
                        "name": s.get("name"),
                        "change_rate": s.get("change_rate"),
                        "volume_ratio": s.get("volume_ratio"),
                        "price": s.get("price"),
                    }
                    for s in top3
                ],
            }
            sector_results.append(result)

        # 주도 섹터 우선, 그 다음 상위 3종목 평균 상승률 내림차순
        sector_results.sort(
            key=lambda x: (x["is_leading"], x["top3_avg_change_rate"]),
            reverse=True,
        )

        # DB 저장
        for r in sector_results[:20]:
            await self.db.execute(
                text(
                    "INSERT INTO sector_analysis "
                    "(sector_code, sector_name, market, top3_avg_change_rate, "
                    "sector_volume_ratio, is_leading, leader_ticker, leader_name, "
                    "leader_change_rate, details) "
                    "VALUES (:code, :name, :market, :avg, :vol, :leading, "
                    ":lt, :ln, :lcr, :details::jsonb)"
                ),
                {
                    "code": r["sector_code"],
                    "name": r["sector_name"],
                    "market": r["market"],
                    "avg": r["top3_avg_change_rate"],
                    "vol": r["sector_volume_ratio"],
                    "leading": r["is_leading"],
                    "lt": r["leader_ticker"],
                    "ln": r["leader_name"],
                    "lcr": r["leader_change_rate"],
                    "details": json.dumps(r["top_stocks"], ensure_ascii=False),
                },
            )
        await self.db.commit()
        logger.info("섹터 분석 완료: %d개 섹터 (주도: %d개)",
                     len(sector_results),
                     sum(1 for r in sector_results if r["is_leading"]))

        return sector_results

    # ================================================================
    # Task 3: 단기 과열 경고
    # ================================================================

    async def check_overheat_alerts(self, markets: list[str] | None = None) -> list[dict]:
        """단기 과열 종목을 감지하여 경고 태그와 함께 반환.

        경고 조건:
        - 이격도 과열: 20일 이동평균 대비 130% 이상 이격
        - 단기 급등: 최근 3일 상승률 합계 > 30% & 회전율 > 200%
        """
        markets = markets or ["KOSPI", "KOSDAQ"]
        all_stocks = await self._fetch_market_data(markets)

        alerts = []
        for stock in all_stocks:
            warnings = []

            # 이격도 계산: 현재가 / 20일 이동평균 * 100
            # 20일 이평을 정확히 알 수 없으므로 KIS 데이터의 근사치 사용
            # (현재가 vs 시가 기준 근사. 정밀 계산은 일봉 API로 별도 조회 필요)
            price = stock.get("price", 0)
            ma20 = await self._get_ma20(stock["ticker"])
            if ma20 and ma20 > 0:
                disparity = round(price / ma20 * 100, 2)
                stock["disparity_20d"] = disparity
                if disparity >= 130:
                    warnings.append(f"이격도과열({disparity}%)")

            # 단기 급등 체크 (change_rate는 당일 등락률)
            # 3일 누적 상승률은 일봉 데이터가 필요하므로
            # 당일 등락률 + 거래량 비율로 근사
            change_rate = stock.get("change_rate", 0)
            turnover = stock.get("turnover_rate", 0)
            volume_ratio = stock.get("volume_ratio", 0)

            # 당일 급등 + 거래 폭발 패턴
            if change_rate > 15 and turnover > 200:
                warnings.append(f"급등과열(등락{change_rate}%,회전율{turnover}%)")
            elif change_rate > 10 and volume_ratio > 5:
                warnings.append(f"거래폭발(등락{change_rate}%,거래량비{volume_ratio}x)")

            if warnings:
                stock["overheat_warnings"] = warnings
                stock["is_overheated"] = True
                alerts.append(stock)

        alerts.sort(key=lambda x: x.get("change_rate", 0), reverse=True)
        logger.info("과열 경고: %d종목 감지", len(alerts))
        return alerts

    async def _get_ma20(self, ticker: str) -> float | None:
        """종목의 20일 이동평균가 조회 (KIS 일봉 API)"""
        try:
            await self.broker._ensure_token()
            tr_id = "FHKST01010400"  # 국내주식기간별시세(일봉)
            headers = self.broker._build_headers(tr_id)

            from datetime import datetime, timedelta, timezone
            end_date = datetime.now(timezone.utc).strftime("%Y%m%d")
            start_date = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y%m%d")

            resp = await self.broker.client.get(
                f"{self.broker.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                headers=headers,
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": ticker,
                    "FID_INPUT_DATE_1": start_date,
                    "FID_INPUT_DATE_2": end_date,
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "0",
                },
            )
            resp.raise_for_status()
            prices = resp.json().get("output2", [])

            closes = [int(p.get("stck_clpr", 0)) for p in prices[:20] if p.get("stck_clpr")]
            if len(closes) >= 20:
                return sum(closes) / 20
        except Exception:
            logger.debug("MA20 조회 실패: %s", ticker)
        return None
