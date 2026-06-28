"""
Pytest configuration and shared fixtures.

Fixture overview
----------------
reset_settings_cache  Clears the @lru_cache on get_settings() between tests
                      so each test gets a predictable configuration.

mock_service          A MagicMock(spec=OllamaService) with sensible defaults:
                      - generate() returns a fixed string
                      - is_available() returns True

client(mock_service)  A FastAPI TestClient with app.state.ollama patched to
                      the mock_service.  Prevents any real HTTP calls to Ollama.

Design note -- fresh app per test
----------------------------------
The ``client`` fixture creates a fresh ``TestClient`` for each test and
patches ``app.state.ollama`` directly.  While using ``create_application()``
to build a fresh app per test would provide stronger isolation, this would
also re-run ``configure_logging()`` and middleware registration on every
test.  The current approach is sufficient for the test suite because:
  * Each test restores the mock via the fixture lifecycle.
  * ``reset_settings_cache`` ensures settings are re-read.
  * Tests that need to delete ``app.state.ollama`` must restore it themselves
    (see ``TestChatServiceNotReady``).

Usage example
-------------
::

    def test_chat_ok(client, mock_service):
        response = client.post("/chat", json={"message": "Hello"})
        assert response.status_code == 200
        mock_service.generate.assert_called_once_with("Hello")
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import reset_rate_limit_state
from app.main import app
from app.services.ollama_service import OllamaService


@pytest.fixture(autouse=True)
def reset_settings_cache():  # type: ignore[return]
    """
    Clear the ``get_settings`` LRU cache before and after each test.

    Without this, a test that mutates environment variables would affect
    subsequent tests because the singleton is cached.
    """
    get_settings.cache_clear()
    reset_rate_limit_state()
    for attr in ("_ready_status", "_ready_time"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    yield
    get_settings.cache_clear()
    reset_rate_limit_state()
    for attr in ("_ready_status", "_ready_time"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


@pytest.fixture
def mock_service() -> MagicMock:
    """
    Return a MagicMock that satisfies the OllamaService interface.

    Defaults:
    * ``generate`` returns ``"Test AI response."``
    * ``is_available`` returns ``True``

    Override per-test::

        mock_service.generate.return_value = "Custom reply"
        mock_service.generate.side_effect = OllamaConnectionError("down")
    """
    service = MagicMock(spec=OllamaService)
    service.generate.return_value = "Test AI response."
    service.is_available.return_value = True
    return service


@pytest.fixture
def client(mock_service: MagicMock) -> Generator[TestClient, None, None]:
    """
    Return a synchronous TestClient with Ollama mocked out.

    Patches ``app.state.ollama`` with *mock_service* and restores the
    original value after the test completes, preventing test pollution.

    Args:
        mock_service: The MagicMock OllamaService fixture.

    Returns:
        Configured :class:`~fastapi.testclient.TestClient`.
    """
    original = getattr(app.state, "ollama", None)
    app.state.ollama = mock_service
    # raise_server_exceptions=False lets tests assert on 5xx responses
    # rather than having the client re-raise the exception.
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        # Restore original to prevent test pollution.
        if original is not None:
            app.state.ollama = original
        elif hasattr(app.state, "ollama"):
            del app.state.ollama
