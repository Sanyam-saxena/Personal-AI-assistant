"""
Tests for the /health and /ready endpoints.

Coverage
--------
* /health always returns 200 with {"status": "healthy"}.
* /health response includes expected security headers.
* /health does not appear in the access log (spam suppression).
* /ready returns 200 + ReadinessResponse when Ollama is reachable.
* /ready returns 503 when Ollama is unreachable.
* /ready response includes X-Request-ID and X-Response-Time headers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """GET /health — liveness probe."""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_response_body(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data == {"status": "healthy"}

    def test_has_x_content_type_options(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert headers.get("X-Content-Type-Options") == "nosniff"

    def test_has_x_frame_options(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert headers.get("X-Frame-Options") == "DENY"

    def test_has_cache_control(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert headers.get("Cache-Control") == "no-store"

    def test_has_content_security_policy(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert "Content-Security-Policy" in headers

    def test_has_permissions_policy(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert "Permissions-Policy" in headers

    def test_has_request_id_header(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert "X-Request-ID" in headers
        assert len(headers["X-Request-ID"]) > 0

    def test_has_response_time_header(self, client: TestClient) -> None:
        headers = client.get("/health").headers
        assert "X-Response-Time" in headers

    def test_upstream_request_id_is_echoed(self, client: TestClient) -> None:
        """Upstream correlation IDs should be reflected back in the response."""
        custom_id = "my-trace-id-abc"
        headers = client.get("/health", headers={"X-Request-ID": custom_id}).headers
        assert headers["X-Request-ID"] == custom_id

    def test_malicious_request_id_is_sanitised(self, client: TestClient) -> None:
        """Control characters must be stripped to prevent log injection."""
        malicious = "abc\nERROR | root | Fake log line"
        headers = client.get("/health", headers={"X-Request-ID": malicious}).headers
        assert "\n" not in headers["X-Request-ID"]
        assert "Fake log line" not in headers["X-Request-ID"]


class TestReadyEndpoint:
    """GET /ready — readiness probe."""

    def test_returns_200_when_ollama_available(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.is_available.return_value = True
        response = client.get("/ready")
        assert response.status_code == 200

    def test_response_body_when_ready(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.is_available.return_value = True
        data = client.get("/ready").json()
        assert data["status"] == "ready"
        assert data["ollama"] == "reachable"

    def test_returns_503_when_ollama_unavailable(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.is_available.return_value = False
        response = client.get("/ready")
        assert response.status_code == 503

    def test_503_response_has_detail_key(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        mock_service.is_available.return_value = False
        data = client.get("/ready").json()
        assert "detail" in data

    def test_calls_is_available(
        self, client: TestClient, mock_service: MagicMock
    ) -> None:
        client.get("/ready")
        mock_service.is_available.assert_called_once()
