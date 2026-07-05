"""
Backend health status UI warning component.
"""

from __future__ import annotations

import streamlit as st
from config.constants import ERRORS


def render_backend_status(is_healthy: bool) -> None:
    """
    Renders the backend health status warning UI if the connection check fails.
    """
    if not is_healthy:
        st.error(ERRORS["backend_connection"])
