"""
Component for rendering individual chat messages.
"""

from __future__ import annotations

import streamlit as st


def render_message(message: dict[str, str]) -> None:
    """
    Renders a single chat message (either user or assistant) using Streamlit's native chat container.
    """
    role = message["role"]
    content = message["content"]
    with st.chat_message(role):
        st.markdown(content)
