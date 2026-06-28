"""
Ollama integration service.

Design decisions
----------------
**Application singleton**
    ``OllamaService`` is created once during lifespan startup and stored in
    ``app.state.ollama``.  Route dependencies read it from there.  This means
    the underlying ``requests.Session`` TCP-connection pool is shared across
    all requests rather than being re-created per request.

**requests.Session with connection pool**
    ``pool_maxsize=20`` allows up to 20 simultaneous keep-alive connections.
    Raise this value if you expect more than 20 concurrent requests.
    Note: since ``requests`` is synchronous, each in-flight request occupies
    one thread from FastAPI's thread pool (default 40).  Under very high
    concurrency consider migrating to ``httpx.AsyncClient`` so the event
    loop is never blocked.

**Split connect / read timeouts**
    ``timeout=(connect_timeout, read_timeout)`` is passed to every request.
    A short connect timeout (default 10 s) surfaces "Ollama is down" quickly.
    A long read timeout (default 60 s) accommodates slow generation.

**System prompt**
    A configurable system prompt is prepended server-side to every user
    message.  This provides basic behavioural guardrails and cannot be
    bypassed by a direct API caller.

**No double-logging**
    Technical error details are logged at the point of failure in this module.
    Route handlers do NOT re-log them -- they only map exception types to HTTP
    status codes.  This eliminates duplicate log records.

**Pydantic validation of Ollama response**
    ``OllamaGenerateResponse.model_validate()`` is used instead of raw dict
    access.  If Ollama's wire format changes we get a ``ValidationError`` with
    a precise field diff rather than a bare ``KeyError`` at an unexpected site.

**Exceptions centralised**
    Exceptions live in ``app.core.exceptions`` so the route layer can import
    them independently of this module, avoiding circular imports.

**Log encoding safety**
    Log messages use only ASCII characters to avoid ``UnicodeEncodeError``
    on Windows terminals running the ``cp1252`` code page.
"""

from __future__ import annotations

import logging
import time

import requests
from pydantic import ValidationError
from requests.adapters import HTTPAdapter
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    HTTPError,
    RequestException,
    Timeout,
)

from app.core.config import Settings
from app.core.exceptions import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaServiceError,
    OllamaTimeoutError,
)
from app.models.schemas import OllamaGenerateResponse

logger = logging.getLogger(__name__)

# Timeout used exclusively for the is_available() health probe.
# Kept short and independent of the configured generation timeout.
_PROBE_TIMEOUT: tuple[int, int] = (5, 5)

# Maximum characters of the model response to log at DEBUG level.
# Enough to verify output without flooding logs on long responses.
_RESPONSE_LOG_CHARS = 200


