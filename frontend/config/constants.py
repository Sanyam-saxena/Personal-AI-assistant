"""
User-facing UI string constants for the Streamlit frontend.
"""

from __future__ import annotations

APP_NAME: str = "⚡ Sam"

PAGE_TITLE: str = "Sam"

AVATARS: dict[str, str] = {
    "assistant": "⚡",
    "user": "👤"
}

CHAT: dict[str, str | list[str]] = {
    "placeholder": "Ask Sam anything...",
    "spinner": "Sam is thinking...",
    "welcome_title": "⚡ Sam",
    "welcome_subtitle": "Your personal AI assistant",
    "welcome_greeting": "How can I help you today?",
    "suggested_prompts": [
        "Explain Python decorators",
        "Build a Flask API",
        "Summarize a PDF",
        "Help me debug code"
    ]
}

ERRORS: dict[str, str] = {
    "backend_connection": (
        "⚠️ Cannot connect to AI Backend. Please check if the backend is running locally on port 8000 "
        "and that OLLAMA is serving requests properly."
    )
}
