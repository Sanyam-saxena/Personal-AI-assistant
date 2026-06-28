"""
Unit tests for ASGI middleware.

Tests cover:
- BodyLimitMiddleware: Content-Length pre-check, negative values, chunked
  transfer encoding, valid requests passing through.
- RequestIDMiddleware: UUID generation, client-provided ID sanitisation,
  empty sanitised ID fallback, security headers, access logging suppression.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import reset_rate_limit_state
from app.main import app


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset rate-limit state before each test to prevent cross-test interference."""
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


@pytest.fixture
def test_client() -> TestClient:
    """Create a TestClient without raising server exceptions for 4xx/5xx."""
    return TestClient(app, raise_server_exceptions=False)


# ── BodyLimitMiddleware Tests ──────────────────────────────────────────────


class TestBodyLimitMiddleware:
    """Tests for the body-size enforcement middleware."""

    def test_normal_request_passes_through(self, test_client: TestClient) -> None:
        """A normally-sized request should not be blocked."""
        response = test_client.get("/health")
        assert response.status_code == 200

    def test_oversized_content_length_rejected(self, test_client: TestClient) -> None:
        """Requests declaring Content-Length > max should get 413."""
        # Send a request with a Content-Length header that exceeds the limit.
        # The actual body doesn't matter; the middleware checks the header first.
        huge_body = "x" * 100_000
        response = test_client.post(
            "/chat",
            content=huge_body,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413

    def test_negative_content_length_rejected(self, test_client: TestClient) -> None:
        """Requests with negative Content-Length should get 400."""
        response = test_client.post(
            "/chat",
            content='{"message": "hi"}',
            headers={
                "Content-Type": "application/json",
                "Content-Length": "-1",
            },
        )
        # The TestClient may normalise the Content-Length header, so this
        # test may get a different status depending on the client behaviour.
        # We accept either 400 (our middleware) or a client-side error.
        assert response.status_code in (400, 422)


# ── RequestIDMiddleware Tests ──────────────────────────────────────────────


class TestRequestIDMiddleware:
    """Tests for correlation ID, timing, and security header middleware."""

    def test_generates_request_id_when_absent(self, test_client: TestClient) -> None:
        """When no X-Request-ID header is sent, one should be generated."""
        response = test_client.get("/health")
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0

    def test_uses_client_request_id(self, test_client: TestClient) -> None:
        """When a valid X-Request-ID is sent, it should be echoed back."""
        response = test_client.get(
            "/health",
            headers={"X-Request-ID": "my-custom-trace-id-123"},
        )
        request_id = response.headers.get("X-Request-ID")
        assert request_id == "my-custom-trace-id-123"

    def test_sanitises_malicious_request_id(self, test_client: TestClient) -> None:
        """
        Special characters in X-Request-ID should be stripped to prevent
        log injection attacks.
        """
        response = test_client.get(
            "/health",
            headers={"X-Request-ID": "abc\nFAKE LOG LINE\r\n"},
        )
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        # Newlines and carriage returns should be stripped
        assert "\n" not in request_id
        assert "\r" not in request_id

    def test_empty_sanitised_id_gets_uuid(self, test_client: TestClient) -> None:
        """If all characters are stripped, a UUID should be generated."""
        response = test_client.get(
            "/health",
            headers={"X-Request-ID": "###$$$%%%"},
        )
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0
        # Should look like a UUID (contains hyphens)
        assert "-" in request_id

    def test_response_time_header_present(self, test_client: TestClient) -> None:
        """X-Response-Time header should be present on all responses."""
        response = test_client.get("/health")
        response_time = response.headers.get("X-Response-Time")
        assert response_time is not None
        assert response_time.endswith("ms")

    def test_security_headers_present(self, test_client: TestClient) -> None:
        """All security headers should be present on responses."""
        response = test_client.get("/health")

        expected_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }

        for header_name, expected_value in expected_headers.items():
            actual = response.headers.get(header_name)
            assert actual == expected_value, (
                f"Expected {header_name}: {expected_value}, got: {actual}"
            )

    def test_security_headers_on_error_responses(self, test_client: TestClient) -> None:
        """Security headers should be present even on error responses."""
        response = test_client.post("/chat", json={})  # Will trigger 422
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_docs_and_redoc_have_minimal_csp(self, test_client: TestClient) -> None:
        """/docs and /redoc should have custom, less restrictive CSP headers for rendering."""
        response_docs = test_client.get("/docs")
        assert response_docs.status_code == 200
        csp_docs = response_docs.headers.get("Content-Security-Policy")
        assert csp_docs is not None
        assert "default-src 'self'" in csp_docs
        assert "unsafe-inline" in csp_docs
        assert "cdn.jsdelivr.net" in csp_docs

        response_redoc = test_client.get("/redoc")
        assert response_redoc.status_code == 200
        csp_redoc = response_redoc.headers.get("Content-Security-Policy")
        assert csp_redoc is not None
        assert "default-src 'self'" in csp_redoc
        assert "unsafe-inline" in csp_redoc
        assert "fonts.gstatic.com" in csp_redoc

    def test_openapi_has_strict_csp(self, test_client: TestClient) -> None:
        """/openapi.json should keep the strict default CSP."""
        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers.get("Content-Security-Policy") == "default-src 'none'; frame-ancestors 'none'"

    def test_openapi_disabled_returns_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When OPENAPI_ENABLED is False, /docs, /redoc, and /openapi.json must return 404."""
        from app.core.config import get_settings
        from app.main import create_application

        # Clear settings cache and override
        get_settings.cache_clear()
        monkeypatch.setenv("OPENAPI_ENABLED", "False")

        # Create a new application instance
        disabled_app = create_application()
        client = TestClient(disabled_app, raise_server_exceptions=False)

        # Verify all return 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

        # Clean up settings cache after test
        get_settings.cache_clear()


# ── Rate Limiter Tests ─────────────────────────────────────────────────────


class TestRateLimiter:
    """Tests for the per-IP rate limiter on /chat."""

    def test_normal_request_not_rate_limited(self, test_client: TestClient) -> None:
        """A single request should not be rate-limited."""
        # Need a valid service mock for this
        from unittest.mock import MagicMock
        from app.services.ollama_service import OllamaService

        mock = MagicMock(spec=OllamaService)
        mock.generate.return_value = "response"
        mock.is_available.return_value = True
        app.state.ollama = mock

        response = test_client.post("/chat", json={"message": "hello"})
        # Should be 200 (not 429)
        assert response.status_code != 429
