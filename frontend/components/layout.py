"""
Layout component for the Streamlit frontend.
Handles creating and organizing the structural page containers and margins.
"""

from __future__ import annotations

import streamlit as st


def render_layout() -> None:
    """
    Creates and arranges the page structure and canvas spacing.
    Intentionally hides Streamlit implementation details (e.g. DeltaGenerator returns).
    Future milestones (Memory panels, Voice indicators, RAG panels) can hook directly
    into this component to rearrange the main layout grid.
    """
    # Mount layout structural marker and top margin spacing
    st.markdown(
        "<div class='layout-root' style='margin-top: 0.5rem;'></div>",
        unsafe_allow_html=True,
    )
