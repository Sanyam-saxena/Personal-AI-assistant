"""
Request body size limit middleware (pure ASGI).

Problem addressed
-----------------
FastAPI's Pydantic validation runs *after* the full request body has been read
into memory.  Without an upstream guard, a client can send a multi-megabyte
(or multi-gigabyte) body that exhausts heap memory and crashes the server —
or simply occupies a thread for long enough to deny service to other clients.

This middleware enforces size limits at the **ASGI layer** — before any
framework code touches the body.

Two enforcement mechanisms
--------------------------
1. **Content-Length pre-check**  If the ``Content-Length`` header is present
   its value is validated (must be a non-negative integer ≤ ``max_bytes``).
   Invalid or oversized values are rejected immediately with a ``400`` or
   ``413`` response.

2. **Streaming byte-count guard**  For *all* requests (including
   ``Transfer-Encoding: chunked`` which omit ``Content-Length``), the
   middleware wraps the ASGI ``receive`` callable to count bytes as they
   arrive.  If the running total exceeds ``max_bytes`` the next
   ``http.request`` message returns an empty body with
   ``more_body=False``, causing the framework to see a truncated body and
   reject it during Pydantic parsing.  The response is then a ``413``
   injected directly by the middleware.

Implementation note — pure ASGI
--------------------------------
Previous versions used ``BaseHTTPMiddleware`` which spawns a child
``anyio`` task for ``call_next``, breaking ``contextvars.ContextVar``
propagation and buffering the entire response in memory.  This version
uses raw ASGI ``__call__`` to avoid those issues.

Registration order
------------------
Register **before** ``CORSMiddleware`` (closer to the application) so
oversized bodies are rejected before CORS headers are set.  In Starlette
the last ``add_middleware`` call becomes the outermost wrapper.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class BodyLimitMiddleware:
    """
    Reject requests whose body exceeds *max_bytes*.

    Enforces limits via both ``Content-Length`` pre-check and streaming
    byte counting, so ``Transfer-Encoding: chunked`` requests are also
    covered.

    Args:
        app:       The ASGI application to wrap.
        max_bytes: Maximum allowed body size in bytes.
    """

    def __init__(self, app, max_bytes: int) -> None:  # type: ignore[type-arg]
        self.app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[type-arg]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ── Content-Length pre-check ───────────────────────────────────────
        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")

        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except (ValueError, UnicodeDecodeError):
                path = scope.get("path", "?")
                logger.warning(
                    "Rejected request with non-integer Content-Length | "
                    "value=%r | path=%s",
                    content_length_raw,
                    path,
                )
                await self._send_json(
                    send,
                    status=400,
                    body={"detail": "Invalid Content-Length header."},
                )
                return

            if content_length < 0:
                path = scope.get("path", "?")
                logger.warning(
                    "Rejected request with negative Content-Length | "
                    "value=%d | path=%s",
                    content_length,
                    path,
                )
                await self._send_json(
                    send,
                    status=400,
                    body={"detail": "Invalid Content-Length header."},
                )
                return

            if content_length > self._max_bytes:
                path = scope.get("path", "?")
                logger.warning(
                    "Rejected oversized request | "
                    "content_length=%d | max=%d | path=%s",
                    content_length,
                    self._max_bytes,
                    path,
                )
                await self._send_json(
                    send,
                    status=413,
                    body={
                        "detail": (
                            f"Request body too large. "
                            f"Maximum allowed size is {self._max_bytes:,} bytes."
                        )
                    },
                )
                return

        # ── Streaming byte-count guard ────────────────────────────────────
        # Wraps the ASGI receive callable to count bytes as they arrive.
        # This catches chunked-encoded bodies that omit Content-Length.
        bytes_received = 0
        exceeded = False

        async def guarded_receive():
            nonlocal bytes_received, exceeded

            message = await receive()

            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                bytes_received += len(chunk)

                if bytes_received > self._max_bytes:
                    exceeded = True
                    # Return empty body to the downstream app.  The
                    # app will see a truncated/empty body and fail
                    # validation, but we intercept the response below.
                    return {
                        "type": "http.request",
                        "body": b"",
                        "more_body": False,
                    }

            return message

        # Track whether we've started sending the response or injected our own
        response_started = False
        injected = False

        async def guarded_send(message):
            nonlocal response_started, injected

            if injected:
                return

            if exceeded and not response_started:
                # The downstream app tried to send a response, but the
                # body was truncated.  Send our 413 instead.
                injected = True
                response_started = True
                path = scope.get("path", "?")
                logger.warning(
                    "Rejected oversized chunked request | "
                    "bytes_received=%d | max=%d | path=%s",
                    bytes_received,
                    self._max_bytes,
                    path,
                )
                await self._send_json(
                    send,
                    status=413,
                    body={
                        "detail": (
                            f"Request body too large. "
                            f"Maximum allowed size is {self._max_bytes:,} bytes."
                        )
                    },
                )
                return

            response_started = message.get("type") == "http.response.start"
            await send(message)

        await self.app(scope, guarded_receive, guarded_send)

    @staticmethod
    async def _send_json(send, *, status: int, body: dict) -> None:  # type: ignore[type-arg]
        """Send a complete JSON response via raw ASGI send."""
        payload = json.dumps(body).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(payload)).encode("ascii")],
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
            }
        )
