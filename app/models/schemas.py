"""
Pydantic schemas for API request / response validation.

Public schemas (used directly by FastAPI route definitions)
------------------------------------------------------------
ChatRequest              POST /chat  -- inbound body
ChatResponse             POST /chat  -- outbound body
HealthResponse           GET  /health -- outbound body
ReadinessResponse        GET  /ready  -- outbound body
ErrorResponse            Payload for non-2xx responses (HTTP 5xx)
ValidationErrorResponse  Sanitised payload for HTTP 422 responses

Internal schemas (used only by OllamaService)
----------------------------------------------
OllamaGenerateResponse   Validated against the Ollama API response body.
                         Stat fields are ``int | None`` because Ollama omits
                         them on cache-hit responses and early-termination.

Design notes
------------
* ``OllamaGenerateResponse`` uses ``model_config = {"extra": "ignore"}`` so
  new fields added by Ollama upgrades do not cause validation errors.
* ``model_config = {"extra": "ignore"}`` is intentionally absent from public
  schemas so unexpected client fields are flagged as validation errors.
* ``ChatRequest.message`` uses a ``field_validator`` to reject
  whitespace-only messages, which would waste compute on Ollama.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ── Public schemas ─────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Inbound body for the ``POST /chat`` endpoint."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=8192,
        description="The user's message to send to the AI assistant.",
        examples=["What is the capital of France?"],
    )

    @field_validator("message")
    @classmethod
    def _sanitise_message(cls, v: str) -> str:
        """
        Sanitise the user message to prevent prompt injection and control character abuse,
        and reject empty or whitespace-only messages.
        """
        if not v.strip():
            raise ValueError("Message must not be empty or whitespace-only.")

        import re
        # Strip null bytes
        v = v.replace("\x00", "")
        # Strip Unicode bidirectional formatting/control characters
        bidi_chars = [
            "\u202e", "\u202d", "\u202a", "\u202b", "\u202c", 
            "\u200e", "\u200f", "\u061c", "\u2066", "\u2067", 
            "\u2068", "\u2069"
        ]
        for char in bidi_chars:
            v = v.replace(char, "")
        # Replace multi-newline role indicators to prevent role/instruction injection
        v = re.sub(r'[\r\n]{2,}\s*(User|Assistant|System)\s*:', r'\n\1:', v, flags=re.IGNORECASE)
        return v

    model_config = {
        "json_schema_extra": {
            "example": {"message": "Explain quantum entanglement simply."}
        }
    }


class ChatResponse(BaseModel):
    """Successful response body for the ``POST /chat`` endpoint."""

    response: str = Field(..., description="The AI-generated reply.")

    model_config = {
        "json_schema_extra": {
            "example": {"response": "Quantum entanglement is a phenomenon..."}
        }
    }


class HealthResponse(BaseModel):
    """Response body for the ``GET /health`` liveness endpoint."""

    status: str = Field(default="healthy", description="Process liveness status.")

    model_config = {"json_schema_extra": {"example": {"status": "healthy"}}}


class ReadinessResponse(BaseModel):
    """Response body for the ``GET /ready`` readiness endpoint."""

    status: str = Field(
        ..., description="'ready' when Ollama is reachable."
    )
    ollama: str = Field(
        ..., description="'reachable' or 'unreachable'."
    )

    model_config = {
        "json_schema_extra": {
            "example": {"status": "ready", "ollama": "reachable"}
        }
    }


class ErrorResponse(BaseModel):
    """Standard error payload for all non-2xx responses (5xx)."""

    detail: str = Field(..., description="Human-readable error description.")

    model_config = {
        "json_schema_extra": {
            "example": {"detail": "Cannot connect to Ollama. Is it running?"}
        }
    }


class ValidationErrorResponse(BaseModel):
    """
    Sanitised error payload for HTTP 422 Unprocessable Entity.

    The default FastAPI 422 handler returns the full Pydantic error tree
    including internal field names, Python type names, and constraint values.
    Replacing it with this schema reduces information disclosure without
    losing client-actionable information.
    """

    detail: str = Field(
        default="Request validation failed. Check the request body.",
        description="Summary of the validation failure.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"detail": "Request validation failed. Check the request body."}
        }
    }


# ── Internal / Ollama schemas ──────────────────────────────────────────────


class OllamaGenerateResponse(BaseModel):
    """
    Response from ``POST /api/generate`` on the Ollama server.

    Stat fields are ``int | None`` because Ollama omits them on cache-hit
    responses and when generation is stopped early.  Unknown extra fields
    returned by newer Ollama versions are silently ignored.
    """

    model: str
    response: str
    done: bool
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None

    model_config = {"extra": "ignore"}
