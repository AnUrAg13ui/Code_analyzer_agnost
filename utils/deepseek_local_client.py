"""
Model-agnostic LLM client.

Routes to one of three backends based on LLM_PROVIDER:
  "ollama"  — Ollama local server  (ollama run deepseek-coder)  ← default
  "vllm"    — vLLM OpenAI-compatible server
  "openai"  — OpenAI or any OpenAI-compatible cloud/self-hosted endpoint

Universal override: if LLM_BASE_URL and LLM_MODEL are both set they take
precedence over the provider-specific config, letting you point at any
OpenAI-compatible endpoint without changing LLM_PROVIDER at all.

All three providers speak the OpenAI chat-completions protocol so they
share a single _openai_chat() implementation — switching providers is
purely a configuration change, never a code change.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Global semaphore to throttle LLM requests
_llm_semaphore = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)


# ──────────────────────────────────────────────────────────────────────────────
# Provider resolution
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_params() -> Tuple[str, str, str]:
    """
    Return (base_url, model, api_key) following the override hierarchy:
      1. LLM_BASE_URL + LLM_MODEL env vars   (highest priority)
      2. Provider-specific config block
    """
    # Universal override
    if settings.LLM_BASE_URL and settings.LLM_MODEL:
        return (
            settings.LLM_BASE_URL.rstrip("/"),
            settings.LLM_MODEL,
            settings.LLM_API_KEY or "none",
        )

    p = settings.LLM_PROVIDER.lower()

    if p == "ollama":
        # Ollama exposes an OpenAI-compatible /v1 layer since v0.1.24
        base = settings.OLLAMA_BASE_URL.rstrip("/") + "/v1"
        return base, settings.OLLAMA_MODEL, "none"

    elif p == "vllm":
        base = settings.VLLM_BASE_URL.rstrip("/") + "/v1"
        return base, settings.VLLM_MODEL, "none"

    elif p == "openai":
        return (
            settings.OPENAI_BASE_URL.rstrip("/"),
            settings.OPENAI_MODEL,
            settings.OPENAI_API_KEY,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
            "Valid values: ollama | vllm | openai"
        )


def _resolve_health_url() -> str:
    """Return the URL used for the reachability probe."""
    if settings.LLM_BASE_URL:
        return f"{settings.LLM_BASE_URL.rstrip('/')}/models"

    p = settings.LLM_PROVIDER.lower()
    if p == "ollama":
        # Native tags endpoint — always available even before any model is loaded
        return f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    elif p == "vllm":
        return f"{settings.VLLM_BASE_URL.rstrip('/')}/v1/models"
    elif p == "openai":
        return f"{settings.OPENAI_BASE_URL.rstrip('/')}/models"
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Client
# ──────────────────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Provider-agnostic async LLM client.

    Uses the OpenAI chat-completions protocol for all providers.
    Switching from Ollama to vLLM (or any other endpoint) requires
    only an environment variable change — no code changes.
    """

    def __init__(self):
        self.timeout = settings.LLM_TIMEOUT
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.temperature = settings.LLM_TEMPERATURE

        self._base_url, self._model, self._api_key = _resolve_params()
        self._chat_url = f"{self._base_url}/chat/completions"

        logger.info(
            "LLMClient ready — provider=%s  model=%s  endpoint=%s",
            settings.LLM_PROVIDER,
            self._model,
            self._base_url,
        )

        self._http: Optional[httpx.AsyncClient] = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            logger.debug("LLMClient HTTP session closed.")

    # ── Public API ────────────────────────────────────────────────

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Send a prompt and return the model response as plain text."""
        return await self._openai_chat(prompt, system)

    async def generate_structured(
        self, prompt: str, system: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Like generate() but attempts to parse the response as JSON.
        Falls back to {"raw": <text>} on any parse failure.
        """
        raw = await self.generate(prompt, system)
        return self._safe_parse_json(raw)

    async def health_check(self) -> bool:
        """Return True if the configured model endpoint is reachable."""
        url = _resolve_health_url()
        if not url:
            return False
        try:
            http = await self._get_http()
            resp = await http.get(url, timeout=5)
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Health check failed (%s): %s", url, exc)
            return False

    # ── Single shared implementation ──────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=16),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)),
        reraise=True,
    )
    async def _openai_chat(self, prompt: str, system: Optional[str]) -> str:
        """
        POST to /chat/completions using the OpenAI message format.
        Works identically for Ollama /v1, vLLM, and OpenAI.
        """
        messages: list = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }

        http = await self._get_http()
        try:
            async with _llm_semaphore:
                resp = await http.post(self._chat_url, json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("Failed to connect to LLM at %s: %s", self._chat_url, exc)
            raise
        except httpx.TimeoutException:
            logger.error(
                "LLM request timed out after %ds (provider=%s model=%s)",
                self.timeout, settings.LLM_PROVIDER, self._model,
            )
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "LLM HTTP %s from %s: %s",
                exc.response.status_code,
                self._chat_url,
                exc.response.text[:300],
            )
            raise

        data = resp.json()

        # Standard OpenAI response shape
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            # Fallback for non-standard shapes
            logger.warning(
                "Unexpected LLM response shape; keys present: %s", list(data.keys())
            )
            return (
                data.get("content")
                or data.get("response")
                or data.get("text")
                or str(data)
            )

    # ── Utilities ─────────────────────────────────────────────────

    @staticmethod
    def _safe_parse_json(text: str) -> Dict[str, Any]:
        """
        Extract and parse the first JSON object from model output.
        Handles markdown code fences (```json ... ```) transparently.
        """
        cleaned = text.strip()
        for fence in ("```json", "```"):
            if cleaned.startswith(fence):
                cleaned = cleaned[len(fence):]
                break
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                logger.debug("JSON parse failed (%s); returning raw fallback.", exc)

        return {"raw": text}

    # ── Introspection (used by /health endpoint) ──────────────────

    @property
    def provider(self) -> str:
        return settings.LLM_PROVIDER

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────────

_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return the shared LLMClient singleton (created on first call)."""
    global _client_instance
    if _client_instance is None:
        _client_instance = LLMClient()
    return _client_instance


# Backward-compatibility alias
get_deepseek_client = get_llm_client
