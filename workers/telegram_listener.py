"""텔레그램 뉴스 채널 실시간 수집 워커.

Telethon 유저 봇으로 지정된 채널의 새 메시지를 수신하여
news_articles 테이블에 직접 저장한다.

K8s Deployment로 상시 실행된다.

환경 변수:
    TELEGRAM_API_ID    : telegram.org > My Applications 에서 발급
    TELEGRAM_API_HASH  : 위와 동일
    TELEGRAM_SESSION_STRING : StringSession 문자열
                              (최초 인증 후 telethon.sessions.StringSession().save()로 추출)
    TG_CHANNEL_IDS     : 구독할 채널 ID 또는 username (쉼표 구분)
                         예: "-1001234567890,some_channel_username"
    DATABASE_URL       : PostgreSQL 연결 문자열
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

API_ID = int(os.environ.get("TELEGRAM_API_ID", "0"))
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")

_raw_channels = os.environ.get("TG_CHANNEL_IDS", "")
CHANNEL_IDS: list[int | str] = []
for _ch in _raw_channels.split(","):
    _ch = _ch.strip()
    if not _ch:
        continue
    try:
        CHANNEL_IDS.append(int(_ch))
    except ValueError:
        CHANNEL_IDS.append(_ch)  # username 형식

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://trading:trading@localhost:5432/trading",
)

# ---------------------------------------------------------------------------
# DB 세션 팩토리
# ---------------------------------------------------------------------------

_engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
_async_session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def _save_article(title: str, content: str, url: str, source: str) -> None:
    """뉴스 아티클 하나를 DB에 저장. 중복 URL은 무시."""
    async with _async_session() as db:
        if url:
            row = await db.execute(
                sql_text("SELECT id FROM news_articles WHERE url = :url"),
                {"url": url},
            )
            if row.fetchone():
                logger.debug("중복 스킵: %s", url)
                return

        await db.execute(
            sql_text(
                "INSERT INTO news_articles (source, title, content, url, keywords, crawled_at) "
                "VALUES (:source, :title, :content, :url, :keywords, :crawled_at)"
            ),
            {
                "source": source,
                "title": title[:500],
                "content": content,
                "url": url,
                "keywords": [],
                "crawled_at": datetime.now(timezone.utc),
            },
        )
        await db.commit()
        logger.info("[저장] %s | %s", source, title[:60])


# ---------------------------------------------------------------------------
# Telethon 클라이언트
# ---------------------------------------------------------------------------

def _build_client() -> TelegramClient:
    if not API_ID or not API_HASH:
        raise RuntimeError("TELEGRAM_API_ID / TELEGRAM_API_HASH 환경 변수 필요")
    if not SESSION_STRING:
        raise RuntimeError(
            "TELEGRAM_SESSION_STRING 환경 변수 필요.\n"
            "최초 인증: python -c \""
            "from telethon.sync import TelegramClient; from telethon.sessions import StringSession; "
            "c=TelegramClient(StringSession(), API_ID, API_HASH); c.start(); "
            "print(c.session.save())\""
        )
    return TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


async def run() -> None:
    """메인 이벤트 루프."""
    if not CHANNEL_IDS:
        logger.warning("TG_CHANNEL_IDS 미설정 — 구독할 채널 없음. 종료.")
        return

    client = _build_client()
    await client.start()

    me = await client.get_me()
    logger.info("텔레그램 유저 봇 시작: %s (id=%s)", me.username or me.first_name, me.id)
    logger.info("구독 채널: %s", CHANNEL_IDS)

    @client.on(events.NewMessage(chats=CHANNEL_IDS))
    async def _handler(event: events.NewMessage.Event) -> None:
        msg = event.message
        if not msg or not msg.text:
            return

        # 채널 정보
        chat = await event.get_chat()
        channel_title: str = getattr(chat, "title", "") or getattr(chat, "username", "") or str(chat.id)
        channel_id: int = chat.id

        # 메시지 링크 (공개 채널이면 t.me 링크, 비공개면 내부 ID 형식)
        username: str = getattr(chat, "username", "") or ""
        if username:
            msg_url = f"https://t.me/{username}/{msg.id}"
        else:
            msg_url = f"tg://channel?id={channel_id}&msg_id={msg.id}"

        # 제목: 첫 줄 또는 최대 100자
        lines = msg.text.strip().splitlines()
        title = lines[0][:100] if lines else msg.text[:100]
        content = msg.text

        source = f"telegram_{channel_id}"

        try:
            await _save_article(
                title=title,
                content=content,
                url=msg_url,
                source=source,
            )
        except Exception:
            logger.exception("DB 저장 실패: channel=%s msg_id=%s", channel_title, msg.id)

    logger.info("이벤트 대기 중 — Ctrl+C로 종료")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(run())
