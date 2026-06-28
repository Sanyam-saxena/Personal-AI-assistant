"""
Sidebar component for the Streamlit frontend.
"""

from __future__ import annotations

import html
import os
import streamlit as st
from services.api_client import APIClient


def render_sidebar(api_client: APIClient, is_healthy: bool) -> None:
    """
    Renders the sidebar containing backend health diagnostic,
    active model details, conversation statistics, and management actions.

    Args:
        api_client: The API client instance.
        is_healthy: Checked status of the backend API connection.
    """
    with st.sidebar:
        # Title
        st.markdown("### 🔧 Diagnostics & Control")
        st.markdown("---")

        # 1. Connection Status
        if is_healthy:
            status_html = """
            <div class="status-badge status-online">
                <span class="status-dot"></span>
                Reachable
            </div>
            """
        else:
            status_html = """
            <div class="status-badge status-offline">
                <span class="status-dot"></span>
                Unreachable
            </div>
            """

        st.markdown("<div class='stat-label'>Backend Connection</div>", unsafe_allow_html=True)
        st.markdown(status_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        # 2. Model Name
        # Load the model from env (matching backend setup) or fall back to 'qwen3'
        model_name = html.escape(os.environ.get("OLLAMA_MODEL", "qwen3"))
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Active LLM Model</div>
                <div class="stat-value">{model_name}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # 3. Message Count
        # Count user + assistant messages in history
        msg_history = st.session_state.get("messages", [])
        message_count = len(msg_history)

        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Conversation Turn(s)</div>
                <div class="stat-value">{message_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("---")

        # 4. Clear Chat Button
        # Button styled using Streamlit native components (with custom CSS overriding borders)
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
