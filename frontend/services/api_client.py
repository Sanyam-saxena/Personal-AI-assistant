"""
API client for interacting with the FastAPI backend.
"""

from __future__ import annotations

import logging
import os

import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors."""


class APIConnectionError(APIError):
    """Raised when connection to backend fails."""


class APITimeoutError(APIError):
    """Raised when the backend request times out."""


class APIResponseError(APIError):
    """Raised when backend returns an unexpected status or malformed response."""


def validate_backend_url(url: str) -> str:
    """
    Validate that the URL is a valid http/https URL and prevent private IPs in production.
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme. Must be http or https.")
    if not parsed.netloc:
        raise ValueError("Invalid URL: missing network location.")
    
    # Warning for non-standard ports
    if parsed.port and parsed.port not in (80, 443, 8000, 8501):
        logger.warning("APIClient using non-standard port: %d", parsed.port)

    # Disallow loopback/private IPs in production environment to prevent SSRF
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        host = parsed.hostname
        if host:
            is_loopback = (
                host == "localhost" or
                host.startswith("127.") or
                host == "::1"
            )
            is_private = False
            # Check for RFC 1918 private subnets
            parts = host.split(".")
            if len(parts) == 4:
                try:
                    p1, p2 = int(parts[0]), int(parts[1])
                    if p1 == 10:
                        is_private = True
                    elif p1 == 192 and p2 == 168:
                        is_private = True
                    elif p1 == 172 and (16 <= p2 <= 31):
                        is_private = True
                except ValueError:
                    pass
            if is_loopback or is_private:
                raise ValueError(
                    f"SSRF Prevention: Direct connections to private or loopback IPs ({host}) "
                    "are disallowed when ENVIRONMENT=production."
                )
    return url


class APIClient:
    """
    Client for communicating with the FastAPI backend proxy.

    Configurable via the ``BACKEND_URL`` environment variable.
    """

    def __init__(self, base_url: str | None = None) -> None:
        # Load backend URL from env, falling back to localhost:8000
        env_url = os.environ.get("BACKEND_URL")
        raw_url = base_url or env_url or "http://localhost:8000"
        try:
            validated_url = validate_backend_url(raw_url)
        except ValueError as exc:
            logger.error("Invalid BACKEND_URL configured: %s", exc)
            raise ValueError(f"Invalid BACKEND_URL: {exc}") from exc
        self.base_url = validated_url.rstrip("/")
        self._session = self._build_session()
        logger.info("APIClient initialized | base_url=%s", self.base_url)

    @staticmethod
    def _build_session() -> requests.Session:
        """
        Builds a requests.Session with connection pooling and retry policies.

        Retries are limited to **idempotent methods** (GET, HEAD) only.
        POST requests are never retried because ``/chat`` is not idempotent
        -- retrying would cause duplicate Ollama generations.
        """
        session = requests.Session()
        # Setup retry strategy for transient errors.
        # IMPORTANT: Only retry idempotent methods to avoid duplicate
        # Ollama generations on POST /chat.
        retry_strategy = Retry(
            total=3,  # 3 retries max
            backoff_factor=1,  # 1s, 2s, 4s delay between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,  # Let raise_for_status() handle status raises
        )
        adapter = HTTPAdapter(
            pool_connections=2,
            pool_maxsize=10,
            max_retries=retry_strategy,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def check_health(self) -> bool:
        """
        Checks the backend liveness endpoint.

        Returns:
            True if healthy, False otherwise.
        """
        url = f"{self.base_url}/health"
        try:
            # Short timeout for health check
            response = self._session.get(url, timeout=3.0)
            if response.status_code == 200:
                data = response.json()
                return data.get("status") == "healthy"
            logger.warning(
                "Health check returned non-200 status | status=%d",
                response.status_code,
            )
            return False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            logger.debug("Health check failed | error=%s", exc)
            return False
        except Exception as exc:
            logger.warning("Unexpected error during health check | error=%s", exc)
            return False

    def send_chat(self, message: str) -> str:
        """
        Sends a message to the backend chat endpoint and returns the reply.

        Args:
            message: User prompt to send.

        Returns:
            The AI response string.

        Raises:
            APIConnectionError: If the backend is unreachable.
            APITimeoutError: If the backend fails to respond within the timeout.
            APIResponseError: If validation fails or a status code indicates an error.
        """
        url = f"{self.base_url}/chat"
        payload = {"message": message}

        logger.debug("Sending prompt to backend | message_len=%d chars", len(message))

        # Bind `resp` to None so the except blocks can safely check it.
        resp: requests.Response | None = None

        try:
            # 70-second timeout (10s connect, 60s read to match backend defaults)
            # Note: json= auto-sets Content-Type, no manual header needed.
            resp = self._session.post(
                url,
                json=payload,
                timeout=(10.0, 70.0),
            )

            # Check for specific error status codes before raise_for_status
            if resp.status_code == 413:
                raise APIResponseError("Message is too large.")
            if resp.status_code == 422:
                raise APIResponseError("Message validation failed on server.")

            resp.raise_for_status()

        except (APIConnectionError, APITimeoutError, APIResponseError):
            # Re-raise our own exceptions without wrapping.
            raise

        except requests.exceptions.ConnectionError as exc:
            logger.error("Connection failed | url=%s", url)
            raise APIConnectionError(
                "Failed to connect to the backend server. Is it running?"
            ) from exc

        except requests.exceptions.Timeout as exc:
            logger.error("Request timed out | url=%s", url)
            raise APITimeoutError(
                "Request timed out. The backend model is taking too long to generate."
            ) from exc

        except requests.exceptions.HTTPError as exc:
            status_code = resp.status_code if resp is not None else 0
            err_detail = "Unknown error"
            if resp is not None:
                try:
                    err_detail = resp.json().get("detail", "Unknown error")
                except ValueError:
                    err_detail = resp.text[:200]
            logger.error(
                "HTTP error occurred | status=%d | detail=%s",
                status_code,
                err_detail,
            )
            raise APIResponseError(
                f"Server error ({status_code}): {err_detail}"
            ) from exc

        # Process and validate response payload
        try:
            data = resp.json()
        except ValueError as exc:
            logger.error(
                "Non-JSON response from backend | text=%.200s",
                resp.text[:200],
            )
            raise APIResponseError(
                "Received a malformed non-JSON reply from backend."
            ) from exc

        ai_response = data.get("response")
        if not isinstance(ai_response, str):
            logger.error("Invalid response schema | data=%s", data)
            raise APIResponseError(
                "Backend response schema mismatch. Missing 'response' key."
            )

        return ai_response
