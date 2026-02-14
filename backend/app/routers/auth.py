"""인증 라우터 - 스텔스 로그인."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..core.config import settings
from ..core.security import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str
    key_sequence: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def stealth_login(req: LoginRequest):
    """스텔스 로그인: 비밀번호 또는 키 시퀀스로 인증"""
    authenticated = False

    if req.password == settings.STEALTH_PASSWORD:
        authenticated = True
    elif req.key_sequence and req.key_sequence == settings.STEALTH_KEY_SEQUENCE:
        authenticated = True

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 실패",
        )

    token = create_access_token({"sub": "trader", "role": "admin"})
    return TokenResponse(access_token=token)
