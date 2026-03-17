import abc
from typing import Any, Dict, List, Optional
from fastapi import Request

class PullRequestEvent:
    """
    Standardized payload format passed from any webhook parser
    into the review graph.
    """
    def __init__(self, owner: str, repo: str, pr_number: int, action: str, head_sha: str = ""):
        self.owner = owner
        self.repo = repo
        self.pr_number = pr_number
        self.action = action
        self.head_sha = head_sha

class GitProvider(abc.ABC):
    """
    Abstract Base Class for Git Provider Integrations (GitHub, GitLab, etc.).
    Defines the methods required by the Code Analyzer Agent.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the provider, e.g. 'github', 'gitlab'"""
        pass

    @abc.abstractmethod
    async def verify_webhook_signature(self, request: Request, raw_body: bytes) -> bool:
        """
        Verify that the webhook genuinely comes from the Git Provider.
        """
        pass

    @abc.abstractmethod
    def parse_webhook_payload(self, request: Request, payload: Dict[str, Any]) -> Optional[PullRequestEvent]:
        """
        Parse the provider-specific webhook payload into a standardized PullRequestEvent.
        Return None if the event should be ignored (e.g. not a PR event).
        """
        pass

    @abc.abstractmethod
    async def get_pr_detail(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """Fetch PR details."""
        pass

    @abc.abstractmethod
    async def get_pr_files(self, owner: str, repo: str, pull_number: int) -> List[Dict[str, Any]]:
        """Fetch list of changed file objects with patch diffs."""
        pass

    @abc.abstractmethod
    async def get_file_content_snippet(self, owner: str, repo: str, file_path: str, ref: str) -> Optional[str]:
        """Fetch the raw text content of a file at a specific Git reference."""
        pass

    @abc.abstractmethod
    async def get_commit_history(self, owner: str, repo: str, file_path: str, max_commits: int) -> List[Dict[str, Any]]:
        """Fetch recent commits that touched a specific file."""
        pass

    @abc.abstractmethod
    async def post_pr_comment(self, owner: str, repo: str, pull_number: int, body: str) -> Optional[int]:
        """Post a review comment to the Pull Request."""
        pass

    async def close(self):
        """Cleanup any underlying HTTP client sessions."""
        pass

