from typing import Optional
from services.git_provider import GitProvider
from services.github_service import get_github_service

def get_provider(provider_name: str) -> Optional[GitProvider]:
    """
    Factory function to retrieve the appropriate GitProvider instance
    based on the provider name string.
    """
    provider_name = provider_name.lower().strip()
    if provider_name == "github":
        return get_github_service()
    
    # Easily extensible to other providers:
    # elif provider_name == "gitlab":
    #     return get_gitlab_service()
    
    return None
