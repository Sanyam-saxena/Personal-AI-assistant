"""
Domain exception hierarchy.

Centralising all application-level exceptions here means:

* Routes can import exception classes without importing the service module,
  eliminating a circular-import risk.
* Unit tests can ``raise`` and ``catch`` exceptions in isolation.
* The complete hierarchy is visible in one place.

Hierarchy
---------
AppError
└── OllamaServiceError
    ├── OllamaConnectionError   TCP-level failure
    ├── OllamaTimeoutError      Read timeout exceeded
    └── OllamaResponseError     Unexpected HTTP status or invalid payload
"""


class AppError(Exception):
    """Root exception for all application domain errors."""


# ── Ollama ─────────────────────────────────────────────────────────────────


class OllamaServiceError(AppError):
    """Base class for all errors originating in the Ollama integration."""


class OllamaConnectionError(OllamaServiceError):
    """Raised when a TCP connection to the Ollama server cannot be established."""


class OllamaTimeoutError(OllamaServiceError):
    """Raised when an Ollama request exceeds the configured read timeout."""


class OllamaResponseError(OllamaServiceError):
    """
    Raised when Ollama returns an unexpected HTTP status code or when
    the response body cannot be parsed / validated against the expected schema.
    """
