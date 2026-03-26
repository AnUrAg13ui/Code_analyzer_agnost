"""
Past PR Checker Agent.
Detects repeated mistakes that were flagged in earlier pull requests.
Uses historical findings from PostgreSQL as primary signal.
"""

import asyncio
import itertools
import logging
from typing import Any, Dict, List, Optional, Tuple, cast

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from utils.prompt_loader import load_prompt

SYSTEM_PROMPT, FINDING_SCHEMA = load_prompt("past_pr")

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
        repeated_issues: Optional[List[Dict[str, Any]]] = None,
        role: str = "developer",
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
        # Rebind to a concrete type — Pyre2 doesn't narrow Optional through closures
        _issues: List[Dict[str, Any]] = list(repeated_issues)

        all_findings: List[Dict[str, Any]] = []
        debug_context: List[Dict[str, Any]] = []

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            if file_ctx.get("status") == "removed":
                return [], 0.0

            # Filter repeated issues relevant to this file
            relevant = [
                r for r in _issues
                if r.get("file_path") == file_ctx["file_path"]
            ]
            if not relevant:
                # Still check with full context but lower weight
                relevant = list(itertools.islice(_issues, 5))

            prompt = self._build_prompt(file_ctx, "", relevant, role)
            debug_context.append({
                "file_path": file_ctx.get("file_path", "unknown"),
                "file_context": file_ctx,
                "prompt": prompt,
                "relevant_issues": relevant,
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
                logger.exception("PastPRAgent failed on %s: %s", file_ctx["file_path"], exc)
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
                f"Past PR checker: {len(all_findings)} repeated issues across {analyzed} files."
            ),
            "debug_context": debug_context,
        }

    def _build_prompt(
        self,
        file_ctx: Dict[str, Any],
        memory_context: str,
        repeated_issues: List[Dict],
        role: str,
    ) -> str:
        code_fragment = ContextBuilder.build_past_pr_fragment(file_ctx)

        # Build a rich, structured block of previous findings for the LLM
        past_issues_lines = []
        for idx, r in enumerate(repeated_issues, 1):
            past_issues_lines.append(
                f"[{idx}] Severity: {r.get('severity', 'unknown').upper()}\n"
                f"    Type    : {r.get('issue_type', 'unknown')}\n"
                f"    File    : {r.get('file_path', 'unknown')}\n"
                f"    Seen    : {r.get('occurrences', 1)}x in previous PRs\n"
                f"    Detail  : {r.get('description', 'No description')}"
            )
        past_issues_text = "\n\n".join(past_issues_lines) if past_issues_lines else "None recorded."

        return f"""
Your task: Analyze the current code change below and determine if it repeats or
resembles issues that were flagged in PREVIOUS pull requests of the same repository.

## PREVIOUSLY FLAGGED ISSUES (from database of past PR reviews):
{past_issues_text}

## CURRENT CODE CHANGE:
{code_fragment}

## OUTPUT FORMAT:
{FINDING_SCHEMA}
""".strip()
