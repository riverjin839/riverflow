-- =============================================================
-- Trading System Database Schema
-- PostgreSQL + pgvector
-- =============================================================

-- pgvector extension 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================
-- 1. 기본 테이블 (Base Architecture)
-- =============================================================

-- 매매일지
CREATE TABLE trade_journal (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    ticker_name VARCHAR(50),
    buy_price DECIMAL(12,2),
    sell_price DECIMAL(12,2),
    quantity INTEGER,
    profit_rate DECIMAL(6,2),
    buy_reason TEXT,
    ai_feedback TEXT,
    ai_verdict VARCHAR(20),              -- 원칙준수 / 원칙위반 / 판단보류
    ai_score SMALLINT,                   -- 종합 점수 (1~10)
    ai_evaluation JSONB,                 -- 항목별 상세 평가
    chart_image_path VARCHAR(255),
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 시황 브리핑
CREATE TABLE market_briefing (
    id SERIAL PRIMARY KEY,
    briefing_type VARCHAR(20) NOT NULL,
    raw_data JSONB,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 뉴스 크롤링 결과 (+ LLM 재료 분석)
CREATE TABLE news_articles (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),
    title VARCHAR(500),
    content TEXT,
    url VARCHAR(500),
    keywords TEXT[],
    embedding vector(768),
    impact_score SMALLINT DEFAULT 0,       -- 시장 영향력 (1~10)
    theme VARCHAR(100),                     -- 관련 테마/섹터
    is_leading BOOLEAN DEFAULT false,       -- 시장 주도 뉴스 여부
    crawled_at TIMESTAMPTZ DEFAULT NOW()
);

-- 사용자 투자 원칙/인사이트 (RAG 소스)
CREATE TABLE user_documents (
    id SERIAL PRIMARY KEY,
    doc_type VARCHAR(20),
    title VARCHAR(200),
    content TEXT,
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 2. 증권사 연동 / 조건 검색 / 자동매매 테이블
-- =============================================================

-- 조건식 저장
CREATE TABLE search_conditions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    conditions JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    auto_trade BOOLEAN DEFAULT false,
    auto_trade_config JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 조건 검색 결과
CREATE TABLE search_results (
    id SERIAL PRIMARY KEY,
    condition_id INTEGER REFERENCES search_conditions(id) ON DELETE CASCADE,
    ticker VARCHAR(10),
    ticker_name VARCHAR(50),
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    price_at_match DECIMAL(12,2),
    volume_at_match BIGINT,
    match_details JSONB,
    saved BOOLEAN DEFAULT false,
    traded BOOLEAN DEFAULT false
);

-- 자동매매 주문 기록
CREATE TABLE auto_trade_orders (
    id SERIAL PRIMARY KEY,
    condition_id INTEGER REFERENCES search_conditions(id) ON DELETE SET NULL,
    result_id INTEGER REFERENCES search_results(id) ON DELETE SET NULL,
    order_id VARCHAR(50),
    ticker VARCHAR(10) NOT NULL,
    side VARCHAR(4) NOT NULL,
    quantity INTEGER NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitted',
    broker VARCHAR(20) NOT NULL DEFAULT 'kis',
    strategy_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 3. 전문가 트레이딩 로직 테이블
-- =============================================================

-- 섹터 분석 결과 (주기적 스냅샷)
CREATE TABLE sector_analysis (
    id SERIAL PRIMARY KEY,
    sector_code VARCHAR(10) NOT NULL,
    sector_name VARCHAR(50) NOT NULL,
    market VARCHAR(10) NOT NULL,            -- KOSPI / KOSDAQ
    top3_avg_change_rate DECIMAL(8,4),      -- 상위 3종목 평균 상승률
    sector_volume_ratio DECIMAL(8,2),       -- 섹터 거래대금 전일비(%)
    is_leading BOOLEAN DEFAULT false,       -- 주도 섹터 여부
    leader_ticker VARCHAR(10),              -- 대장주 종목코드
    leader_name VARCHAR(50),                -- 대장주 이름
    leader_change_rate DECIMAL(8,4),        -- 대장주 등락률
    details JSONB,                          -- 상위 종목 상세 정보
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 투자자별 수급 스냅샷 (1분 단위)
CREATE TABLE supply_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_time TIMESTAMPTZ NOT NULL,
    market VARCHAR(10) NOT NULL,            -- KOSPI / KOSDAQ
    index_value DECIMAL(12,2),              -- 지수
    index_change_rate DECIMAL(8,4),         -- 지수 등락률
    foreign_net_buy BIGINT DEFAULT 0,       -- 외인 순매수(백만원)
    institution_net_buy BIGINT DEFAULT 0,   -- 기관 순매수(백만원)
    individual_net_buy BIGINT DEFAULT 0,    -- 개인 순매수(백만원)
    foreign_trend VARCHAR(10),              -- 외인 추세: rising/falling/flat
    institution_trend VARCHAR(10),          -- 기관 추세
    details JSONB
);

-- AI 챗 대화 히스토리
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL,
    role VARCHAR(10) NOT NULL,          -- user / assistant
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 브로커 API 키 (암호화 저장)
CREATE TABLE broker_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(50) UNIQUE NOT NULL,
    value TEXT NOT NULL,                   -- Fernet(AES-256) 암호화된 값
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================
-- 4. 인덱스
-- =============================================================

-- pgvector HNSW 인덱스 (코사인 유사도 검색)
CREATE INDEX idx_news_embedding ON news_articles
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_docs_embedding ON user_documents
    USING hnsw (embedding vector_cosine_ops);

-- 일반 인덱스
CREATE INDEX idx_journal_trade_date ON trade_journal(trade_date);
CREATE INDEX idx_journal_ticker ON trade_journal(ticker);
CREATE INDEX idx_briefing_type ON market_briefing(briefing_type);
CREATE INDEX idx_briefing_created ON market_briefing(created_at);
CREATE INDEX idx_news_crawled ON news_articles(crawled_at);
CREATE INDEX idx_news_source ON news_articles(source);
CREATE INDEX idx_search_conditions_active ON search_conditions(is_active);
CREATE INDEX idx_search_results_condition ON search_results(condition_id);
CREATE INDEX idx_search_results_matched ON search_results(matched_at);
CREATE INDEX idx_auto_orders_ticker ON auto_trade_orders(ticker);
CREATE INDEX idx_auto_orders_created ON auto_trade_orders(created_at);
CREATE INDEX idx_auto_orders_status ON auto_trade_orders(status);
CREATE INDEX idx_news_impact ON news_articles(impact_score) WHERE impact_score >= 8;
CREATE INDEX idx_news_theme ON news_articles(theme) WHERE theme IS NOT NULL;
CREATE INDEX idx_sector_analyzed ON sector_analysis(analyzed_at);
CREATE INDEX idx_sector_leading ON sector_analysis(is_leading) WHERE is_leading = true;
CREATE INDEX idx_supply_time ON supply_snapshots(snapshot_time);
CREATE INDEX idx_supply_market ON supply_snapshots(market, snapshot_time);
CREATE INDEX idx_chat_session ON chat_messages(session_id, created_at);
