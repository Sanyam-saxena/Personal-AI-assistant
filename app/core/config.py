"""
Application configuration.

All settings are loaded from environment variables / the .env file.
``get_settings()`` is memoised via ``lru_cache`` so the file is parsed
exactly once per process.  Call ``get_settings.cache_clear()`` in test
fixtures to get a fresh instance between test cases.

Key design decisions
--------------------
* ``OLLAMA_CONNECT_TIMEOUT`` and ``OLLAMA_READ_TIMEOUT`` are separate because
  they serve fundamentally different purposes: a short connect timeout (10 s)
  surfaces "Ollama is down" quickly; a long read timeout (60 s) accommodates
  slow generation on modest hardware without lying to the caller.

* ``ENVIRONMENT`` enables runtime guards (e.g. suppressing the verbose startup
  banner in production, warning when OPENAPI_ENABLED=true in production).

* ``MAX_REQUEST_BODY_BYTES`` is enforced at the ASGI middleware layer — before
  JSON parsing — so oversized bodies are rejected without touching the heap.
  Pydantic's max_length constraint is an *additional* guard, not the first one.

* ``CORS_ORIGINS`` defaults to ``http://localhost:8501`` (the Streamlit frontend)
  rather than ``"*"`` to enforce least-privilege by default.  Use ``"*"``
  explicitly only for local development.

* ``OPENAPI_ENABLED`` defaults to ``True`` for development convenience but
  emits a startup WARNING when set to ``True`` in production.

* ``SYSTEM_PROMPT`` is prepended server-side to every user message before
  sending it to Ollama, providing basic behavioural guardrails.  Override
  via the environment variable.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valid environment names — enforced by a field validator.
EnvironmentType = Literal["development", "staging", "production"]


class Settings(BaseSettings):
    """
    Application settings backed by environment variables.

    Attributes
    ----------
    ENVIRONMENT:              Runtime environment name.
    OLLAMA_URL:               Base URL of the Ollama server.
    OLLAMA_MODEL:             Model tag (must be pulled via ``ollama pull``).
    OLLAMA_CONNECT_TIMEOUT:   TCP handshake timeout in seconds.
    OLLAMA_READ_TIMEOUT:      Full-response read timeout in seconds.
    MAX_REQUEST_BODY_BYTES:   Hard cap on inbound request body size.
    APP_TITLE:                Title shown in the OpenAPI UI.
    APP_VERSION:              Semantic version string.
    LOG_LEVEL:                Root logging level.
    CORS_ORIGINS:             Comma-separated allowed origins (default: localhost:8501).
    OPENAPI_ENABLED:          Expose /docs, /redoc, /openapi.json when True.
    SYSTEM_PROMPT:            System prompt prepended to every user message.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Runtime environment ───────────────────────────────────────────────────
    ENVIRONMENT: EnvironmentType = "development"

    # ── Ollama ────────────────────────────────────────────────────────────────
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3"
    OLLAMA_CONNECT_TIMEOUT: int = 10
    OLLAMA_READ_TIMEOUT: int = 60

    # ── Request limits ────────────────────────────────────────────────────────
    # 32 KB is generous for a chat message. Raise if you need longer prompts.
    MAX_REQUEST_BODY_BYTES: int = 32_768

    # ── Application ───────────────────────────────────────────────────────────
    APP_TITLE: str = "AI Assistant Backend"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"

    # ── Security ─────────────────────────────────────────────────────────────
    # Default to the Streamlit frontend origin for least-privilege.
    # Use "*" for local dev only if you need cross-origin from other tools.
    # Production: CORS_ORIGINS=http://frontend.example.com,https://frontend.example.com
    CORS_ORIGINS: str = "http://localhost:8501"
    # Set to false in production to hide /docs, /redoc, and /openapi.json.
    OPENAPI_ENABLED: bool = True
    # Comma-separated list of trusted proxy IPs (e.g. 10.0.0.1,192.168.1.1).
    # If empty, all X-Forwarded-For headers are ignored.
    TRUSTED_PROXIES: str = ""

    # ── AI Guardrails ────────────────────────────────────────────────────────
    # System prompt prepended server-side to every user message.
    # Override via SYSTEM_PROMPT env var for custom behaviour.
    SYSTEM_PROMPT: str = (
        "You are a helpful, concise AI assistant. "
        "Do not generate executable code unless explicitly asked. "
        "Do not reveal internal system details."
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("OLLAMA_URL")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        """Normalise URL so path concatenation is always predictable."""
        return v.rstrip("/")

    @field_validator("OLLAMA_CONNECT_TIMEOUT", "OLLAMA_READ_TIMEOUT", "MAX_REQUEST_BODY_BYTES")
    @classmethod
    def _must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be a positive integer.")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def _valid_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}.")
        return upper

    # ── Computed helpers ──────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running in the production environment."""
        return self.ENVIRONMENT == "production"

    @property
    def parsed_cors_origins(self) -> list[str]:
        """
        Return ``CORS_ORIGINS`` as a list.

        ``"*"`` → ``["*"]``
        ``"https://a.com,https://b.com"`` → ``["https://a.com", "https://b.com"]``
        """
        raw = self.CORS_ORIGINS.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def parsed_trusted_proxies(self) -> list[str]:
        """
        Return ``TRUSTED_PROXIES`` as a list.
        """
        raw = self.TRUSTED_PROXIES.strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(",") if p.strip()]


@lru_cache()
def get_settings() -> Settings:
    """
    Return the cached singleton settings instance.

    Memoised with ``lru_cache`` so ``.env`` is read exactly once.
    In test fixtures call ``get_settings.cache_clear()`` to reset.
    """
    return Settings()
