"""
Message Actions component for rendering response controls (copy, regenerate, feedback).
"""

from __future__ import annotations

import streamlit as st


def render_message_actions(message: dict[str, str], index: int) -> None:
    """
    Renders action buttons below assistant responses.
    
    API accepts the complete message dictionary and index to allow future
    extensibility (e.g. Speak, Pin, Export, Share, Edit) without changing interface.
    """
    # Create narrow columns to place buttons side-by-side
    col1, col2, col3, col4, col5 = st.columns([0.15, 0.22, 0.1, 0.1, 0.43])
    
    # 1. Copy Action - Python-first mock using st.toast
    with col1:
        if st.button("📋 Copy", key=f"copy_{index}", use_container_width=True, help="Copy to Clipboard"):
            # FUTURE INTEGRATION POINT: Replace with native clipboard utility or JS injector
            st.toast("Copied message to clipboard! (Mocked)")
            
    # 2. Regenerate Action - disabled placeholder
    with col2:
        st.button("🔄 Retry", key=f"retry_{index}", disabled=True, use_container_width=True, help="Regenerate Response (Coming Soon)")
        
    # 3. Feedback thumbs - disabled placeholders
    with col3:
        st.button("👍", key=f"thumbs_up_{index}", disabled=True, use_container_width=True, help="Good Response (Coming Soon)")
    with col4:
        st.button("👎", key=f"thumbs_down_{index}", disabled=True, use_container_width=True, help="Bad Response (Coming Soon)")
        
    # 4. More Options - disabled architectural placeholder
    with col5:
        st.button("⋮ More", key=f"more_{index}", disabled=True, use_container_width=True, help="More actions: Share, Pin, Export (Coming Soon)")
Distributed-action placeholders are fully isolated.
