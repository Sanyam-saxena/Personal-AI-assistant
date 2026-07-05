"""
Welcome Screen component for the Streamlit frontend.
"""

from __future__ import annotations

import streamlit as st
from config.constants import CHAT


def render_welcome() -> str | None:
    """
    Renders the modern welcome panel and returns a suggested prompt if clicked.
    
    Designed to be extensible: future options (e.g. recent conversations, quick actions,
    document uploads, voice templates) can be integrated modularly inside this layout.
    """
    # 1. Main Welcome Branding Container
    st.markdown(
        f"""
        <div class="welcome-container">
            <div class="welcome-logo">{CHAT["welcome_title"]}</div>
            <div class="welcome-title">{CHAT["welcome_title"]}</div>
            <div class="welcome-subtitle">{CHAT["welcome_subtitle"]}</div>
            <div style="font-size: 1.25rem; font-weight: 500; margin-bottom: 1.5rem;">
                {CHAT["welcome_greeting"]}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Suggested Prompts Dynamic Grid
    # We render buttons in a structured 2x2 column layout
    selected_prompt: str | None = None
    suggested_prompts = CHAT.get("suggested_prompts", [])
    
    if suggested_prompts:
        col1, col2 = st.columns(2)
        for i, prompt in enumerate(suggested_prompts):
            # Alternate columns for the 2x2 grid structure
            target_col = col1 if i % 2 == 0 else col2
            with target_col:
                if st.button(
                    prompt, 
                    use_container_width=True, 
                    key=f"suggested_prompt_{i}"
                ):
                    selected_prompt = prompt

    return selected_prompt
