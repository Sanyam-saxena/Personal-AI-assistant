"""
Theme and semantic design token constants for the Streamlit frontend.
"""

from __future__ import annotations


def get_semantic_tokens(is_dark: bool) -> dict[str, str]:
    """
    Returns the semantic design token values depending on whether
    the active theme is dark mode.
    """
    return {
        "surface": "#09090b" if is_dark else "#ffffff",
        "surface_secondary": "#0c0c0f" if is_dark else "#f9fafb",
        "border": "#1e1e24" if is_dark else "#e4e4e7",
        "border_subtle": "#16161a" if is_dark else "#f0f0f2",
        "text_primary": "#fafafa" if is_dark else "#09090b",
        "text_secondary": "#a1a1aa" if is_dark else "#71717a",
        "text_dim": "#52525b" if is_dark else "#a1a1aa",
        "accent": "#2563eb",
        "hover": "rgba(37, 99, 235, 0.15)" if is_dark else "rgba(37, 99, 235, 0.08)",
        "success": "#22c55e" if is_dark else "#16a34a",
        "success_bg": "rgba(34, 197, 94, 0.12)" if is_dark else "rgba(22, 163, 74, 0.08)",
        "warning": "#f59e0b" if is_dark else "#d97706",
        "warning_bg": "rgba(245, 158, 11, 0.12)" if is_dark else "rgba(217, 119, 6, 0.08)",
        "error": "#ef4444" if is_dark else "#dc2626",
        "error_bg": "rgba(239, 68, 68, 0.12)" if is_dark else "rgba(220, 38, 38, 0.08)",
        "shadow": "rgba(0, 0, 0, 0.4)" if is_dark else "rgba(0, 0, 0, 0.05)",
    }
