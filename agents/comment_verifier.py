"""
Comment Verifier Agent.
Checks if code comments and documentation accurately describe the actual code behaviour.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from config.prompts.comment_verifier import SYSTEM_PROMPT, FINDING_SCHEMA

logger = logging.getLogger(__name__)


class CommentVerifierAgent:
    """
    Subagent that verifies documentation and comment accuracy against code changes.
    """

    AGENT_NAME = "comment_verifier"
    ISSUE_TYPE = "docs"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        file_contexts: List[Dict[str, Any]],
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """
        Run comment verification over all changed files.
        Skips files without any comments or docstrings in the diff.
        """
        all_findings: List[Dict[str, Any]] = []
        total_confidence = 0.0
        analyzed = 0

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            if file_ctx.get("status") == "removed":
                return [], 0.0

            # Quick pre-filter: only run if the diff contains comments
            patch = file_ctx.get("patch", "")
            has_comments = any(
                marker in patch
                for marker in ('"""', "'''", "#", "//", "/*", "*/", "<!--")
            )
            if not has_comments:
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
                logger.exception("CommentVerifier failed on %s: %s", file_ctx["file_path"], exc)
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
                f"Comment verifier: {len(all_findings)} doc issues across {analyzed} files."
            ),
        }

    def _build_prompt(self, file_ctx: Dict[str, Any], memory_context: str) -> str:
        code_fragment = ContextBuilder.build_comment_verifier_fragment(file_ctx)
        return f"""
Check whether the comments and documentation in the following code changes
are accurate and consistent with the actual implementation.

{memory_context}

{code_fragment}

{FINDING_SCHEMA}
""".strip()
