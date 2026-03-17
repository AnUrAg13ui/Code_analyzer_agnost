-- ============================================================
-- AI Code Analyzer Agent — PostgreSQL Schema
-- ============================================================

-- Enable pg_trgm for fuzzy search on descriptions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------
-- pr_reviews  : Persistent findings from every analysed PR
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pr_reviews (
    id            BIGSERIAL PRIMARY KEY,
    repo          TEXT        NOT NULL,
    pr_number     INTEGER     NOT NULL,
    file_path     TEXT        NOT NULL,
    issue_type    TEXT        NOT NULL,          -- bug | rule | history | repeat | docs
    severity      TEXT        NOT NULL,          -- high | medium | low
    description   TEXT        NOT NULL,
    line_start    INTEGER,
    line_end      INTEGER,
    confidence    FLOAT       NOT NULL DEFAULT 0,
    agent_name    TEXT,
    raw_response  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_repo_pr
    ON pr_reviews (repo, pr_number);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_file
    ON pr_reviews (file_path);

CREATE INDEX IF NOT EXISTS idx_pr_reviews_severity
    ON pr_reviews (severity);

-- ------------------------------------------------------------
-- module_risk  : Aggregated risk score per module / file path
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS module_risk (
    id            BIGSERIAL PRIMARY KEY,
    module_name   TEXT        NOT NULL UNIQUE,
    bug_count     INTEGER     NOT NULL DEFAULT 0,
    rule_count    INTEGER     NOT NULL DEFAULT 0,
    risk_score    FLOAT       NOT NULL DEFAULT 0,
    last_issue    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_module_risk_score
    ON module_risk (risk_score DESC);

-- ------------------------------------------------------------
-- coding_rules  : Configurable rule catalogue
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coding_rules (
    id               BIGSERIAL PRIMARY KEY,
    rule_name        TEXT        NOT NULL UNIQUE,
    rule_description TEXT        NOT NULL,
    category         TEXT        NOT NULL DEFAULT 'general',   -- security | style | arch | perf
    severity         TEXT        NOT NULL DEFAULT 'medium',
    enabled          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed some default rules
INSERT INTO coding_rules (rule_name, rule_description, category, severity)
VALUES
    ('no-hardcoded-secrets',   'Credentials and API keys must not be hardcoded in source files.',    'security', 'high'),
    ('no-sql-injection',       'SQL queries must use parameterised statements.',                     'security', 'high'),
    ('no-eval',                'Use of eval() is forbidden in production code.',                     'security', 'high'),
    ('single-responsibility',  'Every function / class should have a single, well-defined purpose.', 'arch',     'medium'),
    ('max-function-length',    'Functions should not exceed 50 logical lines.',                      'style',    'low'),
    ('docstring-required',     'Public functions and classes must have a docstring.',                 'style',    'low'),
    ('no-bare-except',         'Bare except clauses must not be used.',                              'style',    'medium'),
    ('no-mutable-defaults',    'Mutable default arguments are forbidden.',                           'style',    'medium'),
    ('no-global-state',        'Avoid module-level mutable state without synchronisation.',          'arch',     'medium'),
    ('secure-random',          'Use secrets module instead of random for security-sensitive values.','security', 'high')
ON CONFLICT (rule_name) DO NOTHING;

-- ------------------------------------------------------------
-- pr_reports  : Final aggregated report per PR
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pr_reports (
    id              BIGSERIAL PRIMARY KEY,
    repo            TEXT        NOT NULL,
    pr_number       INTEGER     NOT NULL,
    total_findings  INTEGER     NOT NULL DEFAULT 0,
    high_count      INTEGER     NOT NULL DEFAULT 0,
    medium_count    INTEGER     NOT NULL DEFAULT 0,
    low_count       INTEGER     NOT NULL DEFAULT 0,
    avg_confidence  FLOAT       NOT NULL DEFAULT 0,
    report_markdown TEXT,
    github_comment_id BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repo, pr_number)
);

-- ------------------------------------------------------------
-- Helper view: high-risk files across all PRs
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW high_risk_files AS
SELECT
    file_path,
    COUNT(*)          AS total_issues,
    SUM(CASE WHEN severity = 'high'   THEN 1 ELSE 0 END) AS high_issues,
    SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) AS medium_issues,
    MAX(created_at)   AS last_seen
FROM pr_reviews
GROUP BY file_path
ORDER BY high_issues DESC, total_issues DESC;
