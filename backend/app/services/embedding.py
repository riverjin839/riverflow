"""임베딩 서비스 (Ollama bge-m3 / OpenAI).

뉴스, 사용자 문서 등을 벡터로 변환하여 pgvector에 저장한다.
"""

import logging

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """벡터 임베딩 생성"""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.EMBEDDING_MODEL
        self.client = httpx.AsyncClient(timeout=60.0)

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트 임베딩"""
        resp = await self.client.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩 (순차 호출)"""
        results = []
        for text in texts:
            vec = await self.embed(text)
            results.append(vec)
        return results

    async def close(self) -> None:
        await self.client.aclose()
