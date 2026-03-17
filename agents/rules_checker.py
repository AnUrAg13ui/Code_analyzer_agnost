"""
Rules Checker Agent.
Detects coding style violations, naming issues, architecture violations, and bad practices.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from config.prompts.rules_checker import SYSTEM_PROMPT, FINDING_SCHEMA

logger = logging.getLogger(__name__)


class RulesCheckerAgent:
    """
    Subagent responsible for enforcing project coding rules and style standards.
    """

    AGENT_NAME = "rules_checker"
    ISSUE_TYPE = "rule"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        file_contexts: List[Dict[str, Any]],
        memory_context: str = "",
        active_rules: str = "",
    ) -> Dict[str, Any]:
        """
        Run rules checking over all changed files.

        Args:
            file_contexts: List of file context dicts.
            memory_context: Formatted historical memory string.
            active_rules: Formatted list of active coding rules.

        Returns:
            Dict with 'findings', 'confidence', 'summary', 'agent_name'.
        """
        all_findings: List[Dict[str, Any]] = []
        total_confidence = 0.0
        analyzed = 0

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            fp = file_ctx.get("file_path", "unknown")
            if file_ctx.get("status") == "removed":
                return [], 0.0

            prompt = self._build_prompt(file_ctx, memory_context, active_rules)
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
                logger.exception("RulesChecker failed on %s: %s", fp, exc)
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
            "summary": f"Rules checker: {len(all_findings)} violations across {analyzed} files.",
        }

    def _build_prompt(
        self, file_ctx: Dict[str, Any], memory_context: str, active_rules: str
    ) -> str:
        code_fragment = ContextBuilder.build_rules_checker_fragment(file_ctx)
        return f"""
Analyze the following code changes for coding rule violations and bad practices using your own reasoning and best practices knowledge.

{memory_context}
{code_fragment}

{FINDING_SCHEMA}
""".strip()
