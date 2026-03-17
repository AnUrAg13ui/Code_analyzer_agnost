"""
GitHub REST API service.
Handles PR file fetching, diff retrieval, and review comment posting.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Request
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings
from services.git_provider import GitProvider, PullRequestEvent


logger = logging.getLogger(__name__)
settings = get_settings()


class GitHubService(GitProvider):
    """Async wrapper around the GitHub REST API, implementing the GitProvider interface."""

    @property
    def provider_name(self) -> str:
        return "github"


    def __init__(self):
        self.base_url = settings.GITHUB_API_BASE
        self.token = settings.GITHUB_TOKEN
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers, timeout=30, follow_redirects=True
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ──────────────────────────────────────────────────────────────
    # PR Data
    # ──────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )
    async def get_pr_files(
        self, owner: str, repo: str, pull_number: int
    ) -> List[Dict[str, Any]]:
        """
        GET /repos/{owner}/{repo}/pulls/{pull_number}/files
        Returns list of changed file objects with patch diffs.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        client = await self._get_client()
        results: List[Dict[str, Any]] = []
        page = 1

        try:
            while True:
                resp = await client.get(url, params={"per_page": 100, "page": page})
                if resp.status_code == 404:
                    logger.warning("PR %s not found in %s/%s", pull_number, owner, repo)
                    return []
                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    logger.error("GitHub API Rate Limit exceeded.")
                
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                results.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        except httpx.HTTPStatusError as exc:
            logger.error("GitHub API error %d: %s", exc.response.status_code, exc.response.text)
            raise

        logger.info(
            "Fetched %d changed files for PR #%d in %s/%s",
            len(results), pull_number, owner, repo,
        )
        return results[: settings.MAX_FILES_PER_PR]

    async def get_pr_detail(
        self, owner: str, repo: str, pull_number: int
    ) -> Dict[str, Any]:
        """GET /repos/{owner}/{repo}/pulls/{pull_number}"""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        client = await self._get_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_file_content_snippet(
        self, owner: str, repo: str, file_path: str, ref: str = "HEAD"
    ) -> Optional[str]:
        """Fetch raw file content at a given ref (for surrounding context)."""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{file_path}"
        client = await self._get_client()
        try:
            resp = await client.get(url, params={"ref": ref})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            import base64
            data = resp.json()
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Could not fetch %s@%s: %s", file_path, ref, exc)
        return None

    async def get_commit_history(
        self, owner: str, repo: str, file_path: str, max_commits: int = 20
    ) -> List[Dict[str, Any]]:
        """Fetch recent commits that touched a specific file."""
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        client = await self._get_client()
        resp = await client.get(url, params={"path": file_path, "per_page": max_commits})
        if resp.status_code != 200:
            return []
        return resp.json()

    async def get_git_blame(
        self, owner: str, repo: str, file_path: str, ref: str
    ) -> Optional[str]:
        """
        Approximate git blame using the GitHub blame API (GraphQL).
        Returns a text summary of blame ranges.
        """
        # GitHub REST does not expose blame; skip gracefully
        logger.debug("Git blame via REST is not supported; skipping %s", file_path)
        return None

    # ──────────────────────────────────────────────────────────────
    # Review Comments
    # ──────────────────────────────────────────────────────────────

    async def post_pr_comment(
        self, owner: str, repo: str, pull_number: int, body: str
    ) -> Optional[int]:
        """
        Post an issue-level comment (appears in the PR conversation).
        Returns the GitHub comment ID.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        client = await self._get_client()
        resp = await client.post(url, json={"body": body})
        if resp.status_code in (200, 201):
            comment_id = resp.json().get("id")
            logger.info(
                "Posted review comment #%s on PR #%d", comment_id, pull_number
            )
            return comment_id
        logger.error(
            "Failed to post comment on PR #%d: %s %s",
            pull_number, resp.status_code, resp.text,
        )
        return None

    async def create_review(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        commit_id: str,
        body: str,
        inline_comments: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        """
        Create a formal PR review with optional inline file comments.
        inline_comments: [{"path": str, "line": int, "body": str}, ...]
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        client = await self._get_client()
        payload: Dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": "COMMENT",
        }
        if inline_comments:
            payload["comments"] = inline_comments

        resp = await client.post(url, json=payload)
        if resp.status_code in (200, 201):
            return resp.json()
        logger.error(
            "Failed to create review on PR #%d: %s", pull_number, resp.text
        )
        return None

    # ──────────────────────────────────────────────────────────────
    # Webhook verification
    # ──────────────────────────────────────────────────────────────

    async def verify_webhook_signature(self, request: Request, raw_body: bytes) -> bool:
        """
        Verify the X-Hub-Signature-256 HMAC from GitHub.
        Returns True if valid, False otherwise.
        """
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        secret = settings.GITHUB_WEBHOOK_SECRET
        if not secret:
            logger.warning(
                "GITHUB_WEBHOOK_SECRET not set; skipping signature verification"
            )
            return True  # Allow through in dev mode

        if not signature_header or not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(
            secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        provided = signature_header[len("sha256="):]
        return hmac.compare_digest(expected, provided)

    def parse_webhook_payload(self, request: Request, payload: Dict[str, Any]) -> Optional[PullRequestEvent]:
        """
        Parse GitHub pull_request payloads.
        """
        event_type = request.headers.get("x-github-event", "")
        if event_type != "pull_request":
            return None
        
        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            return None

        pr_data = payload.get("pull_request", {})
        repo_data = payload.get("repository", {})
        
        pr_number = pr_data.get("number")
        owner = repo_data.get("owner", {}).get("login")
        repo = repo_data.get("name")
        head_sha = pr_data.get("head", {}).get("sha", "")

        if not all([pr_number, owner, repo]):
            return None

        return PullRequestEvent(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            action=action,
            head_sha=head_sha
        )


# Module-level singleton
_github_service: Optional[GitHubService] = None


def get_github_service() -> GitHubService:
    global _github_service
    if _github_service is None:
        _github_service = GitHubService()
    return _github_service
