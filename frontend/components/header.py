"""
Header rendering component for the Streamlit frontend.
"""

from __future__ import annotations

import streamlit as st
from config.constants import APP_NAME


def render_header(is_dark: bool) -> None:
    """
    Renders the main header containing the brand title and the theme toggle button.
    """
    head_left, head_right = st.columns([9, 1.5])
    with head_left:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 0.5rem;">
                <span style="font-size: 1.8rem; font-weight: 800; letter-spacing: -0.05em; 
                             background: linear-gradient(135deg, #2563eb, #60a5fa);
                             -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                    {APP_NAME}
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
