"""
Unit tests for OllamaService.

These tests mock ``requests.Session`` to verify the service layer's behaviour
without making real HTTP calls.  Each test focuses on a single concern:

- Happy-path generation
- Connection failures -> OllamaConnectionError
- Timeout failures -> OllamaTimeoutError
- HTTP errors -> OllamaResponseError
- Malformed JSON -> OllamaResponseError
- Schema mismatch -> OllamaResponseError
- Health probe (is_available) happy and failure paths
- System prompt prepending
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    HTTPError,
    Timeout,
)

from app.core.config import Settings
from app.core.exceptions import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaServiceError,
    OllamaTimeoutError,
)
from app.services.ollama_service import OllamaService


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with sensible defaults for tests."""
    defaults = {
        "OLLAMA_URL": "http://localhost:11434",
        "OLLAMA_MODEL": "test-model",
        "OLLAMA_CONNECT_TIMEOUT": 5,
        "OLLAMA_READ_TIMEOUT": 30,
        "SYSTEM_PROMPT": "You are a test assistant.",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    raise_for_status_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text or json.dumps(json_data or {})

    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("No JSON")

    if raise_for_status_effect:
        resp.raise_for_status.side_effect = raise_for_status_effect
    else:
        resp.raise_for_status.return_value = None

    return resp


# ── Test classes ────────────────────────────────────────────────────────────


class TestOllamaServiceGenerate:
    """Tests for OllamaService.generate()."""

    def test_successful_generation(self) -> None:
        """Happy path: generate returns the model response text."""
        session = MagicMock(spec=requests.Session)
        session.post.return_value = _mock_response(
            json_data={
                "model": "test-model",
                "response": "Hello from AI",
                "done": True,
            }
        )

        settings = _make_settings()
        service = OllamaService(settings=settings, session=session)
        result = service.generate("Say hello")

        assert result == "Hello from AI"
        session.post.assert_called_once()

    def test_system_prompt_prepended(self) -> None:
        """The system prompt should be prepended to the user prompt."""
        session = MagicMock(spec=requests.Session)
        session.post.return_value = _mock_response(
            json_data={
                "model": "test-model",
                "response": "Answer",
                "done": True,
            }
        )

        settings = _make_settings(SYSTEM_PROMPT="Be concise.")
        service = OllamaService(settings=settings, session=session)
        service.generate("What is 2+2?")

        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["prompt"].startswith("Be concise.")
        assert "What is 2+2?" in payload["prompt"]

    def test_empty_system_prompt_uses_raw_prompt(self) -> None:
        """When system prompt is empty, the raw user prompt is sent directly."""
        session = MagicMock(spec=requests.Session)
        session.post.return_value = _mock_response(
            json_data={
                "model": "test-model",
                "response": "Answer",
                "done": True,
            }
        )

        settings = _make_settings(SYSTEM_PROMPT="")
        service = OllamaService(settings=settings, session=session)
        service.generate("raw question")

        call_args = session.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert payload["prompt"] == "raw question"

    def test_connection_error_raises_domain_exception(self) -> None:
        """ConnectionError should map to OllamaConnectionError."""
        session = MagicMock(spec=requests.Session)
        session.post.side_effect = RequestsConnectionError("Connection refused")

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaConnectionError):
            service.generate("hello")

    def test_timeout_error_raises_domain_exception(self) -> None:
        """Timeout should map to OllamaTimeoutError."""
        session = MagicMock(spec=requests.Session)
        session.post.side_effect = Timeout("Read timed out")

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaTimeoutError):
            service.generate("hello")

    def test_http_404_raises_response_error(self) -> None:
        """404 (model not found) should map to OllamaResponseError."""
        session = MagicMock(spec=requests.Session)
        mock_resp = _mock_response(status_code=404, text="model not found")
        http_err = HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_err
        session.post.return_value = mock_resp

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaResponseError, match="model was not found"):
            service.generate("hello")

    def test_http_500_raises_response_error(self) -> None:
        """500 from Ollama should map to OllamaResponseError."""
        session = MagicMock(spec=requests.Session)
        mock_resp = _mock_response(status_code=500, text="internal error")
        http_err = HTTPError(response=mock_resp)
        mock_resp.raise_for_status.side_effect = http_err
        session.post.return_value = mock_resp

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaResponseError, match="HTTP error response"):
            service.generate("hello")

    def test_invalid_json_raises_response_error(self) -> None:
        """Non-JSON response from Ollama should raise OllamaResponseError."""
        session = MagicMock(spec=requests.Session)
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("Expecting value")
        mock_resp.text = "not json at all"
        session.post.return_value = mock_resp

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaResponseError, match="not valid JSON"):
            service.generate("hello")

    def test_schema_mismatch_raises_response_error(self) -> None:
        """JSON that doesn't match OllamaGenerateResponse should raise."""
        session = MagicMock(spec=requests.Session)
        session.post.return_value = _mock_response(
            json_data={"unexpected": "schema"}
        )

        service = OllamaService(settings=_make_settings(), session=session)

        with pytest.raises(OllamaResponseError, match="schema"):
            service.generate("hello")

    def test_optional_stat_fields(self) -> None:
        """Generation should succeed when Ollama omits optional stat fields."""
        session = MagicMock(spec=requests.Session)
        session.post.return_value = _mock_response(
            json_data={
                "model": "test-model",
                "response": "Cached response",
                "done": True,
                # No eval_count, total_duration, etc.
            }
        )

        service = OllamaService(settings=_make_settings(), session=session)
        result = service.generate("hello")
        assert result == "Cached response"


class TestOllamaServiceIsAvailable:
    """Tests for OllamaService.is_available()."""

    def test_healthy_ollama(self) -> None:
        """Returns True when Ollama responds 200."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value = _mock_response(status_code=200)

        service = OllamaService(settings=_make_settings(), session=session)
        assert service.is_available() is True

    def test_unhealthy_status(self) -> None:
        """Returns False when Ollama responds non-200."""
        session = MagicMock(spec=requests.Session)
        session.get.return_value = _mock_response(status_code=500)

        service = OllamaService(settings=_make_settings(), session=session)
        assert service.is_available() is False

    def test_connection_error(self) -> None:
        """Returns False when Ollama is unreachable."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = RequestsConnectionError("refused")

        service = OllamaService(settings=_make_settings(), session=session)
        assert service.is_available() is False

    def test_timeout(self) -> None:
        """Returns False when probe times out."""
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = Timeout("timed out")

        service = OllamaService(settings=_make_settings(), session=session)
        assert service.is_available() is False


class TestOllamaServiceClose:
    """Tests for OllamaService.close()."""

    def test_close_drains_session(self) -> None:
        """close() should call session.close()."""
        session = MagicMock(spec=requests.Session)
        service = OllamaService(settings=_make_settings(), session=session)
        service.close()
        session.close.assert_called_once()
