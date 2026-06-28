"""
Custom CSS styling injection for the Streamlit frontend.
"""

from __future__ import annotations

import streamlit as st


def inject_custom_css(is_dark: bool) -> None:
    """
    Injects custom CSS overrides into Streamlit to hide chrome and apply
    a premium Zinc/Glassmorphic design system.

    Args:
        is_dark: Whether the active theme is dark mode.
    """
    # Color tokens for Light vs Dark mode
    bg = "#09090b" if is_dark else "#ffffff"
    bg_subtle = "#0c0c0f" if is_dark else "#f9fafb"
    card = "#0c0c0f" if is_dark else "#ffffff"
    border = "#1e1e24" if is_dark else "#e4e4e7"
    border_subtle = "#16161a" if is_dark else "#f0f0f2"
    text = "#fafafa" if is_dark else "#09090b"
    text_muted = "#a1a1aa" if is_dark else "#71717a"
    text_dim = "#52525b" if is_dark else "#a1a1aa"
    accent = "#2563eb"
    accent_subtle = "rgba(37,99,235,0.15)" if is_dark else "rgba(37,99,235,0.08)"
    green = "#22c55e" if is_dark else "#16a34a"
    green_muted = "rgba(34,197,94,0.12)" if is_dark else "rgba(22,163,74,0.08)"
    red = "#ef4444" if is_dark else "#dc2626"
    red_muted = "rgba(239,68,68,0.12)" if is_dark else "rgba(220,38,38,0.08)"

    css = f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* Fonts loaded via <link> above (faster than @import, no FOUC) */

        /* CSS Variables */
        :root {{
            --bg: {bg};
            --bg-subtle: {bg_subtle};
            --card: {card};
            --border: {border};
            --border-subtle: {border_subtle};
            --text: {text};
            --text-muted: {text_muted};
            --text-dim: {text_dim};
            --accent: {accent};
            --accent-subtle: {accent_subtle};
            --green: {green};
            --green-muted: {green_muted};
            --red: {red};
            --red-muted: {red_muted};
            --radius: 12px;
        }}

        /* Hide Streamlit default components */
        header[data-testid="stHeader"], 
        #MainMenu, 
        footer, 
        [data-testid="stToolbar"],
        [data-testid="stDecoration"], 
        [data-testid="stStatusWidget"], 
        .stDeployButton,
        div[data-testid="stSidebarCollapsedControl"] {{
            display: none !important;
        }}

        /* Reset Global Container backgrounds */
        html, body, 
        [data-testid="stAppViewContainer"], 
        [data-testid="stApp"], 
        .main, 
        .block-container, 
        section[data-testid="stMain"] {{
            background-color: var(--bg) !important;
            color: var(--text) !important;
            font-family: 'DM Sans', -apple-system, sans-serif !important;
        }}

        /* App view padding limit */
        .block-container {{
            padding: 2rem 2.5rem 3rem !important;
            max-width: 1100px !important;
        }}

        /* Sidebar Custom Styles */
        [data-testid="stSidebar"] {{
            background-color: var(--bg-subtle) !important;
            border-right: 1px solid var(--border) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
            padding-top: 1rem !important;
        }}

        /* Scrollbar customization */
        ::-webkit-scrollbar {{
            width: 6px;
            height: 6px;
        }}
        ::-webkit-scrollbar-track {{
            background: transparent;
        }}
        ::-webkit-scrollbar-thumb {{
            background: var(--border);
            border-radius: 4px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: var(--text-dim);
        }}

        /* Custom Header Brand Layout */
        .brand-container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}
        .brand-logo {{
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.04em;
            background: linear-gradient(135deg, var(--accent), #60a5fa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        /* Custom Chat bubble styles */
        div[data-testid="stChatMessage"] {{
            background-color: transparent !important;
            border: none !important;
            padding: 0.5rem 0 !important;
        }}

        /* Custom Stat Card widgets */
        .stat-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        }}
        .stat-label {{
            font-size: 0.75rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }}
        .stat-value {{
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
        }}

        /* Status Badge Widget */
        .status-badge {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 30px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .status-online {{
            color: var(--green);
            background-color: var(--green-muted);
            border: 1px solid rgba(34, 197, 94, 0.2);
        }}
        .status-offline {{
            color: var(--red);
            background-color: var(--red-muted);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }}
        .status-online .status-dot {{
            background-color: var(--green);
            box-shadow: 0 0 8px var(--green);
            animation: pulse 2s infinite;
        }}
        .status-offline .status-dot {{
            background-color: var(--red);
            box-shadow: 0 0 8px var(--red);
        }}

        /* Accent button customizations */
        .stButton button {{
            border-radius: 8px !important;
            transition: all 0.2s ease-in-out !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
        }}
        .stButton button:hover {{
            border-color: var(--accent) !important;
            color: var(--accent) !important;
            background-color: var(--accent-subtle) !important;
        }}

        /* Pulsing dot animation */
        @keyframes pulse {{
            0% {{
                transform: scale(0.9);
                opacity: 0.8;
            }}
            50% {{
                transform: scale(1.1);
                opacity: 1;
            }}
            100% {{
                transform: scale(0.9);
                opacity: 0.8;
            }}
        }}

        /* Code syntax font customization */
        code {{
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 0.9em !important;
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
