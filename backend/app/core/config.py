import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 전역 설정"""

    APP_NAME: str = "Trading System"
    DEBUG: bool = False

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://trading:trading@localhost:5432/trading"

    # Ollama (호스트에서 실행, K8s 내부에서 API 호출)
    OLLAMA_BASE_URL: str = "http://host.k3d.internal:11434"
    OLLAMA_MODEL: str = "llama3"
    EMBEDDING_MODEL: str = "bge-m3"

    # OpenAI (대체용)
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24시간

    # 스텔스 로그인
    STEALTH_PASSWORD: str = "change-me"
    STEALTH_KEY_SEQUENCE: str = "up,up,down,down,left,right,left,right"

    # 텔레그램 알림
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    class Config:
        env_file = ".env.local"
        case_sensitive = True


settings = Settings()
