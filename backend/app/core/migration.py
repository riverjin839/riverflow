"""앱 시작 시 DB 스키마 마이그레이션 - 누락 테이블/컬럼 자동 생성."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MIGRATION_SQL = [
    # ── 누락 테이블 생성 ──

    # chat_messages
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        session_id VARCHAR(50) NOT NULL,
        role VARCHAR(10) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at)",

    # sector_analysis
    """
    CREATE TABLE IF NOT EXISTS sector_analysis (
        id SERIAL PRIMARY KEY,
        sector_code VARCHAR(10) NOT NULL,
        sector_name VARCHAR(50) NOT NULL,
        market VARCHAR(10) NOT NULL,
        top3_avg_change_rate DECIMAL(8,4),
        sector_volume_ratio DECIMAL(8,2),
        is_leading BOOLEAN DEFAULT false,
        leader_ticker VARCHAR(10),
        leader_name VARCHAR(50),
        leader_change_rate DECIMAL(8,4),
        details JSONB,
        analyzed_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sector_analyzed ON sector_analysis(analyzed_at)",
    "CREATE INDEX IF NOT EXISTS idx_sector_leading ON sector_analysis(is_leading) WHERE is_leading = true",

    # supply_snapshots
    """
    CREATE TABLE IF NOT EXISTS supply_snapshots (
        id SERIAL PRIMARY KEY,
        snapshot_time TIMESTAMPTZ NOT NULL,
        market VARCHAR(10) NOT NULL,
        index_value DECIMAL(12,2),
        index_change_rate DECIMAL(8,4),
        foreign_net_buy BIGINT DEFAULT 0,
        institution_net_buy BIGINT DEFAULT 0,
        individual_net_buy BIGINT DEFAULT 0,
        foreign_trend VARCHAR(10),
        institution_trend VARCHAR(10),
        details JSONB
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_supply_time ON supply_snapshots(snapshot_time)",
    "CREATE INDEX IF NOT EXISTS idx_supply_market ON supply_snapshots(market, snapshot_time)",

    # user_documents
    """
    CREATE TABLE IF NOT EXISTS user_documents (
        id SERIAL PRIMARY KEY,
        doc_type VARCHAR(20),
        title VARCHAR(200),
        content TEXT,
        embedding vector(768),
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,

    # broker_settings (암호화된 API 키 저장)
    """
    CREATE TABLE IF NOT EXISTS broker_settings (
        id SERIAL PRIMARY KEY,
        key VARCHAR(50) UNIQUE NOT NULL,
        value TEXT NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,

    # ── trade_journal 컬럼 추가 ──
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'trade_journal' AND column_name = 'ai_verdict'
        ) THEN
            ALTER TABLE trade_journal ADD COLUMN ai_verdict VARCHAR(20);
        END IF;
    END$$
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'trade_journal' AND column_name = 'ai_score'
        ) THEN
            ALTER TABLE trade_journal ADD COLUMN ai_score SMALLINT;
        END IF;
    END$$
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'trade_journal' AND column_name = 'ai_evaluation'
        ) THEN
            ALTER TABLE trade_journal ADD COLUMN ai_evaluation JSONB;
        END IF;
    END$$
    """,
]


async def run_migrations(session: AsyncSession) -> None:
    """누락된 테이블/컬럼을 자동으로 생성."""
    for sql in MIGRATION_SQL:
        try:
            await session.execute(text(sql))
        except Exception as e:
            logger.warning("마이그레이션 SQL 실행 실패 (무시): %s", e)
    await session.commit()
    logger.info("DB 마이그레이션 완료")
