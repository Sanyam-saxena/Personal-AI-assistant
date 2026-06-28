"""
Unit tests for the frontend API client.

Tests cover:
- APIClient instantiation (URL from env, fallback, explicit)
- send_chat happy path
- Connection errors -> APIConnectionError
- Timeout errors -> APITimeoutError
- HTTP error responses -> APIResponseError
- Malformed JSON responses
- Health check happy and failure paths
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

# Adjust path so frontend packages are importable
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend.services.api_client import (
    APIClient,
    APIConnectionError,
    APIResponseError,
    APITimeoutError,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    raise_for_status_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text or ""

    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("No JSON")

    if raise_for_status_effect:
        resp.raise_for_status.side_effect = raise_for_status_effect
    else:
        resp.raise_for_status.return_value = None

    return resp


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAPIClientInit:
    """Tests for APIClient initialisation."""

    def test_default_url(self) -> None:
        """Should default to localhost:8000."""
        with patch.dict(os.environ, {}, clear=True):
            client = APIClient()
            assert "localhost:8000" in client.base_url

    def test_url_from_env(self) -> None:
        """Should use BACKEND_URL env var."""
        with patch.dict(os.environ, {"BACKEND_URL": "http://custom:9000"}):
            client = APIClient()
            assert client.base_url == "http://custom:9000"

    def test_explicit_url(self) -> None:
        """Explicit URL overrides env var."""
        with patch.dict(os.environ, {"BACKEND_URL": "http://env:9000"}):
            client = APIClient(base_url="http://explicit:7000")
            assert client.base_url == "http://explicit:7000"

    def test_trailing_slash_stripped(self) -> None:
        """Trailing slashes should be stripped."""
        client = APIClient(base_url="http://localhost:8000/")
        assert client.base_url == "http://localhost:8000"

    def test_invalid_scheme_raises_value_error(self) -> None:
        """Should reject URLs with non-http/https schemes."""
        with pytest.raises(ValueError, match="scheme"):
            APIClient(base_url="ftp://localhost:8000")

    def test_missing_netloc_raises_value_error(self) -> None:
        """Should reject URLs missing host/domain."""
        with pytest.raises(ValueError, match="missing network location"):
            APIClient(base_url="http://")

    def test_ssrf_protection_in_production(self) -> None:
        """Should disallow private/loopback IPs when ENVIRONMENT=production."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(ValueError, match="SSRF Prevention"):
                APIClient(base_url="http://localhost:8000")
            with pytest.raises(ValueError, match="SSRF Prevention"):
                APIClient(base_url="http://127.0.0.1:8000")
            with pytest.raises(ValueError, match="SSRF Prevention"):
                APIClient(base_url="http://192.168.1.5:8000")
            with pytest.raises(ValueError, match="SSRF Prevention"):
                APIClient(base_url="http://10.0.0.1:8000")
            with pytest.raises(ValueError, match="SSRF Prevention"):
                APIClient(base_url="http://172.16.5.10:8000")

            # Public IP allowed in production
            client = APIClient(base_url="https://api.myjarvis.com")
            assert client.base_url == "https://api.myjarvis.com"


class TestSendChat:
    """Tests for APIClient.send_chat()."""

    def test_successful_chat(self) -> None:
        """Happy path: send_chat returns the AI response string."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(json_data={"response": "Hello from AI"})

        with patch.object(client._session, "post", return_value=mock_resp):
            result = client.send_chat("Hello")
            assert result == "Hello from AI"

    def test_connection_error(self) -> None:
        """ConnectionError should raise APIConnectionError."""
        client = APIClient(base_url="http://test:8000")

        with patch.object(
            client._session,
            "post",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            with pytest.raises(APIConnectionError):
                client.send_chat("hello")

    def test_timeout_error(self) -> None:
        """Timeout should raise APITimeoutError."""
        client = APIClient(base_url="http://test:8000")

        with patch.object(
            client._session,
            "post",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            with pytest.raises(APITimeoutError):
                client.send_chat("hello")

    def test_413_raises_response_error(self) -> None:
        """413 should raise APIResponseError about message size."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(status_code=413)

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(APIResponseError, match="too large"):
                client.send_chat("hello")

    def test_422_raises_response_error(self) -> None:
        """422 should raise APIResponseError about validation."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(status_code=422)

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(APIResponseError, match="validation"):
                client.send_chat("hello")

    def test_malformed_json_raises_response_error(self) -> None:
        """Non-JSON response should raise APIResponseError."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("Expecting value")
        mock_resp.text = "not json"

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(APIResponseError, match="malformed"):
                client.send_chat("hello")

    def test_missing_response_key_raises_error(self) -> None:
        """JSON without 'response' key should raise APIResponseError."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(json_data={"wrong_key": "value"})

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(APIResponseError, match="schema"):
                client.send_chat("hello")


class TestCheckHealth:
    """Tests for APIClient.check_health()."""

    def test_healthy_backend(self) -> None:
        """Returns True when backend responds 200 with status=healthy."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(json_data={"status": "healthy"})

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.check_health() is True

    def test_unhealthy_status(self) -> None:
        """Returns False when backend responds 200 but status != healthy."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(json_data={"status": "degraded"})

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.check_health() is False

    def test_non_200_status(self) -> None:
        """Returns False when backend responds with non-200."""
        client = APIClient(base_url="http://test:8000")
        mock_resp = _mock_response(status_code=500)
        mock_resp.json.return_value = {}

        with patch.object(client._session, "get", return_value=mock_resp):
            assert client.check_health() is False

    def test_connection_error(self) -> None:
        """Returns False when backend is unreachable."""
        client = APIClient(base_url="http://test:8000")

        with patch.object(
            client._session,
            "get",
            side_effect=requests.exceptions.ConnectionError("refused"),
        ):
            assert client.check_health() is False

    def test_timeout(self) -> None:
        """Returns False when health check times out."""
        client = APIClient(base_url="http://test:8000")

        with patch.object(
            client._session,
            "get",
            side_effect=requests.exceptions.Timeout("timed out"),
        ):
            assert client.check_health() is False
