"""
Theme and design token constants for the Streamlit frontend.
"""

from __future__ import annotations


def get_theme_colors(is_dark: bool) -> dict[str, str]:
    """
    Returns the design system color tokens depending on whether
    the active theme is dark mode.
    """
    return {
        "bg": "#09090b" if is_dark else "#ffffff",
        "bg_subtle": "#0c0c0f" if is_dark else "#f9fafb",
        "card": "#0c0c0f" if is_dark else "#ffffff",
        "border": "#1e1e24" if is_dark else "#e4e4e7",
        "border_subtle": "#16161a" if is_dark else "#f0f0f2",
        "text": "#fafafa" if is_dark else "#09090b",
        "text_muted": "#a1a1aa" if is_dark else "#71717a",
        "text_dim": "#52525b" if is_dark else "#a1a1aa",
        "accent": "#2563eb",
        "accent_subtle": "rgba(37,99,235,0.15)" if is_dark else "rgba(37,99,235,0.08)",
        "green": "#22c55e" if is_dark else "#16a34a",
        "green_muted": "rgba(34,197,94,0.12)" if is_dark else "rgba(22,163,74,0.08)",
        "red": "#ef4444" if is_dark else "#dc2626",
        "red_muted": "rgba(239,68,68,0.12)" if is_dark else "rgba(220,38,38,0.08)",
    }
