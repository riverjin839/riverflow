import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

import httpx

from ...core.broker_config import BrokerSettings
from .base import (
    AccountBalance,
    BaseBroker,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
    Position,
)

logger = logging.getLogger(__name__)


class KISBroker(BaseBroker):
    """한국투자증권 KIS API 구현체"""

    BASE_URL = "https://openapi.koreainvestment.com:9443"
    VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"

    def __init__(self, settings: BrokerSettings):
        self.settings = settings
        self.base_url = self.VIRTUAL_URL if settings.KIS_IS_VIRTUAL else self.BASE_URL
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.client = httpx.AsyncClient(timeout=30.0)

    async def connect(self) -> bool:
        """OAuth 토큰 발급"""
        resp = await self.client.post(
            f"{self.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.settings.KIS_APP_KEY,
                "appsecret": self.settings.KIS_APP_SECRET,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        logger.info(
            "KIS API 토큰 발급 완료 (모의투자: %s)", self.settings.KIS_IS_VIRTUAL
        )
        return True

    async def _ensure_token(self) -> None:
        """토큰이 없거나 만료 시 재발급"""
        if self.access_token is None:
            await self.connect()

    def _build_headers(self, tr_id: str) -> dict:
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.settings.KIS_APP_KEY,
            "appsecret": self.settings.KIS_APP_SECRET,
            "tr_id": tr_id,
        }

    def _account_parts(self) -> tuple[str, str]:
        """계좌번호를 CANO, ACNT_PRDT_CD로 분리"""
        parts = self.settings.KIS_ACCOUNT_NO.split("-")
        return parts[0], parts[1] if len(parts) > 1 else "01"

    async def get_balance(self) -> AccountBalance:
        """잔고 조회"""
        await self._ensure_token()
        tr_id = "VTTC8434R" if self.settings.KIS_IS_VIRTUAL else "TTTC8434R"
        cano, acnt_prdt_cd = self._account_parts()

        resp = await self.client.get(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._build_headers(tr_id),
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        positions = []
        for item in data.get("output1", []):
            if int(item.get("hldg_qty", 0)) > 0:
                positions.append(
                    Position(
                        ticker=item["pdno"],
                        ticker_name=item.get("prdt_name", ""),
                        quantity=int(item["hldg_qty"]),
                        avg_price=Decimal(item.get("pchs_avg_pric", "0")),
                        current_price=Decimal(item.get("prpr", "0")),
                        profit_rate=Decimal(item.get("evlu_pfls_rt", "0")),
                        profit_amount=Decimal(item.get("evlu_pfls_amt", "0")),
                    )
                )

        summary = data.get("output2", [{}])
        if isinstance(summary, list) and summary:
            summary = summary[0]

        return AccountBalance(
            total_asset=Decimal(summary.get("tot_evlu_amt", "0")),
            cash=Decimal(summary.get("dnca_tot_amt", "0")),
            stock_value=Decimal(summary.get("scts_evlu_amt", "0")),
            profit_rate=Decimal(summary.get("evlu_pfls_smtl_rt", "0")),
            positions=positions,
        )

    async def get_current_price(self, ticker: str) -> dict:
        """현재가 조회"""
        await self._ensure_token()
        tr_id = "FHKST01010100"

        resp = await self.client.get(
            f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._build_headers(tr_id),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
        resp.raise_for_status()
        data = resp.json()
        output = data.get("output", {})

        return {
            "ticker": ticker,
            "current_price": int(output.get("stck_prpr", 0)),
            "change_rate": float(output.get("prdy_ctrt", 0)),
            "volume": int(output.get("acml_vol", 0)),
            "high": int(output.get("stck_hgpr", 0)),
            "low": int(output.get("stck_lwpr", 0)),
            "open": int(output.get("stck_oprc", 0)),
        }

    async def place_order(self, order: OrderRequest) -> OrderResult:
        """주문 실행"""
        await self._ensure_token()

        if order.side == OrderSide.BUY:
            tr_id = "VTTC0802U" if self.settings.KIS_IS_VIRTUAL else "TTTC0802U"
        else:
            tr_id = "VTTC0801U" if self.settings.KIS_IS_VIRTUAL else "TTTC0801U"

        cano, acnt_prdt_cd = self._account_parts()

        # 시장가: ORD_DVSN=01(지정가), 06(시장가)
        ord_dvsn = "01" if order.order_type == OrderType.LIMIT else "06"

        body = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "PDNO": order.ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": str(order.price) if order.price else "0",
        }

        resp = await self.client.post(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._build_headers(tr_id),
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        output = data.get("output", {})

        status = "submitted" if data.get("rt_cd") == "0" else "rejected"
        logger.info(
            "KIS 주문 %s: %s %s %d주 @ %s",
            status,
            order.side.value,
            order.ticker,
            order.quantity,
            order.price,
        )

        return OrderResult(
            order_id=output.get("ODNO", ""),
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            price=order.price or Decimal("0"),
            status=status,
            broker="kis",
            message=data.get("msg1", ""),
        )

    async def cancel_order(self, order_id: str) -> bool:
        """주문 취소"""
        await self._ensure_token()
        tr_id = "VTTC0803U" if self.settings.KIS_IS_VIRTUAL else "TTTC0803U"
        cano, acnt_prdt_cd = self._account_parts()

        resp = await self.client.post(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl",
            headers=self._build_headers(tr_id),
            json={
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "KRX_FWDG_ORD_ORGNO": "",
                "ORGN_ODNO": order_id,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",  # 취소
                "ORD_QTY": "0",  # 전량
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("rt_cd") == "0"

    async def get_order_history(self, date: Optional[str] = None) -> list[dict]:
        """주문 내역 조회"""
        await self._ensure_token()
        tr_id = "VTTC8001R" if self.settings.KIS_IS_VIRTUAL else "TTTC8001R"
        cano, acnt_prdt_cd = self._account_parts()

        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")

        resp = await self.client.get(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            headers=self._build_headers(tr_id),
            params={
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "INQR_STRT_DT": date,
                "INQR_END_DT": date,
                "SLL_BUY_DVSN_CD": "00",
                "INQR_DVSN": "00",
                "PDNO": "",
                "CCLD_DVSN": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "INQR_DVSN_3": "00",
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("output1", [])

    async def subscribe_realtime(self, tickers: list[str], callback: Callable) -> None:
        """실시간 시세 구독은 별도 realtime_feed 워커에서 처리"""
        raise NotImplementedError(
            "실시간 시세는 realtime_feed 워커를 통해 구독합니다."
        )

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        await self.client.aclose()
