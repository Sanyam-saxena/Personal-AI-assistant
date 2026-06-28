"""
Request ID, timing, access logging, and security-headers middleware (pure ASGI).

Responsibilities (one middleware, one concern group)
----------------------------------------------------
1. **Correlation ID** -- assigns a UUID4 to every request, propagates it via
   ``scope["state"]["request_id"]``, the ``X-Request-ID`` response header,
   and :data:`~app.utils.logger.REQUEST_ID_CTX_VAR` so every log line
   produced during the request lifecycle automatically carries the ID.

2. **Timing** -- measures wall-clock latency from first byte received to last
   byte sent and exposes it in the ``X-Response-Time`` response header.

3. **Access logging** -- emits one INFO line per completed request:
   ``METHOD /path -> STATUS | 123.4ms``.
   Health-probe paths (``/health``, ``/ready``) are intentionally excluded to
   prevent log spam from orchestrators that probe every few seconds.

4. **Security headers** -- adds defensive HTTP headers to every response.
   Individual route handlers can override specific values when semantically
   necessary via ``response.headers[key] = value`` *after* the response is
   built, but the middleware ensures defaults are always present.

   Headers applied:
   X-Content-Type-Options    : nosniff
   X-Frame-Options           : DENY
   X-XSS-Protection          : 1; mode=block
   Referrer-Policy           : strict-origin-when-cross-origin
   Cache-Control             : no-store
   Content-Security-Policy   : default-src 'none'; frame-ancestors 'none'
   Permissions-Policy        : geolocation=(), microphone=(), camera=()

Security notes
--------------
* ``X-Request-ID`` from the client is sanitised -- non-printable characters
  and control sequences are stripped -- to prevent **log injection**.  An
  attacker sending ``X-Request-ID: abc\\nFAKE log line`` would otherwise
  inject a fabricated record into every log line for that request.

* If sanitisation produces an empty string, a fresh UUID4 is generated
  instead, so requests are never untraceable.

* ``Strict-Transport-Security`` is intentionally absent here.  HSTS belongs
  in the TLS-terminating reverse proxy (nginx / Caddy / ALB), not in the
  application server, because it must only be set over HTTPS connections.

Implementation note -- pure ASGI
---------------------------------
Previous versions used ``BaseHTTPMiddleware`` which spawns a child
``anyio`` task for ``call_next``, breaking ``contextvars.ContextVar``
propagation, buffering the entire response in memory, and swallowing
``BackgroundTask`` objects.  This version uses raw ASGI ``__call__`` to
avoid those issues.

Log encoding note
-----------------
Access-log messages use ASCII-only arrows (``->``, ``<-``) instead of
Unicode arrows (U+2192, U+2190) to avoid ``UnicodeEncodeError`` on
Windows terminals running the ``cp1252`` code page.
"""

from __future__ import annotations

import logging
import re
import time
import uuid

from app.utils.logger import REQUEST_ID_CTX_VAR

logger = logging.getLogger(__name__)

# ── Header names ───────────────────────────────────────────────────────────

_REQUEST_ID_HEADER = b"x-request-id"
_REQUEST_ID_HEADER_NAME = b"X-Request-ID"
_RESPONSE_TIME_HEADER_NAME = b"X-Response-Time"

# ── Access log skip list ───────────────────────────────────────────────────
# Health probes are called every few seconds by load balancers and uptime
# monitors.  Logging each invocation at INFO level creates thousands of
# useless lines per day that obscure real application events and inflate log
# ingestion costs.

_NO_ACCESS_LOG: frozenset[str] = frozenset({"/health", "/ready"})

# ── Input sanitisation ─────────────────────────────────────────────────────
# Stricter than "strip control chars": only alphanumerics, hyphens,
# underscores, and dots are allowed.  Real UUIDs never contain spaces, pipes,
# or other log-format metacharacters.

_UNSAFE_REQUEST_ID_RE: re.Pattern[str] = re.compile(r"[^a-zA-Z0-9\-_.]")
_REQUEST_ID_MAX_LEN = 64  # cap to a sane length

