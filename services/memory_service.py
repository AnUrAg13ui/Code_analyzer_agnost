"""
Memory service: retrieves historical PostgreSQL insights to enrich analysis context.
Provides recent findings, module risk data, and repeated issue patterns.
"""

import logging
from typing import Any, Dict, List, Optional

from database.db import (
    get_recent_findings,
    get_module_risk,
    get_repeated_issues,
    get_coding_rules,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Thin service layer over the database module.
    Transforms raw DB rows into prompt-friendly text summaries.
    """

    async def get_memory_context(
        self,
        repo: str,
        pr_number: int,
        file_paths: List[str],
    ) -> Dict[str, Any]:
        """
        Assemble historical memory context for all changed files.
        Returns a dict with keys: file_memories, module_risks, repeated_issues, rules.
        """
        file_memories: Dict[str, List[Dict]] = {}
        module_risks: Dict[str, Optional[Dict]] = {}

        for file_path in file_paths:
            findings = await get_recent_findings(repo, file_path, limit=15)
            file_memories[file_path] = findings

            risk = await get_module_risk(file_path)
            if risk:
                module_risks[file_path] = risk

        repeated = await get_repeated_issues(repo, pr_number, limit=15)
        # rules = await get_coding_rules(enabled_only=True)
        rules = []  # Disable database rules to let model use its own reasoning

        return {
            "file_memories": file_memories,
            "module_risks": module_risks,
            "repeated_issues": repeated,
            "rules": rules,
        }

    # ──────────────────────────────────────────────────────────────
    # Text formatters for embedding in prompts
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def format_file_memory(file_path: str, findings: List[Dict]) -> str:
        if not findings:
            return f"No previous findings for `{file_path}`."
        lines = [f"### Historical issues in `{file_path}`:"]
        for f in findings:
            lines.append(
                f"  - [{f['severity'].upper()}] {f['issue_type']}: {f['description'][:120]}"
                f"  (seen {str(f['created_at'])[:10]})"
            )
        return "\n".join(lines)

    @staticmethod
    def format_module_risk(file_path: str, risk: Dict) -> str:
        return (
            f"### Module risk for `{file_path}`:\n"
            f"  Bug count: {risk['bug_count']} | "
            f"Rule violations: {risk['rule_count']} | "
            f"Risk score: {risk['risk_score']:.1f} | "
            f"Last issue: {str(risk['last_issue'])[:10]}"
        )

    @staticmethod
    def format_repeated_issues(issues: List[Dict]) -> str:
        if not issues:
            return "No repeated cross-PR issues detected."
        lines = ["### Patterns repeated across previous PRs:"]
        for issue in issues:
            lines.append(
                f"  - `{issue['file_path']}` [{issue['severity']}] "
                f"{issue['description'][:100]} "
                f"(seen {issue['occurrences']}x)"
            )
        return "\n".join(lines)

    @staticmethod
    def format_rules(rules: List[Dict]) -> str:
        if not rules:
            return "No enabled coding rules found."
        lines = ["### Active coding rules to enforce:"]
        for r in rules:
            lines.append(
                f"  - **{r['rule_name']}** [{r['category']}/{r['severity']}]: "
                f"{r['rule_description']}"
            )
        return "\n".join(lines)

    def build_memory_prompt(
        self,
        memory_context: Dict[str, Any],
        file_path: Optional[str] = None,
    ) -> str:
        """
        Build a formatted memory context string suitable for injection
        into an agent prompt. Pass file_path to restrict to a single file.
        """
        sections: List[str] = []

        # File-specific memories
        for fp, findings in memory_context.get("file_memories", {}).items():
            if file_path and fp != file_path:
                continue
            sections.append(self.format_file_memory(fp, findings))

        # Module risk
        for fp, risk in memory_context.get("module_risks", {}).items():
            if file_path and fp != file_path:
                continue
            if risk:
                sections.append(self.format_module_risk(fp, risk))

        # Repeated cross-PR patterns
        sections.append(
            self.format_repeated_issues(memory_context.get("repeated_issues", []))
        )

        # Active rules disabled - model uses its own reasoning
        # sections.append(self.format_rules(memory_context.get("rules", [])))

        return "\n\n".join(sections)


# Module-level singleton
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