class OllamaService:
    """
    Application-scoped HTTP client for the Ollama ``/api/generate`` endpoint.

    Must be created once at startup and stored in ``app.state``::

        app.state.ollama = OllamaService(settings=get_settings())

    All public methods are **synchronous** and should be called from FastAPI
    ``def`` (non-async) path operations.  FastAPI dispatches ``def`` handlers
    to a thread-pool executor automatically, keeping the event loop unblocked.

    Args:
        settings: Application settings instance.
        session:  Optional ``requests.Session`` to use.  Pass a mock session
                  in unit tests to avoid real HTTP calls.
    """

    def __init__(
        self,
        settings: Settings,
        session: requests.Session | None = None,
    ) -> None:
        self._model: str = settings.OLLAMA_MODEL
        self._system_prompt: str = settings.SYSTEM_PROMPT
        self._connect_timeout: int = settings.OLLAMA_CONNECT_TIMEOUT
        self._read_timeout: int = settings.OLLAMA_READ_TIMEOUT
        self._generate_url: str = f"{settings.OLLAMA_URL}/api/generate"
        self._tags_url: str = f"{settings.OLLAMA_URL}/api/tags"
        self._session: requests.Session = session or self._build_session()

        logger.info(
            "OllamaService ready | model=%s | connect_timeout=%ds | read_timeout=%ds",
            self._model,
            self._connect_timeout,
            self._read_timeout,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def generate(self, prompt: str) -> str:
        """
        Send *prompt* to Ollama and return the generated text.

        The configured system prompt is prepended server-side so API
        clients cannot bypass behavioural guardrails.

        Args:
            prompt: The user's raw message string.

        Returns:
            The model's reply as a plain string.

        Raises:
            OllamaConnectionError: Ollama server is not reachable.
            OllamaTimeoutError:    Request exceeded the read timeout.
            OllamaResponseError:   HTTP error or invalid response payload.
            OllamaServiceError:    Any other transport-level failure.
        """
        # Prepend the system prompt to provide guardrails.
        sanitised_prompt = self._sanitise_prompt(prompt)
        full_prompt = f"{self._system_prompt}\n\nUser: {sanitised_prompt}" if self._system_prompt else sanitised_prompt

        payload: dict[str, object] = {
            "model": self._model,
            "prompt": full_prompt,
            "stream": False,
        }

        logger.debug(
            "Ollama -> | model=%s | prompt_len=%d chars",
            self._model,
            len(full_prompt),
        )

        t0 = time.monotonic()
        raw = self._make_request(self._generate_url, payload)
        ollama_resp = self._parse_response(raw)
        elapsed_ms = (time.monotonic() - t0) * 1000

        logger.info(
            "Ollama <- | model=%s | done=%s | tokens=%s | response_len=%d chars | %.0fms",
            ollama_resp.model,
            ollama_resp.done,
            ollama_resp.eval_count,  # None when Ollama omits it
            len(ollama_resp.response),
            elapsed_ms,
        )

        # Debug-level preview: first N chars -- useful when investigating
        # model quality issues without flooding logs by default.
        logger.debug(
            "Ollama response preview | %s%s",
            ollama_resp.response[:_RESPONSE_LOG_CHARS],
            "..." if len(ollama_resp.response) > _RESPONSE_LOG_CHARS else "",
        )

        return ollama_resp.response

    def is_available(self) -> bool:
        """
        Perform a lightweight reachability probe against Ollama.

        Uses a short, fixed timeout independent of the configured generation
        timeout so a slow model does not make the readiness probe time out.

        Returns:
            ``True`` if Ollama responds with HTTP 200, ``False`` otherwise.
        """
        try:
            resp = self._session.get(self._tags_url, timeout=_PROBE_TIMEOUT)
            available = resp.status_code == 200
            if not available:
                logger.warning(
                    "Ollama probe returned unexpected status | status=%d",
                    resp.status_code,
                )
            return available
        except (RequestsConnectionError, Timeout):
            # Expected failure modes: Ollama not running or taking too long.
            logger.debug("Ollama probe failed -- server unreachable or timed out")
            return False
        except RequestException as exc:
            # Unexpected failure (SSL error, proxy error, etc.) -- log it so
            # operators can investigate rather than seeing a silent False.
            logger.warning(
                "Ollama probe raised unexpected exception | type=%s | error=%s",
                type(exc).__name__,
                exc,
            )
            return False

    def close(self) -> None:
        """
        Drain the connection pool.

        Should be called in the application lifespan shutdown hook so
        in-flight connections are drained cleanly before the process exits.
        """
        self._session.close()
        logger.debug("OllamaService session closed.")

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _build_session() -> requests.Session:
        """
        Create a ``requests.Session`` with a tuned connection pool.

        ``pool_maxsize=20`` supports up to 20 simultaneous keep-alive
        connections.  The previous value of 10 caused connection queuing under
        moderate concurrency.  Tune to match expected peak concurrency.
        """
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=20)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _make_request(
        self, url: str, payload: dict[str, object]
    ) -> requests.Response:
        """
        POST *payload* to *url* and return the raw ``Response``.

        Translates transport-level ``requests`` exceptions to domain exceptions.
        Internal Ollama error bodies are logged here for operator visibility but
        are **not** propagated to callers so they cannot leak to API clients.

        Returns:
            The ``requests.Response`` object (guaranteed 2xx status).

        Raises:
            OllamaConnectionError: TCP connection failed.
            OllamaTimeoutError:    Read timeout exceeded.
            OllamaResponseError:   Non-2xx HTTP status.
            OllamaServiceError:    Any other transport failure.
        """
        try:
            # json= auto-sets Content-Type: application/json; charset=utf-8
            response = self._session.post(
                url=url,
                json=payload,
                timeout=(self._connect_timeout, self._read_timeout),
            )
            response.raise_for_status()
            return response

        except RequestsConnectionError as exc:
            logger.error("Ollama unreachable | url=%s", url)
            raise OllamaConnectionError(
                "Cannot connect to Ollama. Make sure it is running."
            ) from exc

        except Timeout as exc:
            logger.error(
                "Ollama timed out | connect=%ds read=%ds",
                self._connect_timeout,
                self._read_timeout,
            )
            raise OllamaTimeoutError(
                f"Ollama did not respond within {self._read_timeout}s."
            ) from exc

        except HTTPError as exc:
            status_code = (
                exc.response.status_code if exc.response is not None else 0
            )
            body = exc.response.text[:500] if exc.response is not None else ""
            # Log full body for operators; callers receive only the status code.
            logger.error(
                "Ollama HTTP error | status=%d | body=%.300s",
                status_code,
                body,
            )
            if status_code == 404:
                raise OllamaResponseError(
                    "The requested model was not found on the Ollama server."
                ) from exc
            raise OllamaResponseError(
                "Ollama returned an unexpected HTTP error response."
            ) from exc

        except RequestException as exc:
            logger.error(
                "Unexpected Ollama request error | type=%s",
                type(exc).__name__,
            )
            raise OllamaServiceError(
                "An unexpected error occurred while communicating with Ollama."
            ) from exc

    @staticmethod
    def _parse_response(response: requests.Response) -> OllamaGenerateResponse:
        """
        Deserialise and validate the Ollama response payload.

        Using ``model_validate()`` means a schema mismatch raises a
        ``ValidationError`` with a precise field-level diff rather than a
        bare ``KeyError`` from raw dict access.

        Returns:
            Validated :class:`~app.models.schemas.OllamaGenerateResponse`.

        Raises:
            OllamaResponseError: JSON decode failure or schema mismatch.
        """
        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "Ollama non-JSON body | body=%.200s", response.text[:200]
            )
            raise OllamaResponseError(
                "Ollama returned a response that is not valid JSON."
            ) from exc

        try:
            return OllamaGenerateResponse.model_validate(data)
        except ValidationError as exc:
            logger.error(
                "Ollama response schema mismatch | errors=%s", exc.errors()
            )
            raise OllamaResponseError(
                "Ollama response did not match the expected schema."
            ) from exc

    @staticmethod
    def _sanitise_prompt(prompt: str) -> str:
        """Sanitise the user prompt to prevent prompt injection and control character abuse."""
        import re
        # Strip null bytes
        prompt = prompt.replace("\x00", "")
        # Strip Unicode bidirectional formatting/control characters
        bidi_chars = [
            "\u202e", "\u202d", "\u202a", "\u202b", "\u202c", 
            "\u200e", "\u200f", "\u061c", "\u2066", "\u2067", 
            "\u2068", "\u2069"
        ]
        for char in bidi_chars:
            prompt = prompt.replace(char, "")
        # Replace multi-newline role indicators to prevent role/instruction injection
        prompt = re.sub(r'[\r\n]{2,}\s*(User|Assistant|System)\s*:', r'\n\1:', prompt, flags=re.IGNORECASE)
        return prompt
