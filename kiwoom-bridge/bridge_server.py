"""키움 OpenAPI+ 브릿지 서버.

Windows 환경에서 실행되어 키움 OCX를 HTTP REST API로 노출한다.
K8s Pod에서 이 서버로 HTTP 요청을 보내 키움 기능을 사용한다.

요구 사항:
  - Windows OS (32-bit Python)
  - 키움 OpenAPI+ 모듈 설치
  - 키움 HTS 로그인 상태

실행:
  python bridge_server.py
"""

import os

from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel

app = FastAPI(title="Kiwoom Bridge Server")

BRIDGE_TOKEN = os.environ.get("KIWOOM_BRIDGE_TOKEN", "change-me")


def verify_token(authorization: str = Header(...)) -> None:
    """Bearer 토큰 검증"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ", 1)[1]
    if token != BRIDGE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/health")
async def health():
    return {"status": "ok", "broker": "kiwoom"}


@app.get("/api/balance", dependencies=[Depends(verify_token)])
async def get_balance():
    """잔고 조회 (키움 OCX 호출)"""
    # TODO: pykiwoom / koapy 연동
    return {
        "total_asset": 0,
        "cash": 0,
        "stock_value": 0,
        "profit_rate": 0,
        "positions": [],
    }


@app.get("/api/price/{ticker}", dependencies=[Depends(verify_token)])
async def get_price(ticker: str):
    """현재가 조회"""
    # TODO: 키움 OCX 현재가 조회
    return {
        "ticker": ticker,
        "current_price": 0,
        "change_rate": 0,
        "volume": 0,
    }


class OrderRequest(BaseModel):
    ticker: str
    side: str
    quantity: int
    order_type: str = "limit"
    price: float | None = None
    strategy_id: str | None = None


@app.post("/api/order", dependencies=[Depends(verify_token)])
async def place_order(req: OrderRequest):
    """주문 실행"""
    # TODO: 키움 OCX 주문
    return {
        "order_id": "",
        "status": "rejected",
        "message": "키움 OCX 연동 미구현",
    }


@app.post("/api/order/{order_id}/cancel", dependencies=[Depends(verify_token)])
async def cancel_order(order_id: str):
    """주문 취소"""
    # TODO: 키움 OCX 주문 취소
    return {"success": False, "message": "미구현"}


@app.get("/api/orders", dependencies=[Depends(verify_token)])
async def get_orders(date: str | None = None):
    """주문 내역 조회"""
    # TODO: 키움 OCX 주문 내역
    return {"orders": []}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
