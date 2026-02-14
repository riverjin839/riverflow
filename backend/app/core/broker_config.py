from pydantic_settings import BaseSettings


class BrokerSettings(BaseSettings):
    """증권사 API 설정 - 환경변수에서만 로드"""

    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_ACCOUNT_NO: str = ""
    KIS_HTS_ID: str = ""
    KIS_IS_VIRTUAL: bool = True  # 기본값: 모의투자

    # 키움 브릿지 (확장용)
    KIWOOM_BRIDGE_URL: str = ""
    KIWOOM_BRIDGE_TOKEN: str = ""

    class Config:
        env_file = ".env.local"
        case_sensitive = True

    def mask_secret(self, value: str) -> str:
        """로그 출력 시 시크릿 마스킹"""
        if len(value) <= 8:
            return "****"
        return value[:4] + "*" * (len(value) - 8) + value[-4:]


broker_settings = BrokerSettings()
