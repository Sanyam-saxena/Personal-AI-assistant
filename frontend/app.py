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
    render_layout,
    render_welcome,
    render_typing_indicator,
)

# Initialize logging — level is configurable via environment variable.
configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("frontend_app")


def _cached_health_check(api_client: APIClient) -> bool:
    """
    Return backend health status, cached for 10 seconds.
    """
    now = time.monotonic()
    last_check: float = st.session_state.get("_health_ts", 0.0)
    if now - last_check < 10:
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
    """
    return html.escape(text, quote=True)


def _trim_history() -> None:
    """Trim session state messages to keep only the most recent _MAX_HISTORY messages."""
    if "messages" in st.session_state and len(st.session_state.messages) > _MAX_HISTORY:
        st.session_state.messages = st.session_state.messages[-_MAX_HISTORY:]


def main() -> None:
    # 1. Page Configuration
    # st.set_page_config remains in app.py as the first execution command
    # to avoid StreamlitAPIException errors during bootstrapping.
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

    if "api_client" not in st.session_state:
        st.session_state.api_client = APIClient()

    # app_start_time is used to compute the session duration in the sidebar.
    # Named app_start_time rather than session_start_time to scale for future conversation timings.
    if "app_start_time" not in st.session_state:
        st.session_state.app_start_time = time.time()

    # current_chat_id is reserved for future conversation switching / history features.
    if "current_chat_id" not in st.session_state:
        st.session_state.current_chat_id = None

    api_client: APIClient = st.session_state.api_client
    is_dark = st.session_state.theme == "dark"

    # 3. CSS Injection (keeps layout and styling separate)
    inject_custom_css(is_dark)

    # 4. Render Structural Layout (Page containers only, encapsulates Streamlit details)
    render_layout()

    # 5. Check Health of Backend
    is_healthy = _cached_health_check(api_client)

    # 6. Render Sidebar Controls and Diagnostics
    render_sidebar(api_client, is_healthy)

    # 7. Main Area Content Layout Orchestration
    selected_prompt: str | None = None
    if not st.session_state.messages:
        # Render welcome component (Dynamic suggested prompt buttons)
        selected_prompt = render_welcome()
    else:
        # Render top header bar and existing messages
        render_header(is_dark)
        render_chat(st.session_state.messages)

    # 8. Render Connection Alert if unhealthy
    render_backend_status(is_healthy)

    # 9. User Interaction and Chat Input
    # FUTURE FILE UPLOAD & VOICE INPUTS PLACEHOLDER AREA:
    # A dedicated placeholder container will host voice recording and attachment buttons here in future milestones.
    prompt = render_input(disabled=not is_healthy)
    
    # Resolve prompt from text input or welcome screen selection
    active_prompt = prompt or selected_prompt

    if active_prompt:
        # Save raw prompt to send to backend, sanitise text for local rendering
        st.session_state["pending_prompt"] = active_prompt
        safe_prompt = _sanitise_model_output(active_prompt)
        st.session_state.messages.append({"role": "user", "content": safe_prompt})
        _trim_history()
        st.rerun()

    # 10. Handle Pending Assistant Response Generation
    if "pending_prompt" in st.session_state:
        raw_prompt = st.session_state.pop("pending_prompt")
        
        # Display pulsing typing indicator placeholder while awaiting backend
        typing_container = st.empty()
        with typing_container:
            render_typing_indicator()

        try:
            logger.info("Sending chat prompt to backend")
            reply = api_client.send_chat(raw_prompt)

            # Sanitise model output
            safe_reply = _sanitise_model_output(reply)

            # Clear typing indicator
            typing_container.empty()

            # Append reply to history and trigger rerun
            st.session_state.messages.append(
                {"role": "assistant", "content": safe_reply}
            )
            _trim_history()
            st.rerun()

        except APIError as exc:
            typing_container.empty()
            logger.error("Chat generation failed | error=%s", exc)
            st.error(f"❌ Error: {exc!s}")


if __name__ == "__main__":
    main()
