"""
In-memory rate limiter for API endpoints.

Implements a simple sliding-window counter per client IP address.
Designed for single-instance deployments.  For multi-instance deployments,
use a shared store like Redis instead.

Usage in route dependencies::

    from app.core.rate_limit import rate_limit_dependency

    @router.post("/chat", dependencies=[Depends(rate_limit_dependency)])
    def chat(...):
        ...
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────

# Maximum requests per window per client IP.
_MAX_REQUESTS: int = 20

# Window duration in seconds.
_WINDOW_SECONDS: int = 60

# ── State ──────────────────────────────────────────────────────────────────

# Thread-safe: FastAPI dispatches sync handlers to a thread pool.
_lock = Lock()
_request_log: dict[str, list[float]] = defaultdict(list)
_last_cleanup_time: float = 0.0
_CLEANUP_INTERVAL: float = 10.0
_MAX_LIMITER_IP_KEYS: int = 10000


def reset_rate_limit_state() -> None:
    """
    Clear all rate-limit state.

    Intended for use in test fixtures only.  In production, state
    naturally expires via the sliding window.
    """
    global _last_cleanup_time
    with _lock:
        _request_log.clear()
        _last_cleanup_time = 0.0


def _get_client_ip(request: Request) -> str:
    """
    Extract the client IP from the request.

    Uses ``X-Forwarded-For`` ONLY if the direct connection is from a trusted proxy
    configured in ``TRUSTED_PROXIES``.  Otherwise, falls back to ``request.client.host``.
    """
    from app.core.config import get_settings
    settings = get_settings()

    client_host = request.client.host if request.client else "unknown"

    trusted_proxies = settings.parsed_trusted_proxies
    if not trusted_proxies:
        return client_host

    if client_host in trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For: client, proxy1, proxy2
            return forwarded.split(",")[0].strip()

    return client_host


def _is_rate_limited(client_ip: str) -> bool:
    """
    Check whether *client_ip* has exceeded the rate limit.

    Evicts timestamps older than the current window before counting.
    Returns ``True`` if the client is rate-limited.
    """
    global _last_cleanup_time
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        # Perform global cleanup if interval elapsed or dict is too large
        if now - _last_cleanup_time > _CLEANUP_INTERVAL or len(_request_log) >= _MAX_LIMITER_IP_KEYS:
            to_delete = []
            for ip, ts in _request_log.items():
                active_ts = [t for t in ts if t > cutoff]
                if not active_ts:
                    to_delete.append(ip)
                else:
                    _request_log[ip] = active_ts
            for ip in to_delete:
                del _request_log[ip]
            _last_cleanup_time = now

        timestamps = _request_log[client_ip]
        # Evict expired entries for this IP
        active_ts = [t for t in timestamps if t > cutoff]

        if len(active_ts) >= _MAX_REQUESTS:
            _request_log[client_ip] = active_ts
            return True

        active_ts.append(now)
        _request_log[client_ip] = active_ts
        return False


def rate_limit_dependency(request: Request) -> None:
    """
    FastAPI dependency that enforces per-IP rate limiting.

    Raises HTTP 429 if the client has exceeded the allowed number of
    requests within the sliding window.

    Usage::

        @router.post("/chat", dependencies=[Depends(rate_limit_dependency)])
    """
    client_ip = _get_client_ip(request)

    if _is_rate_limited(client_ip):
        logger.warning(
            "Rate limit exceeded | client=%s | max=%d/%ds",
            client_ip,
            _MAX_REQUESTS,
            _WINDOW_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded. Maximum {_MAX_REQUESTS} requests "
                f"per {_WINDOW_SECONDS} seconds."
            ),
        )
