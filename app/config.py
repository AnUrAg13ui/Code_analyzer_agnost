"""
Configuration management for the AI Code Analyzer Agent.
Loads settings from environment variables with sensible defaults.

Supported LLM providers (LLM_PROVIDER):
  "ollama"  — Ollama local server   (ollama run deepseek-coder)  ← default
  "vllm"    — vLLM OpenAI-compatible server
  "openai"  — OpenAI or any OpenAI-compatible API

Universal override: set LLM_BASE_URL + LLM_MODEL to bypass
provider-specific defaults and point at any endpoint directly.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────
    APP_NAME: str = "AI Code Analyzer Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── FastAPI ───────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ── GitHub ────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_API_BASE: str = "https://api.github.com"

    # ── PostgreSQL ────────────────────────────────────────────────
    USE_DATABASE: bool = True
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/code_analyzer"
    ASYNC_DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/code_analyzer"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ── LLM Provider selection ────────────────────────────────────
    # "ollama" | "vllm" | "openai"
    LLM_PROVIDER: str = "ollama"

    # ── Ollama (default) ──────────────────────────────────────────
    # Run:  ollama run deepseek-coder
    # Ollama exposes both its native API and an OpenAI-compat /v1 layer.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "deepseek-coder:1.3b"   # official Ollama model tag

    # ── vLLM ─────────────────────────────────────────────────────
    VLLM_BASE_URL: str = "http://localhost:8000"
    VLLM_MODEL: str = "deepseek-ai/deepseek-coder-6.7b-instruct"

    # ── OpenAI / any OpenAI-compatible endpoint ───────────────────
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_API_KEY: str = "none"   # use "none" for local/keyless endpoints

    # ── Universal overrides (highest priority) ────────────────────
    # When BOTH are set they take precedence over provider-specific config.
    # Use this to switch models without changing LLM_PROVIDER.
    LLM_BASE_URL: str = ""   # e.g. "http://myserver:11434/v1"
    LLM_MODEL: str = ""      # e.g. "codellama:13b"
    LLM_API_KEY: str = ""    # API key if your override endpoint needs one

    # ── Shared inference parameters ───────────────────────────────
    LLM_TIMEOUT: int = 120
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.1   # low → deterministic code analysis
    LLM_MAX_CONCURRENCY: int = 3   # simultaneous requests to local provider

    # ── Analysis tuning ───────────────────────────────────────────
    CONFIDENCE_THRESHOLD: float = 0.65   # minimum score to surface a finding
    MAX_FILES_PER_PR: int = 50
    MAX_DIFF_LINES: int = 1000    # Reduced from 3000 to speed up processing
    PARALLEL_AGENT_TIMEOUT: int = 180    # Reduced from 600s to 3min for faster feedback

    # TEST 
    ACTIVE_AGENTS: str = "bug_detector"   # comma-separated list of active agents for testing
    ANALYSIS_ROLE: str = "developer"      # "developer", "devops", or "security"
    # ── Severity weights (used in confidence scoring) ─────────────
    SEVERITY_WEIGHTS: dict = {
        "high": 1.0,
        "medium": 0.7,
        "low": 0.4,
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton Settings object."""
    return Settings()
