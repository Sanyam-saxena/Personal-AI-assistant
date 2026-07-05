"""
Chat window component that renders the conversation history stream.
"""

from __future__ import annotations

from components.message_renderer import render_message


def render_chat(messages: list[dict[str, str]]) -> None:
    """
    Renders the chat history stream by iterating and delegating message display to render_message.
    """
    for msg in messages:
        render_message(msg)
