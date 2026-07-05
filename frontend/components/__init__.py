"""
Frontend UI components.

Future planned reusable components (Architectural Placeholders):
- avatar.py            : Displays custom user and assistant avatars. (Replaced by avatars.py in Milestone 2)
- typing_indicator.py : Renders the assistant's typing indicator while thinking. (Implemented in Milestone 2)
- welcome.py           : Renders the welcome greeting/onboarding for new sessions. (Implemented in Milestone 2)
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
from components.layout import render_layout
from components.avatars import get_avatar
from components.welcome import render_welcome
from components.typing_indicator import render_typing_indicator
from components.message_actions import render_message_actions

__all__ = [
    "inject_custom_css",
    "render_sidebar",
    "render_header",
    "render_message",
    "render_chat",
    "render_input",
    "render_backend_status",
    "render_layout",
    "get_avatar",
    "render_welcome",
    "render_typing_indicator",
    "render_message_actions",
]
