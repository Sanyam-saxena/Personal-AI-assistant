"""
Sam AI Assistant Streamlit Frontend.
"""

from __future__ import annotations

import html
import logging
import os
import time

import streamlit as st

from utils.logger import configure_logging
from services.api_client import APIClient, APIError
from config.constants import PAGE_TITLE, CHAT
from components import (
    inject_custom_css,
    render_sidebar,
    render_header,
    render_chat,
    render_input,
    render_backend_status,
)

# Initialize logging — level is configurable via environment variable.
configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("frontend_app")

# Health check cache TTL in seconds.
_HEALTH_CHECK_TTL_S = 10


def _cached_health_check(api_client: APIClient) -> bool:
    """
    Return backend health status, cached for ``_HEALTH_CHECK_TTL_S`` seconds.

    Avoids firing a synchronous HTTP request on every Streamlit rerun (which
    happens on every widget interaction).  The cache uses
    ``st.session_state`` and a monotonic timestamp.
    """
    now = time.monotonic()
    last_check: float = st.session_state.get("_health_ts", 0.0)
    if now - last_check < _HEALTH_CHECK_TTL_S:
        return st.session_state.get("_health_ok", False)

    is_healthy = api_client.check_health()
    st.session_state["_health_ts"] = now
    st.session_state["_health_ok"] = is_healthy
    return is_healthy


# Maximum number of messages kept in history to avoid session state bloating.
_MAX_HISTORY: int = 100


def _sanitise_model_output(text: str) -> str:
    """
    Sanitise AI model output and user input before rendering or storing.

    Escapes HTML entities to prevent XSS via user or model-generated content
    (e.g. ``<script>`` tags).  Markdown formatting is preserved because
    ``st.markdown()`` operates on the escaped text.
    """
    # Escape HTML to prevent raw HTML injection.
    return html.escape(text, quote=True)


def _trim_history() -> None:
    """Trim session state messages to keep only the most recent _MAX_HISTORY messages."""
    if "messages" in st.session_state and len(st.session_state.messages) > _MAX_HISTORY:
        st.session_state.messages = st.session_state.messages[-_MAX_HISTORY:]


def main() -> None:
    # 1. Page Configuration
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # 2. State Initialization
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Cache the API Client in session state so we don't recreate it
    if "api_client" not in st.session_state:
        st.session_state.api_client = APIClient()

    api_client: APIClient = st.session_state.api_client
    is_dark = st.session_state.theme == "dark"

    # 3. Inject CSS Theme
    inject_custom_css(is_dark)

    # 4. Check Health of Backend (cached to avoid blocking every rerun)
    is_healthy = _cached_health_check(api_client)

    # 5. Render Sidebar Controls and Diagnostics
    render_sidebar(api_client, is_healthy)

    # 6. Render Main Header (Brand + Theme Toggle)
    render_header(is_dark)

    # 7. Render Chat History Stream
    render_chat(st.session_state.messages)

    # 8. Render Connection Alert if unhealthy
    render_backend_status(is_healthy)

    # 9. User Interaction and Chat Input
    prompt = render_input(disabled=not is_healthy)
    if prompt:
        # Sanitise user input to prevent XSS
        safe_prompt = _sanitise_model_output(prompt)
        # Append User prompt to history and display it
        st.session_state.messages.append({"role": "user", "content": safe_prompt})
        _trim_history()
        with st.chat_message("user"):
            st.markdown(safe_prompt)

        # Query Backend and get response
        with st.chat_message("assistant"):
            with st.spinner(CHAT["spinner"]):
                try:
                    logger.info("Sending chat prompt to backend")
                    reply = api_client.send_chat(prompt)

                    # Sanitise model output to prevent XSS via model-generated HTML
                    safe_reply = _sanitise_model_output(reply)

                    # Display reply and save to history
                    st.markdown(safe_reply)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": safe_reply}
                    )
                    _trim_history()

                except APIError as exc:
                    logger.error("Chat generation failed | error=%s", exc)
                    st.error(f"❌ Error: {exc!s}")


if __name__ == "__main__":
    main()
