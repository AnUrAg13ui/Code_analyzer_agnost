"""
Git History Analyzer Agent.
Identifies risky modules based on commit frequency, churn, and historical bug density.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from config.prompts.git_history import SYSTEM_PROMPT, FINDING_SCHEMA

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
    ) -> Dict[str, Any]:
        """
        Run history-based risk analysis over all changed files.
        Only processes files that have meaningful commit history data.
        """
        all_findings: List[Dict[str, Any]] = []
        total_confidence = 0.0
        analyzed = 0

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            commit_summary = file_ctx.get("commit_summary", "")
            commit_count = file_ctx.get("previous_commit_count", 0)

            # Only run if we have meaningful history
            if not commit_summary or commit_count < 2:
                return [], 0.0

            prompt = self._build_prompt(file_ctx, memory_context)
            try:
                result = await self.llm.generate_structured(prompt, SYSTEM_PROMPT)
                findings = result.get("findings", [])
                confidence = float(result.get("confidence", 0.5))

                for f in findings:
                    f["file_path"] = f.get("file_path") or file_ctx["file_path"]
                    f["agent_name"] = self.AGENT_NAME
                    f["issue_type"] = self.ISSUE_TYPE
                    f["confidence"] = confidence
                
                return findings, confidence
            except Exception as exc:
                logger.exception("GitHistoryAgent failed on %s: %s", file_ctx["file_path"], exc)
                return [], 0.0

        tasks = [analyze_file(ctx) for ctx in file_contexts]
        results = await asyncio.gather(*tasks)

        for findings, confidence in results:
            if findings or confidence > 0:
                all_findings.extend(findings)
                total_confidence += confidence
                analyzed += 1

        avg_confidence = total_confidence / analyzed if analyzed else 0.0
        return {
            "agent_name": self.AGENT_NAME,
            "findings": all_findings,
            "confidence": avg_confidence,
            "summary": (
                f"Git history: {len(all_findings)} risk signals across {analyzed} files."
            ),
        }

    def _build_prompt(self, file_ctx: Dict[str, Any], memory_context: str) -> str:
        code_fragment = ContextBuilder.build_git_history_fragment(file_ctx)
        commit_count = file_ctx.get("previous_commit_count", 0)

        return f"""
Analyze the following file change in the context of its git commit history.
This file has been changed {commit_count} times recently.

{memory_context}

{code_fragment}

{FINDING_SCHEMA}
""".strip()
