"""
Review poster: generates the final Markdown report and posts it to GitHub.
Also persists all findings to PostgreSQL.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database.db import bulk_insert_findings, upsert_module_risk, upsert_pr_report
from services.git_provider import GitProvider

logger = logging.getLogger(__name__)


class ReviewPoster:
    """
    Builds the final review Markdown document and posts it as a
    GitHub PR comment. Also drives persistence of all findings.
    """

    def __init__(self, provider: GitProvider):
        self.gh = provider

    async def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        head_sha: str,
        findings: List[Dict[str, Any]],
        avg_confidence: float,
    ) -> Optional[int]:
        """
        Full pipeline:
        1. Generate Markdown report
        2. Post to GitHub
        3. Persist to PostgreSQL
        Returns the GitHub comment ID.
        """
        full_repo = f"{owner}/{repo}"
        report_md = self._generate_markdown(pr_number, findings, avg_confidence)

        # Post to GitHub
        comment_id = await self.gh.post_pr_comment(owner, repo, pr_number, report_md)

        # Persist findings
        db_findings = [
            {**f, "repo": full_repo, "pr_number": pr_number}
            for f in findings
        ]
        await bulk_insert_findings(db_findings)

        # Update module risk counters
        for f in findings:
            is_bug = f.get("issue_type") == "bug"
            is_rule = f.get("issue_type") == "rule"
            if is_bug or is_rule:
                await upsert_module_risk(
                    f.get("file_path", "unknown"),
                    is_bug=is_bug,
                    is_rule=is_rule,
                )

        # Persist the aggregated report record
        high = sum(1 for f in findings if f.get("severity") == "high")
        medium = sum(1 for f in findings if f.get("severity") == "medium")
        low = sum(1 for f in findings if f.get("severity") == "low")

        await upsert_pr_report(
            {
                "repo": full_repo,
                "pr_number": pr_number,
                "total_findings": len(findings),
                "high_count": high,
                "medium_count": medium,
                "low_count": low,
                "avg_confidence": avg_confidence,
                "report_markdown": report_md,
                "github_comment_id": comment_id,
            }
        )

        logger.info(
            "Review posted for PR #%d: %d findings (H=%d M=%d L=%d)",
            pr_number, len(findings), high, medium, low,
        )
        return comment_id

    # ──────────────────────────────────────────────────────────────
    # Markdown generation
    # ──────────────────────────────────────────────────────────────

    def _generate_markdown(
        self,
        pr_number: int,
        findings: List[Dict[str, Any]],
        avg_confidence: float,
    ) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        high = [f for f in findings if f.get("severity") == "high"]
        medium = [f for f in findings if f.get("severity") == "medium"]
        low = [f for f in findings if f.get("severity") == "low"]

        lines = [
            "## 🤖 AI Code Review — Automated Analysis",
            "",
            f"> **PR #{pr_number}** | Analysed at {now} | "
            f"Avg confidence: `{avg_confidence:.0%}`",
            "",
            "### Summary",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 High   | {len(high)} |",
            f"| 🟡 Medium | {len(medium)} |",
            f"| 🟢 Low    | {len(low)} |",
            f"| **Total** | **{len(findings)}** |",
            "",
        ]

        def render_findings(group: List[Dict], emoji: str, title: str) -> None:
            if not group:
                return
            lines.append(f"### {emoji} {title} Issues")
            lines.append("")
            for f in group:
                file_info = f"`{f.get('file_path', 'unknown')}`"
                if f.get("line_start"):
                    file_info += f" (L{f.get('line_start')})"
                
                lines.append(f"#### {file_info}")
                
                # Metadata line
                meta = []
                if f.get("category"):
                    meta.append(f"**Category:** `{f['category']}`")
                if f.get("rule_name"):
                    meta.append(f"**Rule:** `{f['rule_name']}`")
                meta.append(f"**Agent:** `{f.get('agent_name', 'unknown')}`")
                meta.append(f"**Confidence:** `{f.get('confidence', 0):.0%}`")
                lines.append(" | ".join(meta))
                lines.append("")

                # Description
                lines.append(f.get("description", ""))
                
                # Impact/Risk details
                impact_lines = []
                if f.get("technical_impact"):
                    impact_lines.append(f"- **Technical Impact:** {f['technical_impact']}")
                if f.get("structural_risk"):
                    impact_lines.append(f"- **Structural Risk:** {f['structural_risk']}")
                if f.get("churn_risk"):
                    impact_lines.append(f"- **Churn Risk:** `{f['churn_risk']}`")
                if f.get("stability_impact"):
                    impact_lines.append(f"- **Stability Impact:** {f['stability_impact']}")
                if f.get("improvement_effort"):
                    impact_lines.append(f"- **Effort to Fix:** `{f['improvement_effort']}`")
                if f.get("readability_impact"):
                    impact_lines.append(f"- **Readability Impact:** `{f['readability_impact']}`")
                
                if impact_lines:
                    lines.append("")
                    lines.extend(impact_lines)

                # Suggested fix
                if f.get("suggested_fix"):
                    lines.append("")
                    lines.append(f"#### 🛠️ Suggested Fix")
                    lines.append(f"{f['suggested_fix']}")
                
                lines.append("")
                lines.append("---")
                lines.append("")

        render_findings(high, "🔴", "High")
        render_findings(medium, "🟡", "Medium")
        render_findings(low, "🟢", "Low")

        if not findings:
            lines.append("✅ **No significant issues detected. Great work!**")
        else:
            lines.append(
                "> _This analysis was generated automatically by the AI Code Analyzer._  \n"
                "> _Findings below the confidence threshold have been filtered out._"
            )

        return "\n".join(lines)
