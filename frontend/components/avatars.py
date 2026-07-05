"""
Avatar management component for the Streamlit frontend.
"""

from __future__ import annotations

from config.constants import AVATARS


def get_avatar(role: str) -> str:
    """
    Returns the avatar asset/character for the specified role.
    Sourced from config/constants.py for easy branding adjustments.
    """
    return AVATARS.get(role, AVATARS["user"])
