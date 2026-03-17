"""
Bug Detector Agent.
Detects logic bugs, security vulnerabilities, memory leaks, and unsafe code patterns.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Tuple

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from config.prompts.bug_detector import SYSTEM_PROMPT, FINDING_SCHEMA

logger = logging.getLogger(__name__)


class BugDetectorAgent:
    """
    Subagent responsible for detecting bugs and security issues.
    Invoked in parallel with other agents by the LangGraph orchestrator.
    """

    AGENT_NAME = "bug_detector"
    ISSUE_TYPE = "bug"

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        file_contexts: List[Dict[str, Any]],
        memory_context: str = "",
    ) -> Dict[str, Any]:
        """
        Run bug detection over all changed files.

        Args:
            file_contexts: List of file context dicts from ContextBuilder.
            memory_context: Formatted historical memory string.

        Returns:
            Dict with 'findings', 'confidence', 'summary', 'agent_name'.
        """
        all_findings: List[Dict[str, Any]] = []
        total_confidence = 0.0
        analyzed = 0

        logger.info("BugDetectorAgent initiating parallel analysis for %d files.", len(file_contexts))

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            fp = file_ctx.get("file_path", "unknown")
            if file_ctx.get("status") == "removed":
                logger.debug("BugDetectorAgent skipping removed file: %s", fp)
                return [], 0.0

            logger.info("BugDetectorAgent analyzing file: %s", fp)
            # Disable memory context (previous findings) for bug detector
            prompt = self._build_prompt(file_ctx, "")
            try:
                result = await self.llm.generate_structured(prompt, SYSTEM_PROMPT)
                logger.info("BugDetectorAgent received results for: %s", fp)
                
                findings = result.get("findings", [])
                confidence = float(result.get("confidence", 0.5))

                for f in findings:
                    f["file_path"] = f.get("file_path") or file_ctx["file_path"]
                    f["agent_name"] = self.AGENT_NAME
                    f["issue_type"] = self.ISSUE_TYPE
                    f["confidence"] = confidence
                
                return findings, confidence
            except Exception as exc:
                logger.exception("BugDetector failed on %s: %s", fp, exc)
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
            "summary": f"Bug detector: {len(all_findings)} findings across {analyzed} files.",
        }

    def _build_prompt(self, file_ctx: Dict[str, Any], memory_context: str) -> str:
        code_fragment = ContextBuilder.build_bug_detector_fragment(file_ctx)
        return f"""
Analyze the following code changes for bugs, vulnerabilities, and unsafe patterns.

{memory_context}

{code_fragment}

{FINDING_SCHEMA}
""".strip()
