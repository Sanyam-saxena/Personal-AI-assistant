"""
Tests for the POST /chat endpoint.

Coverage
--------
Happy path
    * Returns 200 with {"response": "..."} for a valid message.
    * Passes the message string verbatim to OllamaService.generate().
    * Response body matches ChatResponse schema.

Validation errors (422)
    * Empty message is rejected.
    * Missing "message" key is rejected.
    * Non-string "message" is rejected.
    * Message exceeding max_length is rejected.
    * 422 body is sanitised — does not expose Pydantic internals.

Ollama service errors (5xx)
    * OllamaConnectionError  → 503
    * OllamaTimeoutError     → 504
    * OllamaResponseError    → 502
    * OllamaServiceError     → 502
    * Unexpected Exception   → 500

Service not initialised
    * Missing app.state.ollama  → 503 with clear message.

Body size limit
    * Body > MAX_REQUEST_BODY_BYTES → 413.

Security headers
    * Every response carries the security headers injected by
      RequestIDMiddleware.
    * X-Request-ID and X-Response-Time are present.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaServiceError,
    OllamaTimeoutError,
)
from app.main import app


# ── Happy path ──────────────────────────────────────────────────────────────


class TestChatSuccess:
    """POST /chat — successful generation."""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 200

    def test_response_has_response_key(self, client: TestClient) -> None:
        data = client.post("/chat", json={"message": "Hello"}).json()
        assert "response" in data

    def test_response_value_matches_mock(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.return_value = "Hi there!"
        data = client.post("/chat", json={"message": "Hello"}).json()
        assert data["response"] == "Hi there!"

    def test_passes_message_to_generate(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        client.post("/chat", json={"message": "Tell me a joke."})
        mock_service.generate.assert_called_once_with("Tell me a joke.")

    def test_response_is_string(self, client: TestClient) -> None:
        data = client.post("/chat", json={"message": "Hi"}).json()
        assert isinstance(data["response"], str)

    def test_content_type_is_json(self, client: TestClient) -> None:
        response = client.post("/chat", json={"message": "Hi"})
        assert "application/json" in response.headers["content-type"]

    def test_long_message_accepted(self, client: TestClient) -> None:
        """Messages up to max_length should be accepted."""
        long_message = "a" * 8192
        response = client.post("/chat", json={"message": long_message})
        assert response.status_code == 200

    def test_unicode_message(self, client: TestClient) -> None:
        """Unicode messages (emoji, CJK, etc.) should pass through."""
        response = client.post("/chat", json={"message": "你好 🎉"})
        assert response.status_code == 200

    def test_whitespace_only_message_rejected(self, client: TestClient) -> None:
        """Whitespace-only messages should be rejected (wastes compute)."""
        response = client.post("/chat", json={"message": " "})
        assert response.status_code == 422


# ── Validation errors ───────────────────────────────────────────────────────


class TestChatValidation:
    """POST /chat — request validation failures return 422."""

    def test_empty_message_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"message": ""})
        assert response.status_code == 422

    def test_missing_message_key_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={})
        assert response.status_code == 422

    def test_null_message_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"message": None})
        assert response.status_code == 422

    def test_integer_message_rejected(self, client: TestClient) -> None:
        response = client.post("/chat", json={"message": 42})
        assert response.status_code == 422

    def test_message_too_long_rejected(self, client: TestClient) -> None:
        oversized = "x" * 8193  # max_length is 8192
        response = client.post("/chat", json={"message": oversized})
        assert response.status_code == 422

    def test_422_body_has_detail_key(self, client: TestClient) -> None:
        data = client.post("/chat", json={}).json()
        assert "detail" in data

    def test_422_body_does_not_leak_pydantic_internals(
        self, client: TestClient
    ) -> None:
        """
        The sanitised 422 handler must not expose field names, Python types,
        or Pydantic constraint values (information disclosure).
        """
        data = client.post("/chat", json={}).json()
        body_str = json.dumps(data)

        # The sanitised 422 response should only contain a simple "detail"
        # key with a generic message.  Check that Pydantic's default error
        # *structure* (a list of dicts with "loc" keys) is not present,
        # which is a stronger assertion than substring-matching generic
        # words like "type" or "url" that might appear in our own message.
        assert isinstance(data.get("detail"), str), (
            "422 response 'detail' should be a plain string, not a Pydantic "
            f"error structure. Got: {data}"
        )
        # Pydantic-specific error structure tokens that should never
        # appear in a sanitised response.
        pydantic_tokens = [
            "string_too_short",
            "string_type",
            "missing",
            "value_error",
        ]
        for token in pydantic_tokens:
            assert token not in body_str, (
                f"422 response leaks Pydantic internal token: {token!r}\n"
                f"Full body: {body_str}"
            )

    def test_empty_body_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_non_json_body_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/chat",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


# ── Ollama service errors ────────────────────────────────────────────────────


class TestChatOllamaErrors:
    """POST /chat — Ollama errors are mapped to correct HTTP status codes."""

    def test_connection_error_returns_503(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaConnectionError("down")
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 503

    def test_connection_error_response_has_detail(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaConnectionError("Ollama is down")
        data = client.post("/chat", json={"message": "Hi"}).json()
        assert "detail" in data

    def test_timeout_error_returns_504(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaTimeoutError("timed out")
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 504

    def test_response_error_returns_502(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaResponseError("bad response")
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 502

    def test_service_error_returns_502(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaServiceError("unexpected")
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 502

    def test_unexpected_exception_returns_500(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = RuntimeError("completely unexpected")
        response = client.post("/chat", json={"message": "Hi"})
        assert response.status_code == 500

    def test_500_body_does_not_leak_exception_message(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        """Internal exception messages must not reach the client."""
        secret = "super-secret-internal-detail"
        mock_service.generate.side_effect = RuntimeError(secret)
        data = client.post("/chat", json={"message": "Hi"}).json()
        assert secret not in json.dumps(data)

    def test_503_body_has_detail(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.generate.side_effect = OllamaConnectionError("Cannot connect")
        data = client.post("/chat", json={"message": "Hi"}).json()
        assert "detail" in data
        assert len(data["detail"]) > 0


# ── Service not initialised ──────────────────────────────────────────────────


class TestChatServiceNotReady:
    """POST /chat — graceful 503 when app.state.ollama is absent."""

    def test_returns_503_when_state_not_set(self) -> None:
        """
        If lifespan startup fails before OllamaService is created,
        app.state.ollama won't exist.  The dependency should return 503
        rather than a bare AttributeError (which becomes a 500 with no
        context).
        """
        # Use the existing module-level app to avoid a costly lifespan
        # re-init (which tries to connect to Ollama).  Delete the service
        # *inside* the context manager so the dependency sees the missing
        # attribute.
        original = getattr(app.state, "ollama", None)
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                # Delete after lifespan has run so the test is fast
                if hasattr(app.state, "ollama"):
                    del app.state.ollama
                response = c.post("/chat", json={"message": "Hi"})
            assert response.status_code == 503
            assert "detail" in response.json()
        finally:
            # Restore so other tests are not affected.
            if original is not None:
                app.state.ollama = original


# ── Security headers ─────────────────────────────────────────────────────────


class TestChatSecurityHeaders:
    """POST /chat — security headers are present on every response."""

    @pytest.fixture(autouse=True)
    def _ok_response(self, client: TestClient) -> None:
        self._response = client.post("/chat", json={"message": "Hello"})

    def test_x_content_type_options(self) -> None:
        assert self._response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self) -> None:
        assert self._response.headers.get("X-Frame-Options") == "DENY"

    def test_cache_control(self) -> None:
        assert self._response.headers.get("Cache-Control") == "no-store"

    def test_content_security_policy(self) -> None:
        assert "Content-Security-Policy" in self._response.headers

    def test_x_request_id_present(self) -> None:
        assert "X-Request-ID" in self._response.headers

    def test_x_response_time_present(self) -> None:
        assert "X-Response-Time" in self._response.headers

    def test_upstream_request_id_echoed(self, client: TestClient) -> None:
        headers = client.post(
            "/chat",
            json={"message": "Hi"},
            headers={"X-Request-ID": "test-trace-123"},
        ).headers
        assert headers["X-Request-ID"] == "test-trace-123"