# ── Security headers ───────────────────────────────────────────────────────
# Applied to every response.  Encoded to bytes once at import time to avoid
# re-encoding on every request.

_SECURITY_HEADERS: list[list[bytes]] = [
    [b"X-Content-Type-Options", b"nosniff"],
    [b"X-Frame-Options", b"DENY"],
    [b"X-XSS-Protection", b"1; mode=block"],
    [b"Referrer-Policy", b"strict-origin-when-cross-origin"],
    [b"Cache-Control", b"no-store"],
    [b"Content-Security-Policy", b"default-src 'none'; frame-ancestors 'none'"],
    [b"Permissions-Policy", b"geolocation=(), microphone=(), camera=()"],
]


def _sanitise_request_id(raw: str) -> str:
    """
    Return a sanitised copy of *raw* suitable for logging and headers.

    Strips any character that isn't alphanumeric, hyphen, underscore, or dot,
    and truncates to ``_REQUEST_ID_MAX_LEN`` characters.  If the result is
    empty (all characters were stripped), returns an empty string so the
    caller can fall back to a generated UUID.

    Args:
        raw: The raw value from the ``X-Request-ID`` header.

    Returns:
        A safe string, or empty string if nothing survived sanitisation.
    """
    truncated = raw[:128]
    sanitised = _UNSAFE_REQUEST_ID_RE.sub("", truncated)
    return sanitised[:_REQUEST_ID_MAX_LEN]


class RequestIDMiddleware:
    """
    Per-request correlation ID, timing, access logging, and security headers.

    If the inbound request already carries an ``X-Request-ID`` header its
    value is **sanitised** then reused -- this supports end-to-end tracing
    through an API gateway or load balancer.  Otherwise a fresh UUID4 is
    generated.  If sanitisation strips all characters, a fresh UUID4 is
    also generated.

    This is a pure ASGI middleware (no ``BaseHTTPMiddleware``).
    """

    def __init__(self, app) -> None:  # type: ignore[type-arg]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[type-arg]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ── Correlation ID ─────────────────────────────────────────────────
        raw_id = ""
        for header_name, header_value in scope.get("headers", []):
            if header_name == _REQUEST_ID_HEADER:
                raw_id = header_value[:128].decode("latin-1", errors="replace")
                break

        if raw_id:
            request_id = _sanitise_request_id(raw_id)
            # If sanitisation yielded an empty string, generate a new UUID.
            if not request_id:
                request_id = str(uuid.uuid4())
        else:
            request_id = str(uuid.uuid4())

        # Propagate to scope state for route handlers
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # Propagate to ContextVar for log filter
        token = REQUEST_ID_CTX_VAR.set(request_id)

        path = scope.get("path", "?")
        method = scope.get("method", "?")
        start = time.monotonic()

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                elapsed_ms = (time.monotonic() - start) * 1000

                # Collect existing header names for setdefault behavior
                headers = list(message.get("headers", []))
                existing_names = {h[0].lower() for h in headers}

                # Add correlation and timing headers
                headers.append(
                    [_REQUEST_ID_HEADER_NAME, request_id.encode("ascii")]
                )
                headers.append(
                    [
                        _RESPONSE_TIME_HEADER_NAME,
                        f"{elapsed_ms:.1f}ms".encode("ascii"),
                    ]
                )

                # Add security headers (setdefault: skip if already present)
                for header_pair in _SECURITY_HEADERS:
                    if header_pair[0].lower() not in existing_names:
                        headers.append(list(header_pair))

                message = {**message, "headers": headers}

                # Access log (health probes suppressed)
                status = message.get("status", 0)
                if path not in _NO_ACCESS_LOG:
                    logger.info(
                        "%s %s -> %d | %.1fms",
                        method,
                        path,
                        status,
                        elapsed_ms,
                    )

            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "%s %s -> unhandled exception | %.1fms",
                method,
                path,
                elapsed,
            )
            raise
        finally:
            # Always reset the ContextVar so subsequent uses of the same
            # thread do not inherit a stale ID.
            REQUEST_ID_CTX_VAR.reset(token)
