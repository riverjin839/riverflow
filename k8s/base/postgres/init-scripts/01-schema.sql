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

-- 뉴스 크롤링 결과
CREATE TABLE news_articles (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50),
    title VARCHAR(500),
    content TEXT,
    url VARCHAR(500),
    keywords TEXT[],
    embedding vector(768),
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
-- 3. 인덱스
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
