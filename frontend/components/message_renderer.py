"""
Component for rendering individual chat messages.
"""

from __future__ import annotations

import streamlit as st
from components.avatars import get_avatar
from components.message_actions import render_message_actions


def render_message(message: dict[str, str], index: int) -> None:
    """
    Renders a single chat message using Streamlit's native chat container.
    Wraps the message in an st.container with a custom key to support CSS alignments.
    """
    role = message["role"]
    content = message["content"]
    avatar = get_avatar(role)
    
    # Wrap in key-identified container to allow targeted custom CSS rules
    with st.container(key=f"msg-{role}-{index}"):
        with st.chat_message(role, avatar=avatar):
            st.markdown(content)
            # Display action buttons below assistant responses
            if role == "assistant":
                render_message_actions(message, index)
