"""
User-facing UI string constants for the Streamlit frontend.
"""

APP_NAME: str = "⚡ Sam"

PAGE_TITLE: str = "Sam"

CHAT: dict[str, str] = {
    "placeholder": "Ask Sam anything...",
    "spinner": "Sam is thinking...",
    "welcome": "Welcome! I am Sam, your AI assistant."
}

ERRORS: dict[str, str] = {
    "backend_connection": (
        "⚠️ Cannot connect to AI Backend. Please check if the backend is running locally on port 8000 "
        "and that OLLAMA is serving requests properly."
    )
}
