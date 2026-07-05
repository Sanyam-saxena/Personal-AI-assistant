"""
Sidebar component for the Streamlit frontend.
"""

from __future__ import annotations

import html
import os
import time
import streamlit as st
from services.api_client import APIClient


def render_info_card(
    title: str,
    value: str,
    icon: str | None = None,
    status: str | None = None,
) -> None:
    """
    Renders a unified, styled information card in the sidebar.
    Deduplicates UI layout code and aligns with semantic visual system.
    """
    status_html = ""
    if status == "online":
        status_html = """
        <div class="info-card-status status-online">
            <span class="status-dot"></span>
            Reachable
        </div>
        """
    elif status == "offline":
        status_html = """
        <div class="info-card-status status-offline">
            <span class="status-dot"></span>
            Unreachable
        </div>
        """
    elif status == "placeholder":
        status_html = """
        <div class="info-card-status status-placeholder">
            🔒 Coming Soon
        </div>
        """

    # Add icon to display text if present
    icon_prefix = f"{icon} " if icon else ""

    st.markdown(
        f"""
        <div class="info-card">
            <div class="info-card-label">{title}</div>
            <div class="info-card-value">{icon_prefix}{value}</div>
            {status_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(api_client: APIClient, is_healthy: bool) -> None:
    """
    Renders the sidebar with unified info cards containing status, model details,
    conversation turnovers, session duration metrics, and placeholders for future updates.
    """
    with st.sidebar:
        # Title
        st.markdown("### 🔧 Diagnostics & Control")
        st.markdown("---")

        # 1. Connection Status Card
        conn_label = "Online" if is_healthy else "Offline"
        conn_status = "online" if is_healthy else "offline"
        render_info_card("Backend Connection", conn_label, icon="🔌", status=conn_status)

        # 2. Model Name Card
        model_name = html.escape(os.environ.get("OLLAMA_MODEL", "qwen3"))
        render_info_card("Active LLM Model", model_name, icon="🤖")

        # 3. Message Count Card
        msg_history = st.session_state.get("messages", [])
        message_count = len(msg_history)
        render_info_card("Conversation Turn(s)", str(message_count), icon="💬")

        # 4. Session Duration Card (renamed app_start_time)
        app_start = st.session_state.get("app_start_time", time.time())
        elapsed = time.time() - app_start
        mins, secs = divmod(int(elapsed), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            duration_str = f"{hours}h {mins}m {secs}s"
        else:
            duration_str = f"{mins}m {secs}s"
            
        render_info_card("Session Duration", duration_str, icon="⏱️")

        # 5. Future Feature Placeholders (Coming Soon cards)
        render_info_card("Memory Status", "Inactive", icon="🧠", status="placeholder")
        render_info_card("Voice Status", "Disabled", icon="🎙️", status="placeholder")

        st.markdown("---")

        # 6. Clear Chat Button
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
