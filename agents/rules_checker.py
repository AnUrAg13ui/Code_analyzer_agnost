"""
Rules Checker Agent.
Detects coding style violations, naming issues, architecture violations, and bad practices.
"""

import asyncio
import logging
from typing import Any, Dict, List, Tuple, cast

from utils.deepseek_local_client import LLMClient
from services.context_builder import ContextBuilder
from utils.prompt_loader import load_prompt
from utils.rules_loader import get_custom_rules_text

SYSTEM_PROMPT, FINDING_SCHEMA = load_prompt("rules_checker")

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
        role: str = "developer",
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
        debug_context: List[Dict[str, Any]] = []

        async def analyze_file(file_ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
            fp = file_ctx.get("file_path", "unknown")
            if file_ctx.get("status") == "removed":
                return [], 0.0

            prompt = self._build_prompt(file_ctx, "", active_rules, role)
            debug_context.append({
                "file_path": fp,
                "file_context": file_ctx,
                "prompt": prompt,
                "memory_context": "",
                "active_rules": active_rules,
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
                logger.exception("RulesChecker failed on %s: %s", fp, exc)
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
            "summary": f"Rules checker: {len(all_findings)} violations across {analyzed} files.",
            "debug_context": debug_context,
        }

    def _build_prompt(
        self, file_ctx: Dict[str, Any], memory_context: str, active_rules: str, role: str
    ) -> str:
        code_fragment = ContextBuilder.build_rules_checker_fragment(file_ctx)

        # Load user-defined custom rules — honours APPLY_CUSTOM_RULES setting
        custom_rules_text = get_custom_rules_text()

        role_instruction = f"""
You are acting as a {role.upper()} engineer.

Focus areas:
"""

        if role == "developer":
            role_instruction += """
- Code correctness
- Logic errors
- Maintainability
- Readability
"""
        elif role == "devops":
            role_instruction += """
- Deployment risks
- Environment/config issues
- Scalability concerns
- Missing retries, timeouts
- Secrets exposure
"""
        elif role == "security":
            role_instruction += """
- Vulnerabilities
- Injection risks
- Authentication/authorization issues
- Unsafe data handling
"""

        # Build the rules section — use custom rules if provided, else LLM defaults
        if custom_rules_text:
            rules_section = f"""## PROJECT RULES TO ENFORCE:
{custom_rules_text}"""
        else:
            rules_section = """## RULES:
Apply general software engineering best practices and your own expert knowledge
to identify rule violations (naming, structure, patterns, etc.)."""

        return f"""
{role_instruction}

{rules_section}

## CODE TO REVIEW:
{code_fragment}

## OUTPUT FORMAT:
{FINDING_SCHEMA}
""".strip()

