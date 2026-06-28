-- AI-OSINT Platform database schema
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id VARCHAR(50),
    investigator_id VARCHAR(50),
    status VARCHAR(20) DEFAULT 'in_progress',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE CASCADE,
    platform VARCHAR(30),
    username VARCHAR(100),
    full_name VARCHAR(200),
    bio TEXT,
    profile_pic_url TEXT,
    profile_pic_hash VARCHAR(64),
    follower_count INTEGER,
    following_count INTEGER,
    post_count INTEGER,
    is_verified BOOLEAN,
    account_created_date DATE,
    location VARCHAR(200),
    external_urls TEXT[],
    raw_data JSONB,
    scraped_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE profile_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE CASCADE,
    source_profile_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    matched_profile_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    confidence_score DECIMAL(5,2),
    matching_factors JSONB,
    ai_analysis TEXT,
    human_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE investigation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE CASCADE UNIQUE,
    platform_data JSONB,
    cross_matches JSONB,
    ai_correlation JSONB,
    risk_assessment JSONB,
    report_url TEXT,
    completed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE scraping_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID REFERENCES investigations(id) ON DELETE SET NULL,
    platform VARCHAR(30),
    endpoint VARCHAR(200),
    request_timestamp TIMESTAMP DEFAULT NOW(),
    response_status INTEGER,
    response_time_ms INTEGER,
    error_message TEXT,
    ip_used VARCHAR(45)
);

CREATE INDEX idx_profiles_username ON profiles(username);
CREATE INDEX idx_profiles_platform ON profiles(platform);
CREATE INDEX idx_investigations_case ON investigations(case_id);
CREATE INDEX idx_investigations_date ON investigations(created_at DESC);
CREATE INDEX idx_profile_matches_investigation ON profile_matches(investigation_id);
CREATE INDEX idx_scraping_logs_investigation ON scraping_logs(investigation_id);
