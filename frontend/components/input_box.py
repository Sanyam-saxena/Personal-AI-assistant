"""
Input box component for user query submission.
"""

from __future__ import annotations

import streamlit as st
from config.constants import CHAT


def render_input(disabled: bool = False) -> str | None:
    """
    Renders the chat input widget and returns the prompt entered by the user.
    """
    return st.chat_input(CHAT["placeholder"], disabled=disabled)
