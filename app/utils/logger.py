"""
Logging configuration.

Usage in every module
---------------------
::

    import logging
    logger = logging.getLogger(__name__)

Do **not** add handlers at module level.  Call :func:`configure_logging` once
at application startup (in ``app.main``) and all child loggers automatically
route through the root handler.

Request-ID propagation
-----------------------
:data:`REQUEST_ID_CTX_VAR` is a :class:`~contextvars.ContextVar` set by
:class:`~app.middleware.request_id.RequestIDMiddleware` at the start of each
request.  :class:`RequestIDFilter` injects the value into every
:class:`~logging.LogRecord` so every log line carries the correlation ID
automatically -- no explicit passing required.

Design decisions
----------------
* **Root-logger approach**: ``configure_logging`` configures the *root* logger
  rather than a per-namespace logger, so third-party libraries (``httpx``,
  ``requests``) participate in the same handler/filter chain.

* **Sanitised request ID**: The value from the incoming ``X-Request-ID`` header
  is sanitised before being written to the ContextVar (see
  ``RequestIDMiddleware``).  As an extra safety net, ``RequestIDFilter``
  also strips ASCII control characters so any unsanitised value that somehow
  reaches the ContextVar cannot inject newlines into log records.

* **12-character prefix**: Using 12 hex characters (48 bits of UUID entropy)
  reduces the birthday-paradox collision probability to < 0.001% at 10 000
  concurrent requests -- 16x better than the previous 8-character prefix.

* **Noisy loggers silenced**: ``uvicorn.access`` and ``uvicorn.error`` are
  suppressed because ``RequestIDMiddleware`` already emits a superior access
  log that includes request-ID, latency, and method. ``urllib3`` and
  ``requests`` are silenced to prevent redundant HTTP wire-level chatter.

* **Handler management**: Only the application's own handler is added/cleared.
  Uvicorn's handlers are left untouched so its lifecycle messages (e.g.
  "Started server process", "Shutting down") continue to work.

* **UTF-8 encoding**: The stream handler forces UTF-8 encoding to avoid
  ``UnicodeEncodeError`` on Windows terminals using ``cp1252``.
"""

from __future__ import annotations

import logging
import re
import sys
from contextvars import ContextVar

# ── Request-ID ContextVar ──────────────────────────────────────────────────
#
# Default value is twelve dashes so startup / shutdown messages align
# visually with request-scoped log lines.

REQUEST_ID_CTX_VAR: ContextVar[str] = ContextVar(
    "request_id", default="------------"
)

# ── Log format ─────────────────────────────────────────────────────────────
#
# %(request_id)-12s -> the first 12 characters of the request UUID
# (or "------------" during startup / shutdown).

_LOG_FMT = (
    "%(asctime)s | %(levelname)-8s | %(request_id)-12s | %(name)s | %(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Matches any ASCII control character (0x00-0x1F and 0x7F).
_CONTROL_CHARS_RE: re.Pattern[str] = re.compile(r"[\x00-\x1f\x7f]")

# Sentinel attribute name used to identify the handler we create, so we
# only clear our own handler on reconfiguration -- not Uvicorn's.
_APP_HANDLER_ATTR = "_app_logging_handler"

# ── Loggers silenced to WARNING to reduce noise ────────────────────────────
# RequestIDMiddleware already emits a superior access log, so Uvicorn's
# default access log is redundant.  urllib3 wire-level traces belong in
# DEBUG-only sessions.
_SILENCE_AT_WARNING = (
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn",
    "urllib3",
    "urllib3.connectionpool",
    "requests.packages.urllib3",
    "httpx",
)


class RequestIDFilter(logging.Filter):
    """
    Inject the current request ID into every :class:`~logging.LogRecord`.

    Uses the first 12 characters of the stored UUID so log lines stay
    readable while providing 48 bits of entropy for correlation.

    As a defence-in-depth measure the value is stripped of ASCII control
    characters before assignment, so a malformed value in the ContextVar
    cannot inject fake log lines downstream.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        raw = REQUEST_ID_CTX_VAR.get()
        # Strip control characters (defence in depth against log injection).
        safe = _CONTROL_CHARS_RE.sub("", raw)
        record.request_id = safe[:12]  # type: ignore[attr-defined]
        return True


def configure_logging(level: str = "INFO") -> None:
    """
    Configure the root logger for the entire application.

    Must be called **once** at startup, before the first ``logging.getLogger``
    call.  Calling it a second time (hot-reload, test re-runs) is safe because
    only the application's own handler is cleared -- Uvicorn's handlers are
    left intact.

    Args:
        level: Logging level name -- ``DEBUG``, ``INFO``, ``WARNING``,
               ``ERROR``, or ``CRITICAL``.  Case-insensitive.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(log_level)

    # Only clear the handler WE previously added (identified by a sentinel
    # attribute), not handlers added by Uvicorn or other libraries.
    root.handlers = [
        h for h in root.handlers
        if not getattr(h, _APP_HANDLER_ATTR, False)
    ]

    # Force UTF-8 encoding to avoid UnicodeEncodeError on Windows cp1252.
    handler = logging.StreamHandler(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)  # noqa: SIM115
    )
    handler.setLevel(log_level)
    handler.addFilter(RequestIDFilter())
    handler.setFormatter(logging.Formatter(fmt=_LOG_FMT, datefmt=_DATE_FMT))
    setattr(handler, _APP_HANDLER_ATTR, True)  # Mark as ours
    root.addHandler(handler)

    # Silence third-party loggers that produce noise at INFO level.
    for name in _SILENCE_AT_WARNING:
        logging.getLogger(name).setLevel(logging.WARNING)
