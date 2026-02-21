"""키움 OpenAPI+ 브릿지 서버.

Windows 환경에서 실행되어 키움 OCX를 HTTP REST API로 노출한다.
K8s Pod에서 이 서버로 HTTP 요청을 보내 키움 기능을 사용한다.

구조:
  - 메인 스레드: PyQt5 QApplication (키움 OCX COM 이벤트 처리에 필수)
  - 백그라운드 스레드: uvicorn FastAPI HTTP 서버
  - 뉴스 포스팅 스레드: news_queue → POST /api/news/ingest

요구 사항:
  - Windows OS (32-bit Python)
  - 키움 OpenAPI+ 모듈 설치
  - 키움 HTS 로그인 상태

환경 변수:
  - KIWOOM_BRIDGE_TOKEN: 브릿지 서버 인증 토큰
  - BACKEND_URL: 백엔드 베이스 URL (예: http://backend:8000)
  - INTERNAL_API_KEY: 백엔드 /api/news/ingest 인증 키

실행:
  python bridge_server.py
"""

import logging
import os
import queue
import threading

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="Kiwoom Bridge Server")

BRIDGE_TOKEN = os.environ.get("KIWOOM_BRIDGE_TOKEN", "change-me")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "change-me-internal")

# 뉴스 이벤트 버퍼 (Kiwoom Qt 스레드 → 포스팅 스레드)
news_queue: queue.Queue[dict] = queue.Queue(maxsize=500)


# ---------------------------------------------------------------------------
# 키움 실시간 뉴스 관리자
# ---------------------------------------------------------------------------

class KiwoomNewsManager:
    """pykiwoom을 사용한 실시간 뉴스 구독 관리자.

    PyQt5 QApplication이 이미 실행 중인 스레드에서 초기화해야 한다.
    """

    # 키움 실시간 뉴스 화면 번호 (임의값, 다른 화면과 중복 금지)
    SCREEN_NEWS = "9901"
    # 실시간 타입명 (키움 API 명세)
    REAL_TYPE_NEWS = "주식 뉴스 타이틀"
    # 실시간 FID: 20022=뉴스제목, 20023=날짜시간, 20026=뉴스코드
    NEWS_FIDS = "20022;20023;20026"

    def __init__(self) -> None:
        self.kiwoom = None
        self._connected = False

    def connect(self) -> bool:
        """키움 로그인 및 실시간 뉴스 구독."""
        try:
            from pykiwoom.kiwoom import Kiwoom  # Windows 전용

            self.kiwoom = Kiwoom()
            self.kiwoom.CommConnect(block=True)

            # 실시간 뉴스 이벤트 핸들러 연결
            self.kiwoom.OnReceiveRealData.connect(self._on_real_data)

            # 실시간 등록: 빈 종목코드로 전체 뉴스 수신
            self.kiwoom.SetRealReg(self.SCREEN_NEWS, "", self.NEWS_FIDS, "0")

            self._connected = True
            logger.info("키움 연결 및 실시간 뉴스 구독 성공")
            return True
        except Exception:
            logger.exception("키움 연결 실패 — 뉴스 구독 비활성화")
            return False

    def _on_real_data(self, s_code: str, s_real_type: str, s_real_data: str) -> None:
        """키움 실시간 데이터 수신 콜백 (Qt 스레드에서 호출됨)."""
        if s_real_type != self.REAL_TYPE_NEWS:
            return

        title: str = self.kiwoom.GetCommRealData(s_real_type, 20022).strip()
        date_str: str = self.kiwoom.GetCommRealData(s_real_type, 20023).strip()
        news_code: str = self.kiwoom.GetCommRealData(s_real_type, 20026).strip()

        if "특징주" not in title:
            return

        logger.info("[특징주 뉴스] %s | %s | %s", date_str, news_code, title)

        payload = {
            "source": "kiwoom_realtime",
            "title": title,
            "content": "",
            "url": f"kiwoom://news/{news_code}" if news_code else "",
            "keywords": ["특징주"],
        }
        try:
            news_queue.put_nowait(payload)
        except queue.Full:
            logger.warning("뉴스 큐 포화 — 드롭: %s", title[:50])


# ---------------------------------------------------------------------------
# 뉴스 포스팅 스레드: queue → POST /api/news/ingest
# ---------------------------------------------------------------------------

def _news_poster_loop() -> None:
    """백그라운드 스레드: news_queue를 소비하여 백엔드에 전송."""
    client = httpx.Client(timeout=10.0)
    url = f"{BACKEND_URL}/api/news/ingest"
    headers = {"X-API-Key": INTERNAL_API_KEY}

    while True:
        try:
            payload = news_queue.get(timeout=5)
        except queue.Empty:
            continue

        try:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code not in (201, 409):  # 409=중복, 정상
                logger.warning("뉴스 ingest 실패: %s %s", resp.status_code, resp.text[:100])
        except Exception:
            logger.exception("뉴스 POST 오류 — payload: %s", payload.get("title", "")[:50])
        finally:
            news_queue.task_done()


# ---------------------------------------------------------------------------
# FastAPI 엔드포인트
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 진입점: PyQt5 메인 루프 + uvicorn 서브 스레드
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 포스팅 데몬 스레드 시작
    poster = threading.Thread(target=_news_poster_loop, daemon=True, name="news-poster")
    poster.start()

    # uvicorn을 별도 스레드에서 실행 (PyQt5 메인 루프와 공존)
    def _run_uvicorn() -> None:
        uvicorn.run(app, host="0.0.0.0", port=5000, log_level="info")

    server_thread = threading.Thread(target=_run_uvicorn, daemon=True, name="uvicorn")
    server_thread.start()

    # PyQt5 QApplication은 반드시 메인 스레드에서 실행 (Kiwoom OCX COM 요구사항)
    try:
        from PyQt5.QtWidgets import QApplication
        import sys

        qt_app = QApplication(sys.argv)

        # 키움 연결 (QApplication 생성 후에 초기화)
        kiwoom_mgr = KiwoomNewsManager()
        kiwoom_mgr.connect()

        qt_app.exec_()
    except ImportError:
        # Windows 외 환경(테스트용): PyQt5 없이 uvicorn만 실행
        logger.warning("PyQt5 없음 — Kiwoom 기능 비활성화, HTTP 서버만 실행")
        server_thread.join()
