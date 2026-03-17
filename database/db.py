"""
Async PostgreSQL connection pool using asyncpg.
Provides helper methods for common query patterns.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level pool singleton
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Lazy-initialize and return the connection pool."""
    global _pool
    if not settings.USE_DATABASE:
        raise RuntimeError("PostgreSQL is disabled (USE_DATABASE=False)")
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=2,
                max_size=settings.DB_POOL_SIZE,
                command_timeout=60,
            )
            logger.info("PostgreSQL connection pool created.")
        except Exception as exc:
            # Mask potential sensitive info in URL
            sanitized_url = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL
            logger.error("Failed to create PostgreSQL pool for %s: %s", sanitized_url, exc)
            raise
    return _pool


async def close_pool() -> None:
    """Gracefully close the connection pool on shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")


@asynccontextmanager
async def get_connection():
    """Async context manager that yields a single pooled connection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


# ──────────────────────────────────────────────────────────────
# CRUD helpers
# ──────────────────────────────────────────────────────────────

async def insert_finding(finding: Dict[str, Any]) -> int:
    """Persist a single agent finding. Returns the new row id."""
    if not settings.USE_DATABASE:
        return 0
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pr_reviews
                (repo, pr_number, file_path, issue_type, severity,
                 description, line_start, line_end, confidence, agent_name, raw_response)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            RETURNING id
            """,
            finding["repo"],
            finding["pr_number"],
            finding["file_path"],
            finding["issue_type"],
            finding["severity"],
            finding["description"],
            finding.get("line_start"),
            finding.get("line_end"),
            finding.get("confidence", 0.0),
            finding.get("agent_name"),
            finding.get("raw_response"),   # Pass as string; asyncpg handles JSONB
        )
        return row["id"]


async def bulk_insert_findings(findings: List[Dict[str, Any]]) -> None:
    """Batch-insert multiple findings in a single transaction."""
    if not settings.USE_DATABASE or not findings:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                """
                INSERT INTO pr_reviews
                    (repo, pr_number, file_path, issue_type, severity,
                     description, line_start, line_end, confidence, agent_name, raw_response)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                """,
                [
                    (
                        f["repo"], f["pr_number"], f["file_path"],
                        f["issue_type"], f["severity"], f["description"],
                        f.get("line_start"), f.get("line_end"),
                        f.get("confidence", 0.0), f.get("agent_name"),
                        f.get("raw_response"),
                    )
                    for f in findings
                ],
            )


async def get_recent_findings(repo: str, file_path: str, limit: int = 20) -> List[Dict]:
    """Fetch recent findings for the same repo+file for memory context."""
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT issue_type, severity, description, created_at
            FROM pr_reviews
            WHERE repo = $1 AND file_path = $2
            ORDER BY created_at DESC
            LIMIT $3
            """,
            repo, file_path, limit,
        )
        return [dict(r) for r in rows]


async def get_module_risk(module_name: str) -> Optional[Dict]:
    """Return the risk record for a given module/file path."""
    if not settings.USE_DATABASE:
        return None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM module_risk WHERE module_name = $1",
            module_name,
        )
        return dict(row) if row else None


