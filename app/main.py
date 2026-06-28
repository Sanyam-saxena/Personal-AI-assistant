"""
Application entry point.

Exposes the ``app`` instance that Uvicorn targets::

    uvicorn app.main:app --reload

Architecture decisions
----------------------
**configure_logging first**
    ``configure_logging()`` is called at the top of ``create_application()``
    — not at module level — so test fixtures that mutate environment variables
    (or call ``get_settings.cache_clear()``) can set the desired log level
    before the logging system is configured.  Calling it at module level
    would bake in the level at import time, before any test env override runs.

**422 handler on ``app``, not ``router``**
    FastAPI raises ``RequestValidationError`` during Pydantic body parsing,
    *before* routing occurs.  ``APIRouter`` has no ``.exception_handler()``
    method; a router-level handler is therefore impossible and would crash the
    application at startup.  The 422 handler is registered directly on the
    ``app`` instance here.

**App singleton via app.state**
    ``OllamaService`` is created once during lifespan startup and stored in
    ``app.state.ollama``.  Route dependencies read it from there, allowing the
    underlying ``requests.Session`` TCP-connection pool to be reused across
    all requests.  ``OllamaService.close()`` is called on shutdown to drain
    in-flight connections cleanly.

**Middleware registration order**
    Starlette processes ``add_middleware()`` calls in **reverse registration
    order** — the last call becomes the outermost wrapper.  The resulting
    chain for inbound requests is:

         CORSMiddleware         (outermost, first)
         -> BodyLimitMiddleware
         -> RequestIDMiddleware  (innermost, last)
         -> route handler

    CORSMiddleware must be outermost so it handles ``OPTIONS`` preflight
    before other middleware or handlers run.  BodyLimitMiddleware is placed
    before RequestIDMiddleware so oversized bodies are rejected before a
    correlation ID is allocated (minor efficiency gain).

**CORS credentials and wildcard**
    ``allow_credentials`` is automatically set to ``False`` when
    ``CORS_ORIGINS`` includes ``"*"``.  The Fetch specification §3.2.6
    forbids credentialed cross-origin requests to wildcard origins; browsers
    silently reject such responses without an error.

**Production safety guards**
    A startup WARNING is emitted when ``OPENAPI_ENABLED=True`` in a
    production environment so the oversight is visible in logs and monitoring.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.middleware.body_limit import BodyLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.models.schemas import ValidationErrorResponse
from app.routes import chat as chat_router
from app.services.ollama_service import OllamaService
from app.utils.logger import configure_logging

logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """
    FastAPI lifespan context manager.

    **Startup**:
    - Emits the configuration banner (suppressed in production for brevity).
    - Warns if potentially unsafe settings are active in production.
    - Creates the ``OllamaService`` singleton and stores it in ``app.state``.

    **Shutdown**:
    - Drains the TCP connection pool by calling ``OllamaService.close()``.
    """
    settings = get_settings()

    # ── Configuration banner ───────────────────────────────────────────────
    if not settings.is_production:
        logger.info("=" * 60)
        logger.info("  AI Assistant Backend — starting up")
        logger.info("=" * 60)
        logger.info("  Environment       : %s", settings.ENVIRONMENT)
        logger.info("  Version           : %s", settings.APP_VERSION)
        logger.info("  Ollama URL        : %s", settings.OLLAMA_URL)
        logger.info("  Ollama model      : %s", settings.OLLAMA_MODEL)
        logger.info("  Connect timeout   : %ds", settings.OLLAMA_CONNECT_TIMEOUT)
        logger.info("  Read timeout      : %ds", settings.OLLAMA_READ_TIMEOUT)
        logger.info("  Max body size     : %d bytes", settings.MAX_REQUEST_BODY_BYTES)
        logger.info("  Log level         : %s", settings.LOG_LEVEL)
        logger.info(
            "  OpenAPI docs      : %s",
            "enabled -> /docs" if settings.OPENAPI_ENABLED else "disabled",
        )
        logger.info("  CORS origins      : %s", settings.parsed_cors_origins)
        logger.info("=" * 60)
    else:
        # In production emit a single concise line — the full banner is noise
        # in aggregated logs and can expose internal configuration.
        logger.info(
            "AI Assistant Backend starting | env=%s | version=%s | model=%s",
            settings.ENVIRONMENT,
            settings.APP_VERSION,
            settings.OLLAMA_MODEL,
        )

    # ── Production safety warnings ─────────────────────────────────────────
    if settings.is_production and settings.OPENAPI_ENABLED:
        logger.warning(
            "SECURITY: OPENAPI_ENABLED=true in production exposes /docs, "
            "/redoc, and /openapi.json. Set OPENAPI_ENABLED=false to hide them."
        )

    if settings.is_production and "*" in settings.parsed_cors_origins:
        logger.warning(
            "SECURITY: CORS_ORIGINS=* in production. "
            "Set an explicit origin list for production deployments."
        )

    # ── Service singleton ──────────────────────────────────────────────────
    # Storing in app.state means:
    #   - One requests.Session and one TCP pool shared across all requests.
    #   - Tests can inject a mock via app.state.ollama = MagicMock(...)
    app.state.ollama = OllamaService(settings)

    yield  # <- application is serving requests

    # Defensive: ollama may be absent if startup partially failed or a test
    # removed it.  Guard with getattr to prevent a noisy AttributeError.
    ollama = getattr(app.state, "ollama", None)
    if ollama is not None:
        ollama.close()
    logger.info(
        "AI Assistant Backend shutdown complete | env=%s", settings.ENVIRONMENT
    )


# ── Application factory ─────────────────────────────────────────────────────


def create_application() -> FastAPI:
    """
    Construct and return a fully configured :class:`~fastapi.FastAPI` app.

    Using a factory rather than top-level initialisation allows isolated
    instances to be created in tests without importing side-effects.

    Note: ``configure_logging`` is called inside this function (not at module
    level) so test fixtures can override env vars / clear the settings cache
    before the logging system is locked in.
    """
    # ── Bootstrap logging ──────────────────────────────────────────────────
    # Called first so every subsequent log line (including those emitted by
    # middleware and service initialisation) passes through RequestIDFilter.
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    application = FastAPI(
        title=settings.APP_TITLE,
        description=(
            "Production-ready FastAPI backend for a local AI assistant. "
            "Proxies chat requests to a locally running Ollama instance.\n\n"
            "**Quick start:** `POST /chat` with `{\"message\": \"Hello!\"}`"
        ),
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.OPENAPI_ENABLED else None,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    #
    # Registration order is REVERSE of execution order (Starlette builds the
    # chain in reverse).  Execution order for an inbound request:
    #
    #   CORSMiddleware (outermost)
    #   -> BodyLimitMiddleware
    #   -> RequestIDMiddleware (innermost)
    #   -> route handler
    #
    # Both BodyLimitMiddleware and RequestIDMiddleware are pure ASGI
    # middleware (not BaseHTTPMiddleware subclasses), which avoids
    # ContextVar propagation issues and response buffering.

    # Inner: correlation ID, timing, access log, security headers.
    application.add_middleware(RequestIDMiddleware)

    # Middle: reject oversized bodies before they reach Pydantic.
    # Also enforces limits on chunked-encoded bodies via streaming
    # byte counting.
    application.add_middleware(
        BodyLimitMiddleware,
        max_bytes=settings.MAX_REQUEST_BODY_BYTES,
    )

    # Outer: CORS preflight handling.
    origins = settings.parsed_cors_origins
    has_wildcard = "*" in origins
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Fetch spec §3.2.6: credentials are forbidden with wildcard origins.
        # Explicitly disable to prevent browsers silently rejecting responses.
        allow_credentials=not has_wildcard,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # ── Routers ────────────────────────────────────────────────────────────
    application.include_router(chat_router.router)

    # ── Custom Docs Routes with Minimal CSP ─────────────────────────────────
    if settings.OPENAPI_ENABLED:
        from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
        from fastapi.responses import HTMLResponse

        @application.get("/docs", include_in_schema=False)
        async def custom_swagger_ui_html() -> HTMLResponse:
            response = get_swagger_ui_html(
                openapi_url=application.openapi_url or "/openapi.json",
                title=application.title + " - Swagger UI",
                oauth2_redirect_url=application.swagger_ui_oauth2_redirect_url,
                swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
                swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
                swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self'"
            )
            return response

        @application.get("/redoc", include_in_schema=False)
        async def custom_redoc_html() -> HTMLResponse:
            response = get_redoc_html(
                openapi_url=application.openapi_url or "/openapi.json",
                title=application.title + " - ReDoc",
                redoc_js_url="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
                redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "connect-src 'self'"
            )
            return response

    return application


# ── App instance (Uvicorn target) ───────────────────────────────────────────

app: FastAPI = create_application()


# ── Exception handlers ──────────────────────────────────────────────────────
#
# IMPORTANT: These MUST be registered on the ``app`` instance, not on any
# router.  ``APIRouter`` does not support ``.exception_handler()``, and
# ``RequestValidationError`` is raised before routing occurs anyway.


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Replace FastAPI's default 422 response with a sanitised payload.

    The default handler returns the full Pydantic error tree including
    internal field names, Python type names, and constraint values — all
    of which constitute information disclosure about the API's internals.

    This handler returns a fixed generic message that tells the client their
    request is invalid without revealing schema implementation details.  The
    full Pydantic error tree is still logged at DEBUG level for developers.

    Args:
        request: The incoming HTTP request.
        exc:     The ``RequestValidationError`` raised by FastAPI/Pydantic.

    Returns:
        HTTP 422 with a sanitised JSON body.
    """
    logger.debug(
        "Request validation failed | path=%s | errors=%s",
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ValidationErrorResponse().model_dump(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.

    Any :class:`Exception` not caught by a route handler or a more specific
    FastAPI exception handler reaches here.  Note that
    :class:`~fastapi.HTTPException` has its own handler and does **not**
    reach this function.

    Returns a sanitised JSON 500 rather than an HTML error page or an empty
    body so clients always receive a structured response.
    """
    logger.exception(
        "Unhandled exception | %s %s | %s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )
