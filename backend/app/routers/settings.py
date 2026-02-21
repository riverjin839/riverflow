"""설정 라우터 - 브로커 API 키 관리 (암호화 저장)."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.encryption import decrypt, encrypt, mask_value
from ..core.security import verify_token

router = APIRouter(prefix="/api/settings", tags=["settings"])
logger = logging.getLogger(__name__)

# 저장 가능한 브로커 설정 키 목록 (화이트리스트)
BROKER_KEYS = ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "KIS_HTS_ID", "KIS_IS_VIRTUAL"]


class BrokerSettingsRequest(BaseModel):
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_ACCOUNT_NO: str = ""
    KIS_HTS_ID: str = ""
    KIS_IS_VIRTUAL: bool = True


class BrokerSettingsResponse(BaseModel):
    KIS_APP_KEY: str = ""
    KIS_APP_SECRET: str = ""
    KIS_ACCOUNT_NO: str = ""
    KIS_HTS_ID: str = ""
    KIS_IS_VIRTUAL: bool = True
    has_keys: bool = False


@router.get("/broker", response_model=BrokerSettingsResponse)
async def get_broker_settings(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """브로커 API 키 조회 (마스킹된 값 반환)."""
    try:
        result = await db.execute(
            text("SELECT key, value FROM broker_settings WHERE key = ANY(:keys)"),
            {"keys": BROKER_KEYS},
        )
        rows = {r.key: r.value for r in result.fetchall()}
    except Exception:
        await db.rollback()
        return BrokerSettingsResponse()

    app_key = decrypt(rows.get("KIS_APP_KEY", ""))
    app_secret = decrypt(rows.get("KIS_APP_SECRET", ""))
    account_no = decrypt(rows.get("KIS_ACCOUNT_NO", ""))
    hts_id = decrypt(rows.get("KIS_HTS_ID", ""))
    is_virtual_raw = rows.get("KIS_IS_VIRTUAL", "")
    is_virtual = decrypt(is_virtual_raw) != "false" if is_virtual_raw else True

    has_keys = bool(app_key and app_secret and account_no)

    return BrokerSettingsResponse(
        KIS_APP_KEY=mask_value(app_key),
        KIS_APP_SECRET=mask_value(app_secret),
        KIS_ACCOUNT_NO=mask_value(account_no),
        KIS_HTS_ID=mask_value(hts_id),
        KIS_IS_VIRTUAL=is_virtual,
        has_keys=has_keys,
    )


@router.put("/broker")
async def save_broker_settings(
    req: BrokerSettingsRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """브로커 API 키 저장 (암호화)."""
    now = datetime.now(timezone.utc)

    values = {
        "KIS_APP_KEY": req.KIS_APP_KEY,
        "KIS_APP_SECRET": req.KIS_APP_SECRET,
        "KIS_ACCOUNT_NO": req.KIS_ACCOUNT_NO,
        "KIS_HTS_ID": req.KIS_HTS_ID,
        "KIS_IS_VIRTUAL": str(req.KIS_IS_VIRTUAL).lower(),
    }

    for key, val in values.items():
        # 마스킹된 값이면 스킵 (변경되지 않은 기존값)
        if "****" in val:
            continue

        encrypted = encrypt(val)
        await db.execute(
            text(
                "INSERT INTO broker_settings (key, value, updated_at) "
                "VALUES (:key, :value, :now) "
                "ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = :now"
            ),
            {"key": key, "value": encrypted, "now": now},
        )

    await db.commit()

    # 브로커 설정 런타임 반영
    _reload_broker_config(values)

    return {"message": "브로커 설정이 저장되었습니다"}


@router.delete("/broker", status_code=204)
async def delete_broker_settings(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(verify_token),
):
    """브로커 API 키 전체 삭제."""
    await db.execute(
        text("DELETE FROM broker_settings WHERE key = ANY(:keys)"),
        {"keys": BROKER_KEYS},
    )
    await db.commit()


def _reload_broker_config(values: dict) -> None:
    """저장된 값을 런타임 broker_settings에 반영."""
    from ..core.broker_config import broker_settings

    for key, val in values.items():
        if "****" in val:
            continue
        if key == "KIS_IS_VIRTUAL":
            broker_settings.KIS_IS_VIRTUAL = val == "true"
        elif hasattr(broker_settings, key):
            setattr(broker_settings, key, val)


async def load_broker_settings_from_db(session: AsyncSession) -> None:
    """앱 시작 시 DB에서 브로커 설정 로드 → 런타임 반영."""
    try:
        result = await session.execute(
            text("SELECT key, value FROM broker_settings WHERE key = ANY(:keys)"),
            {"keys": BROKER_KEYS},
        )
        rows = {r.key: r.value for r in result.fetchall()}
    except Exception:
        return

    if not rows:
        return

    from ..core.broker_config import broker_settings

    for key, encrypted_val in rows.items():
        try:
            val = decrypt(encrypted_val)
        except Exception:
            continue

        if key == "KIS_IS_VIRTUAL":
            broker_settings.KIS_IS_VIRTUAL = val != "false"
        elif hasattr(broker_settings, key):
            setattr(broker_settings, key, val)

    logger.info("DB에서 브로커 설정 로드 완료")
