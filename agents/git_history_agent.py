"""
Git History Analyzer Agent.
Identifies risky modules based on commit frequency, churn, and historical bug density.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple, cast

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from utils.prompt_loader import load_prompt

SYSTEM_PROMPT, FINDING_SCHEMA = load_prompt("git_history")

logger = logging.getLogger(__name__)


class GitHistoryAgent:
    """
    Subagent that analyses git commit history to flag high-risk modules.
    """

    AGENT_NAME = "git_history_agent"
    ISSUE_TYPE = "history"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        file_contexts: List[Dict[str, Any]],
        memory_context: str = "",
        role: str = "developer",
    ) -> Dict[str, Any]:
        """
        Run history-based risk analysis over all changed files.
        Only processes files that have meaningful commit history data.
        """
        all_findings: List[Dict[str, Any]] = []
        debug_context: List[Dict[str, Any]] = []

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            commit_summary = file_ctx.get("commit_summary", "")
            commit_count = file_ctx.get("previous_commit_count", 0)

            # Only run if we have meaningful history
            if not commit_summary or commit_count < 2:
                return [], 0.0

            prompt = self._build_prompt(file_ctx, "", role)
            debug_context.append({
                "file_path": file_ctx.get("file_path", "unknown"),
                "file_context": file_ctx,
                "prompt": prompt,
                "commit_summary": commit_summary,
                "commit_count": commit_count,
            })
            try:
                result = await self.llm.generate_structured(prompt, SYSTEM_PROMPT)
                findings = result.get("findings", [])
                confidence = float(result.get("confidence", 0.5))

                for f in findings:
                    f["file_path"] = f.get("file_path") or file_ctx["file_path"]
                    f["agent_name"] = self.AGENT_NAME
                    f["issue_type"] = self.ISSUE_TYPE
                    f["confidence"] = confidence
                    f["role"] = role
                
                return findings, confidence
            except Exception as exc:
                logger.exception("GitHistoryAgent failed on %s: %s", file_ctx["file_path"], exc)
                return [], 0.0

        tasks = [analyze_file(ctx) for ctx in file_contexts]
        results = await asyncio.gather(*tasks)

        valid_results: List[Tuple[List[Dict[str, Any]], float]] = [
            (f, c) for f, c in results if f or c > 0
        ]
        for findings, _ in valid_results:
            all_findings.extend(findings)
        analyzed: int = len(valid_results)
        total_confidence: float = sum(c for _, c in valid_results)

        avg_confidence: float = total_confidence / analyzed if analyzed else 0.0
        return {
            "agent_name": self.AGENT_NAME,
            "findings": all_findings,
            "confidence": avg_confidence,
            "summary": (
                f"Git history: {len(all_findings)} risk signals across {analyzed} files."
            ),
            "debug_context": debug_context,
        }

    def _build_prompt(self, file_ctx: Dict[str, Any], memory_context: str, role: str) -> str:
        code_fragment = ContextBuilder.build_git_history_fragment(file_ctx)
        commit_count = file_ctx.get("previous_commit_count", 0)

        return f"""
Analyze the following file change in the context of its git commit history.
This file has been changed {commit_count} times recently.

{code_fragment}

{FINDING_SCHEMA}
""".strip()
