"""LLM 클라이언트 (Ollama / OpenAI 호환).

로컬 Ollama를 기본으로 사용하고, 필요 시 OpenAI API로 전환 가능하다.
"""

import logging

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Ollama REST API 호출 클라이언트"""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str, system: str = "") -> str:
        """텍스트 생성"""
        resp = await self.client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def chat(self, messages: list[dict]) -> str:
        """채팅 형식 생성"""
        resp = await self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    async def close(self) -> None:
        await self.client.aclose()
