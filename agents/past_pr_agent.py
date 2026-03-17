"""
Past PR Checker Agent.
Detects repeated mistakes that were flagged in earlier pull requests.
Uses historical findings from PostgreSQL as primary signal.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from config.prompts.past_pr import SYSTEM_PROMPT, FINDING_SCHEMA

logger = logging.getLogger(__name__)


class PastPRAgent:
    """
    Subagent that cross-references current changes against historical PR findings.
    """

    AGENT_NAME = "past_pr_agent"
    ISSUE_TYPE = "repeat"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        file_contexts: List[Dict[str, Any]],
        memory_context: str = "",
        repeated_issues: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Run repeated-mistake detection.

        Args:
            file_contexts: Changed file contexts.
            memory_context: Formatted historical memory.
            repeated_issues: Raw list of repeated issue dicts from DB.
        """
        if not repeated_issues:
            return {
                "agent_name": self.AGENT_NAME,
                "findings": [],
                "confidence": 0.9,
                "summary": "No past PR data available for comparison.",
            }

        all_findings: List[Dict[str, Any]] = []
        total_confidence = 0.0
        analyzed = 0

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            if file_ctx.get("status") == "removed":
                return [], 0.0

            # Filter repeated issues relevant to this file
            relevant = [
                r for r in repeated_issues
                if r.get("file_path") == file_ctx["file_path"]
            ]
            if not relevant:
                # Still check with full context but lower weight
                relevant = repeated_issues[:5]

            prompt = self._build_prompt(file_ctx, memory_context, relevant)
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
                logger.exception("PastPRAgent failed on %s: %s", file_ctx["file_path"], exc)
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
                f"Past PR checker: {len(all_findings)} repeated issues across {analyzed} files."
            ),
        }

    def _build_prompt(
        self,
        file_ctx: Dict[str, Any],
        memory_context: str,
        repeated_issues: List[Dict],
    ) -> str:
        code_fragment = ContextBuilder.build_past_pr_fragment(file_ctx)

        past_issues_text = "\n".join(
            f"  - [{r['severity'].upper()}] {r['description'][:100]} "
            f"(occurred {r.get('occurrences', 1)}x)"
            for r in repeated_issues
        )

        return f"""
Analyze whether this code change repeats mistakes that were flagged in past pull requests.

## Previously Flagged Issues (from other PRs in this repo):
{past_issues_text}

{memory_context}

{code_fragment}

{FINDING_SCHEMA}
""".strip()
