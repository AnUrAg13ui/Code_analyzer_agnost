"""
Context builder: fetches PR files and constructs a rich analysis context.
Includes diff parsing, surrounding code lines, AST awareness, and commit history.
"""

import ast
import asyncio
import logging
import textwrap
from typing import Any, Dict, List, Optional, Tuple

from app.config import get_settings
from services.git_provider import GitProvider

logger = logging.getLogger(__name__)
settings = get_settings()


class PRContext:
    """Structured context object passed to the LangGraph workflow."""

    def __init__(
        self,
        repo: str,
        pr_number: int,
        owner: str,
        head_sha: str,
        pr_title: str,
        pr_description: str,
        files: List[Dict[str, Any]],
    ):
        self.repo = repo
        self.pr_number = pr_number
        self.owner = owner
        self.head_sha = head_sha
        self.pr_title = pr_title
        self.pr_description = pr_description
        self.files = files  # List of FileContext dicts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "pr_number": self.pr_number,
            "owner": self.owner,
            "head_sha": self.head_sha,
            "pr_title": self.pr_title,
            "pr_description": self.pr_description,
            "files": self.files,
        }


class ContextBuilder:
    """
    Assembles the full analysis context for a Pull Request.
    Fetches files, parses diffs, extracts AST signals, and
    retrieves commit history for each changed file.
    """

    def __init__(self, provider: GitProvider):
        self.gh = provider

    async def build(
        self, owner: str, repo: str, pr_number: int
    ) -> PRContext:
        """
        Main entry point. Returns a PRContext with all enriched file data.
        """
        # 1. PR metadata
        pr_detail = await self.gh.get_pr_detail(owner, repo, pr_number)
        head_sha = pr_detail.get("head", {}).get("sha", "HEAD")
        pr_title = pr_detail.get("title", "")
        pr_description = pr_detail.get("body", "") or ""

        # 2. Changed files with diffs
        raw_files = await self.gh.get_pr_files(owner, repo, pr_number)

        # 3. Enrich files in parallel. Skip tiny/irrelevant changes if many files exist.
        tasks = [
            self._enrich_file(owner, repo, f, head_sha) 
            for f in raw_files
        ]
        
        if not tasks:
            enriched_files = []
        else:
            enriched_files = list(await asyncio.gather(*tasks))

        return PRContext(
            repo=f"{owner}/{repo}",
            pr_number=pr_number,
            owner=owner,
            head_sha=head_sha,
            pr_title=pr_title,
            pr_description=pr_description,
            files=enriched_files,
        )

    # ──────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────

    async def _enrich_file(
        self,
        owner: str,
        repo: str,
        raw_file: Dict[str, Any],
        head_sha: str,
    ) -> Dict[str, Any]:
        file_path: str = raw_file.get("filename", "")
        patch: str = raw_file.get("patch", "") or ""
        status: str = raw_file.get("status", "modified")

        # Trim very large patches
        if len(patch.splitlines()) > settings.MAX_DIFF_LINES:
            lines = patch.splitlines()[: settings.MAX_DIFF_LINES]
            patch = "\n".join(lines) + "\n... (truncated)"

        added_lines, removed_lines = self._parse_added_removed(patch)

        # Fetch full file for surrounding context
        file_content_snippet: Optional[str] = None
        if status != "removed" and file_path.endswith(
            (".py", ".js", ".ts", ".go", ".java", ".rb", ".rs", ".cpp", ".c", ".cs")
        ):
            file_content_snippet = await self.gh.get_file_content_snippet(
                owner, repo, file_path, head_sha
            )

        # AST analysis for Python files
        ast_summary: Optional[str] = None
        if file_path.endswith(".py") and file_content_snippet:
            ast_summary = self._analyze_python_ast(file_content_snippet)

        # Commit history for risk context
        commit_history = await self.gh.get_commit_history(
            owner, repo, file_path, max_commits=10
        )
        commit_summary = self._summarize_commits(commit_history)

        return {
            "file_path": file_path,
            "status": status,
            "patch": patch,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "additions": raw_file.get("additions", 0),
            "deletions": raw_file.get("deletions", 0),
            "file_content_snippet_snippet": file_content_snippet or "",
            "ast_summary": ast_summary,
            "commit_summary": commit_summary,
            "previous_commit_count": len(commit_history),
        }

    @staticmethod
    def _parse_added_removed(
        patch: str,
    ) -> Tuple[List[str], List[str]]:
        """Split a unified diff patch into added and removed lines."""
        added, removed = [], []
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                removed.append(line[1:])
        return added, removed

    @staticmethod
    def _analyze_python_ast(source: str) -> str:
        """
        Parse a Python file with the AST module and return a concise summary
        of its structure: classes, functions, imports, decorators.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return f"AST parse error: {exc}"

        summary_parts = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in ast.walk(node) if isinstance(n, ast.FunctionDef)
                ]
                summary_parts.append(
                    f"Class `{node.name}` (line {node.lineno}) "
                    f"with methods: {', '.join(methods[:10])}"
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not any(
                    isinstance(p, ast.ClassDef)
                    for p in ast.walk(tree)
                    if hasattr(p, "body") and node in getattr(p, "body", [])
                ):
                    summary_parts.append(
                        f"Function `{node.name}` (line {node.lineno})"
                    )
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                summary_parts.append(f"Import: {', '.join(names)}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                summary_parts.append(f"From `{module}` import: {', '.join(names)}")

        return "\n".join(summary_parts[:50])  # Cap at 50 entries

    @staticmethod
    def _summarize_commits(commits: List[Dict[str, Any]]) -> str:
        """Convert raw commit objects into a readable history string."""
        if not commits:
            return "No recent commits found."
        lines = []
        for c in commits[:10]:
            sha = c.get("sha", "")[:7]
            msg = (c.get("commit", {}).get("message", "") or "").splitlines()[0][:80]
            author = c.get("commit", {}).get("author", {}).get("name", "unknown")
            date = c.get("commit", {}).get("author", {}).get("date", "")[:10]
            lines.append(f"[{sha}] {date} {author}: {msg}")
        return "\n".join(lines)

    @staticmethod
    def build_agent_prompt_fragment(file_ctx: Dict[str, Any]) -> str:
        """
        Produce a concise, structured text fragment for a single file
        to be embedded in an agent prompt.
        """
        parts = [
            f"## File: {file_ctx['file_path']}",
            f"Status: {file_ctx['status']} | "
            f"+{file_ctx['additions']} / -{file_ctx['deletions']} lines",
            "",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```",
        ]

        if file_ctx.get("ast_summary"):
            parts += ["", "### AST Structure", file_ctx["ast_summary"]]

        if file_ctx.get("file_content_snippet_snippet"):
            parts += [
                "",
                "### Current File Content (first 3000 chars)",
                "```",
                file_ctx["file_content_snippet_snippet"],
                "```",
            ]

        if file_ctx.get("commit_summary"):
            parts += ["", "### Recent Commit History", file_ctx["commit_summary"]]

        return "\n".join(parts)

    @staticmethod
    def build_bug_detector_fragment(file_ctx: Dict[str, Any]) -> str:
        """Context slice for Bug Detector: Full file content + Diff + AST."""
        parts = [
            f"## File: {file_ctx['file_path']}",
            f"Status: {file_ctx['status']} | "
            f"+{file_ctx['additions']} / -{file_ctx['deletions']} lines",
            "",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```",
        ]

        if file_ctx.get("file_content_snippet_snippet"):
            parts += [
                "",
                "### Full File Content (Current State)",
                "```",
                file_ctx["file_content_snippet_snippet"],
                "```",
            ]

        if file_ctx.get("ast_summary"):
            parts += ["", "### AST Structure Signal", file_ctx["ast_summary"]]

        return "\n".join(parts)

    @staticmethod
    def build_rules_checker_fragment(file_ctx: Dict[str, Any]) -> str:
        """Context slice for Rules Checker: Diff patch only."""
        return "\n".join([
            f"## File: {file_ctx['file_path']}",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```"
        ])

    @staticmethod
    def build_git_history_fragment(file_ctx: Dict[str, Any]) -> str:
        """Context slice for Git Historian: Diff + Commit Log."""
        parts = [
            f"## File: {file_ctx['file_path']}",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```"
        ]

        if file_ctx.get("commit_summary"):
            parts += ["", "### Recent Commit History", file_ctx["commit_summary"]]

        return "\n".join(parts)

    @staticmethod
    def build_past_pr_fragment(file_ctx: Dict[str, Any]) -> str:
        """Context slice for Past PR Checker: Diff patch only (repeated issues provided separately)."""
        return "\n".join([
            f"## File: {file_ctx['file_path']}",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```"
        ])

    @staticmethod
    def build_comment_verifier_fragment(file_ctx: Dict[str, Any]) -> str:
        """Context slice for Comment Verifier: Full file content + Diff."""
        parts = [
            f"## File: {file_ctx['file_path']}",
            "### Diff Patch",
            "```diff",
            file_ctx["patch"] or "(no patch available)",
            "```"
        ]

        if file_ctx.get("file_content_snippet_snippet"):
            parts += [
                "",
                "### Current File Content (Current State)",
                "```",
                file_ctx["file_content_snippet_snippet"],
                "```",
            ]

        return "\n".join(parts)
