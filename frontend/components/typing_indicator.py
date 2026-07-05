"""
Typing Indicator component for the Streamlit frontend.
"""

from __future__ import annotations

import streamlit as st
from components.avatars import get_avatar


def render_typing_indicator() -> None:
    """
    Renders an animated typing indicator bubble representing assistant thinking.
    Isolated to allow future reasoning steps, token streams, or progress bars.
    """
    assistant_avatar = get_avatar("assistant")
    with st.chat_message("assistant", avatar=assistant_avatar):
        st.markdown(
            """
            <div style="display: flex; align-items: center; min-height: 24px; padding: 4px 0;">
                <span class="pulse-dot"></span>
                <span class="pulse-dot"></span>
                <span class="pulse-dot"></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
