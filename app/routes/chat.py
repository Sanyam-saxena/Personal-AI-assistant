"""
Chat routes.

Three endpoints
---------------
    GET  /health   — liveness probe  (is the process alive?)
    GET  /ready    — readiness probe (can the process serve traffic?)
    POST /chat     — single-turn AI conversation

Service dependency
------------------
``get_ollama_service`` reads the singleton :class:`~app.services.ollama_service.OllamaService`
from ``request.app.state.ollama``.  The service is created once during
application lifespan startup (see ``app.main``) so its ``requests.Session``
TCP-connection pool is shared across all requests.

In tests, override ``app.state.ollama`` with a mock to avoid real HTTP calls::

    app.state.ollama = MagicMock(spec=OllamaService)
    app.state.ollama.generate.return_value = "mocked reply"

Sync vs async
-------------
* ``/chat`` and ``/ready`` are ``def`` (not ``async def``) because they invoke
  :mod:`requests`, a blocking synchronous library.  FastAPI dispatches ``def``
  handlers to a thread-pool executor automatically, keeping the event loop
  unblocked.
* ``/health`` is ``async def`` because it performs no I/O and benefits from
  zero thread-pool overhead.

Logging policy
--------------
Technical error details (URL, HTTP status, response body excerpt, exception
chain) are already logged by :class:`~app.services.ollama_service.OllamaService`
at the point of failure.  Route handlers do **not** re-log those details to
avoid duplicate records.  The access log from
:class:`~app.middleware.request_id.RequestIDMiddleware` covers method, path,
status, and latency for every request.

Exception mapping
-----------------
OllamaConnectionError → 503  Service Unavailable
OllamaTimeoutError    → 504  Gateway Timeout
OllamaResponseError   → 502  Bad Gateway
OllamaServiceError    → 502  Bad Gateway
Exception             → 500  Internal Server Error

422 Validation error handler
-----------------------------
IMPORTANT: FastAPI raises ``RequestValidationError`` during Pydantic body
parsing, *before* routing occurs.  A router-level handler (``@router.exception_handler``)
cannot intercept it — ``APIRouter`` does not even have that method.  The
handler MUST be registered on the ``app`` instance.  See ``app.main`` where
``@app.exception_handler(RequestValidationError)`` is defined.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.rate_limit import rate_limit_dependency

from app.core.exceptions import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaServiceError,
    OllamaTimeoutError,
)
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    ReadinessResponse,
    ValidationErrorResponse,
)
from app.services.ollama_service import OllamaService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Dependency ──────────────────────────────────────────────────────────────


def get_ollama_service(request: Request) -> OllamaService:
    """
    FastAPI dependency: return the application-scoped :class:`OllamaService`.

    Reads the singleton stored in ``app.state.ollama`` (set during lifespan
    startup) rather than constructing a new instance per request.  Creating
    a new instance per request would create a new ``requests.Session`` and a
    new TCP connection pool on every call, defeating keep-alive entirely.

    If ``app.state.ollama`` is absent (lifespan startup failed before the
    service could be created), returns HTTP 503 with a clear message rather
    than letting an ``AttributeError`` propagate as an opaque 500.

    Args:
        request: The current HTTP request, injected by FastAPI.

    Returns:
        The application-scoped :class:`~app.services.ollama_service.OllamaService`.

    Raises:
        HTTPException 503: ``app.state.ollama`` has not been initialised.
    """
    service: OllamaService | None = getattr(request.app.state, "ollama", None)
    if service is None:
        logger.error(
            "get_ollama_service: app.state.ollama is not set. "
            "Lifespan startup may have failed."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is not ready. Please try again shortly.",
        )
    return service


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    description=(
        "Returns ``{'status': 'healthy'}`` as long as the API process is "
        "running.  Performs no I/O and does **not** check Ollama. "
        "Use ``/ready`` for a deeper check."
    ),
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Liveness probe.

    Does not log — health probes are called every few seconds by load
    balancers and monitoring systems; logging every invocation at INFO
    level generates thousands of useless lines per day.  The access log in
    ``RequestIDMiddleware`` is also suppressed for this path.
    """
    return HealthResponse(status="healthy")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Probes Ollama reachability.  Returns ``200`` when Ollama is "
        "reachable and ``503`` when it is not.  Container orchestrators "
        "should poll this endpoint to stop routing traffic to unready pods."
    ),
    tags=["System"],
    responses={
        200: {"model": ReadinessResponse, "description": "Service is ready"},
        503: {"model": ErrorResponse, "description": "Ollama is unreachable"},
    },
)
def ready(
    request: Request,
    service: OllamaService = Depends(get_ollama_service),
) -> ReadinessResponse:
    """
    Readiness probe.

    Calls ``OllamaService.is_available()`` which performs a lightweight
    ``GET /api/tags`` against Ollama with a fixed 5-second timeout.
    The result is cached for 2 seconds in app state to prevent hammering Ollama.
    """
    import time
    now = time.monotonic()
    cached_status = getattr(request.app.state, "_ready_status", None)
    cached_time = getattr(request.app.state, "_ready_time", 0.0)

    if cached_status is not None and (now - cached_time) < 2.0:
        is_available = cached_status
    else:
        is_available = service.is_available()
        request.app.state._ready_status = is_available
        request.app.state._ready_time = now

    if not is_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Ollama is unreachable. "
                "Ensure the server is running: `ollama serve`"
            ),
        )
    return ReadinessResponse(status="ready", ollama="reachable")


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with the AI assistant",
    description=(
        "Send a message to the locally running Ollama model and receive "
        "a generated reply.  Ollama errors are mapped to semantically "
        "correct HTTP 5xx status codes."
    ),
    tags=["Chat"],
    dependencies=[Depends(rate_limit_dependency)],
    responses={
        200: {"model": ChatResponse,            "description": "Successful AI response"},
        413: {"model": ErrorResponse,           "description": "Request body too large"},
        422: {"model": ValidationErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse,           "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse,           "description": "Unexpected internal server error"},
        502: {"model": ErrorResponse,           "description": "Invalid response from Ollama"},
        503: {"model": ErrorResponse,           "description": "Ollama is unreachable"},
        504: {"model": ErrorResponse,           "description": "Ollama timed out"},
    },
)
def chat(
    request: ChatRequest,
    service: OllamaService = Depends(get_ollama_service),
) -> ChatResponse:
    """
    Single-turn chat endpoint.

    Forwards the validated message to Ollama and returns the generated
    text.  Domain exceptions raised by :class:`OllamaService` are caught
    and re-raised as :class:`~fastapi.HTTPException` with appropriate status
    codes.

    The service layer already logs technical details at the point of failure;
    this handler does **not** re-log them to avoid duplicate records.

    Args:
        request: Validated request body.
        service: Injected application-scoped OllamaService.

    Returns:
        :class:`~app.models.schemas.ChatResponse` containing the AI reply.
    """
    logger.debug("POST /chat | message_len=%d chars", len(request.message))

    try:
        text = service.generate(request.message)
        return ChatResponse(response=text)

    except OllamaConnectionError as exc:
        # Technical details are already logged by the service layer.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is currently unavailable. Please try again later.",
        ) from exc

    except OllamaTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The AI service took too long to respond. Please try a shorter message.",
        ) from exc

    except (OllamaResponseError, OllamaServiceError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI service returned an invalid response. Please try again.",
        ) from exc

    except Exception as exc:  # noqa: BLE001
        # Catches unexpected exceptions not logged by the service layer
        # (e.g. a future bug in a new code path).
        logger.exception("Unhandled error in POST /chat")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from exc
