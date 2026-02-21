"""LLM 클라이언트 (Ollama / OpenAI 호환).

로컬 Ollama를 기본으로 사용하고, 필요 시 OpenAI API로 전환 가능하다.
"""

import json
import logging
import re

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

NEWS_ANALYSIS_SYSTEM = (
    "당신은 한국 증시 전문 애널리스트입니다. "
    "뉴스 기사를 분석하여 반드시 아래 JSON 형식으로만 응답하세요. "
    "다른 텍스트 없이 JSON만 출력하세요.\n"
    '{"impact_score": 1~10, "theme": "테마명", "is_leading": true/false, "reasoning": "한줄 근거"}'
)

NEWS_ANALYSIS_PROMPT = (
    "다음 뉴스를 분석하세요.\n\n"
    "제목: {title}\n"
    "내용: {content}\n\n"
    "평가 기준:\n"
    "- impact_score: 시장 전체에 미치는 영향력 (1=무관, 5=보통, 10=시장판도변경)\n"
    "- theme: 관련 테마/섹터 (예: 반도체, AI, 2차전지, 초전도체, 바이오, 방산 등)\n"
    "- is_leading: 이 뉴스가 시장 주도 테마와 관련있고 지속성이 있는가? "
    "(단발성 이벤트면 false, 산업 구조적 변화면 true)\n\n"
    "JSON으로만 응답하세요."
)


class LLMClient:
    """Ollama REST API 호출 클라이언트"""

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str, system: str = "", num_predict: int = 600) -> str:
        """텍스트 생성"""
        resp = await self.client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"num_predict": num_predict},
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def chat(self, messages: list[dict], num_predict: int = 800) -> str:
        """채팅 형식 생성"""
        resp = await self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": num_predict},
            },
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")

    async def analyze_news(self, title: str, content: str) -> dict:
        """뉴스 기사를 LLM으로 분석하여 영향도/테마/주도성을 반환.

        Returns:
            {"impact_score": int, "theme": str, "is_leading": bool, "reasoning": str}
        """
        prompt = NEWS_ANALYSIS_PROMPT.format(
            title=title,
            content=content[:500],  # 토큰 절약
        )

        try:
            raw = await self.generate(prompt=prompt, system=NEWS_ANALYSIS_SYSTEM)
            parsed = self._extract_json(raw)
            # 값 범위 보정
            score = max(1, min(10, int(parsed.get("impact_score", 1))))
            return {
                "impact_score": score,
                "theme": str(parsed.get("theme", ""))[:100],
                "is_leading": bool(parsed.get("is_leading", False)),
                "reasoning": str(parsed.get("reasoning", ""))[:200],
            }
        except Exception:
            logger.warning("뉴스 LLM 분석 실패: %s", title[:50])
            return {
                "impact_score": 1,
                "theme": "",
                "is_leading": False,
                "reasoning": "분석 실패",
            }

    @staticmethod
    def _extract_json(text: str) -> dict:
        """LLM 응답에서 JSON 부분만 추출"""
        # JSON 블록 추출 시도
        match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)

    async def close(self) -> None:
        await self.client.aclose()
