"""텔레그램 알림 서비스.

모든 자동매매 주문, 손절/익절, 오류 발생 시 즉시 알림을 보낸다.
"""

import logging

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class Notifier:
    """텔레그램 봇 알림 발송"""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.client = httpx.AsyncClient(timeout=10.0)

    @property
    def _enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    async def send(self, message: str) -> bool:
        """일반 알림 전송"""
        if not self._enabled:
            logger.debug("텔레그램 알림 미설정, 메시지 스킵: %s", message[:50])
            return False

        try:
            resp = await self.client.post(
                f"{TELEGRAM_API}/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
            resp.raise_for_status()
            return True
        except Exception:
            logger.exception("텔레그램 알림 전송 실패")
            return False

    async def alert(self, message: str) -> bool:
        """긴급 알림 (prefix 추가)"""
        return await self.send(f"[ALERT] {message}")

    async def close(self) -> None:
        await self.client.aclose()
