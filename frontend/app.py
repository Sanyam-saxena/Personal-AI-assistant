"""
Jarvis AI Assistant Streamlit Frontend.
"""

from __future__ import annotations

import html
import logging
import os
import time

import streamlit as st

from utils.logger import configure_logging
from services.api_client import APIClient, APIError
from components.custom_css import inject_custom_css
from components.sidebar import render_sidebar

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
        page_title="Jarvis AI Assistant",
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
    head_left, head_right = st.columns([9, 1.5])
    with head_left:
        st.markdown(
            """
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 0.5rem;">
                <span style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.05em; 
                             background: linear-gradient(135deg, #2563eb, #60a5fa);
                             -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    ⚡ Jarvis AI Assistant
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with head_right:
        theme_btn_label = "☀️ Light Mode" if is_dark else "🌙 Dark Mode"
        if st.button(theme_btn_label, use_container_width=True, key="theme_toggle_btn"):
            st.session_state.theme = "light" if is_dark else "dark"
            st.rerun()

    st.markdown(
        "<hr style='margin-top: 0; margin-bottom: 1.5rem; border-color: var(--border);'>",
        unsafe_allow_html=True,
    )

    # 7. Render Chat History Stream
    # Uses Streamlit native chat containers styled dynamically with our custom CSS classes
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 8. User Interaction and Chat Input
    # Only allow typing if backend is online, else prompt connection instructions
    if not is_healthy:
        st.error(
            "⚠️ Cannot connect to Jarvis Backend. Please check if the backend is running locally on port 8000 "
            "and that OLLAMA is serving requests properly."
        )

    # st.chat_input is always available but we handle execution based on connection
    if prompt := st.chat_input("Ask Jarvis anything...", disabled=not is_healthy):
        # Sanitise user input to prevent XSS
        safe_prompt = _sanitise_model_output(prompt)
        # 1. Append User prompt to history and display it
        st.session_state.messages.append({"role": "user", "content": safe_prompt})
        _trim_history()
        with st.chat_message("user"):
            st.markdown(safe_prompt)

        # 2. Query Backend and get response
        with st.chat_message("assistant"):
            with st.spinner("Jarvis is thinking..."):
                try:
                    logger.info("Sending chat prompt to backend")
                    reply = api_client.send_chat(prompt)

                    # Sanitise model output to prevent XSS via model-
                    # generated HTML (e.g. <script> or tracking pixels).
                    safe_reply = _sanitise_model_output(reply)

                    # 3. Display reply and save to history
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
