"""
Frontend UI components.

Future planned reusable components (Architectural Placeholders):
- avatar.py            : Displays custom user and assistant avatars.
- typing_indicator.py : Renders the assistant's typing indicator while thinking.
- welcome.py           : Renders the welcome greeting/onboarding for new sessions.
- footer.py            : Displays page footer with links and version information.
"""

from __future__ import annotations

from components.custom_css import inject_custom_css
from components.sidebar import render_sidebar
from components.header import render_header
from components.message_renderer import render_message
from components.chat_window import render_chat
from components.input_box import render_input
from components.status import render_backend_status

__all__ = [
    "inject_custom_css",
    "render_sidebar",
    "render_header",
    "render_message",
    "render_chat",
    "render_input",
    "render_backend_status",
]