async def upsert_module_risk(module_name: str, is_bug: bool = False, is_rule: bool = False) -> None:
    """Increment counters and refresh the risk score for a module."""
    if not settings.USE_DATABASE:
        return
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO module_risk (module_name, bug_count, rule_count, risk_score, last_issue, updated_at)
            VALUES ($1, $2::INT, $3::INT, $2::INT + $3::INT * 0.5, NOW(), NOW())
            ON CONFLICT (module_name) DO UPDATE SET
                bug_count  = module_risk.bug_count  + EXCLUDED.bug_count,
                rule_count = module_risk.rule_count + EXCLUDED.rule_count,
                risk_score = (module_risk.bug_count + EXCLUDED.bug_count)
                           + (module_risk.rule_count + EXCLUDED.rule_count) * 0.5,
                last_issue = NOW(),
                updated_at = NOW()
            """,
            module_name,
            1 if is_bug else 0,
            1 if is_rule else 0,
        )


async def get_coding_rules(enabled_only: bool = True) -> List[Dict]:
    """Fetch the full rule catalogue."""
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM coding_rules WHERE ($1 = FALSE OR enabled = TRUE) ORDER BY severity, category",
            enabled_only,
        )
        return [dict(r) for r in rows]


async def upsert_pr_report(report: Dict[str, Any]) -> None:
    """Insert or update the aggregated report record for a PR."""
    if not settings.USE_DATABASE:
        return
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO pr_reports
                (repo, pr_number, total_findings, high_count, medium_count, low_count,
                 avg_confidence, report_markdown, github_comment_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (repo, pr_number) DO UPDATE SET
                total_findings    = EXCLUDED.total_findings,
                high_count        = EXCLUDED.high_count,
                medium_count      = EXCLUDED.medium_count,
                low_count         = EXCLUDED.low_count,
                avg_confidence    = EXCLUDED.avg_confidence,
                report_markdown   = EXCLUDED.report_markdown,
                github_comment_id = EXCLUDED.github_comment_id,
                created_at        = NOW()
            """,
            report["repo"], report["pr_number"],
            report["total_findings"], report["high_count"],
            report["medium_count"], report["low_count"],
            report["avg_confidence"], report.get("report_markdown"),
            report.get("github_comment_id"),
        )


async def get_all_reports(limit: int = 50) -> List[Dict]:
    """Fetch all PR reports for the dashboard summary."""
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pr_reports ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]


async def get_report_detail(repo: str, pr_number: int) -> Optional[Dict]:
    """Fetch a single PR report detailed record."""
    if not settings.USE_DATABASE:
        return None
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM pr_reports WHERE repo = $1 AND pr_number = $2",
            repo, pr_number,
        )
        return dict(row) if row else None


async def get_findings_for_pr(repo: str, pr_number: int) -> List[Dict]:
    """Fetch all individual findings for a specific PR."""
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM pr_reviews WHERE repo = $1 AND pr_number = $2 ORDER BY severity DESC, file_path",
            repo, pr_number,
        )
        return [dict(r) for r in rows]


async def get_top_risk_modules(limit: int = 10) -> List[Dict]:
    """Fetch top modules by risk score."""
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM module_risk ORDER BY risk_score DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]


async def get_overall_stats() -> Dict[str, Any]:
    """Calculate high-level stats for the dashboard info cards."""
    if not settings.USE_DATABASE:
        return {}
    async with get_connection() as conn:
        stats = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM pr_reports) as total_prs,
                (SELECT COUNT(*) FROM pr_reviews) as total_findings,
                (SELECT COUNT(*) FROM module_risk WHERE risk_score > 5) as high_risk_modules
            """
        )
        return dict(stats)


async def get_repeated_issues(repo: str, pr_number: int, limit: int = 10) -> List[Dict]:
    """
    Find issues previously flagged in other PRs of the same repo
    that are similar to what we might see again (used by Past PR agent).
    """
    if not settings.USE_DATABASE:
        return []
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT file_path, issue_type, severity, description, COUNT(*) AS occurrences
            FROM pr_reviews
            WHERE repo = $1 AND pr_number != $2
            GROUP BY file_path, issue_type, severity, description
            HAVING COUNT(*) > 1
            ORDER BY occurrences DESC
            LIMIT $3
            """,
            repo, pr_number, limit,
        )
        return [dict(r) for r in rows]


async def init_db() -> None:
    """Create tables if they don't exist (reads schema.sql)."""
    if not settings.USE_DATABASE:
        logger.info("PostgreSQL is disabled (USE_DATABASE=False). Skipping schema init.")
        return
    import pathlib
    schema_path = pathlib.Path(__file__).parent / "schema.sql"
    ddl = schema_path.read_text(encoding="utf-8")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(ddl)
    logger.info("Database schema initialised.")
