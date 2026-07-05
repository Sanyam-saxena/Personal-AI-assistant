"""
Custom CSS styling injection for the Streamlit frontend.
Organized into documented sections to maintain accessibility and responsive design.
"""

from __future__ import annotations

import streamlit as st
from config.theme import get_semantic_tokens


def inject_custom_css(is_dark: bool) -> None:
    """
    Injects custom CSS overrides into Streamlit to hide chrome and apply
    a premium Zinc/Glassmorphic design system using semantic tokens.
    """
    tokens = get_semantic_tokens(is_dark)
    surface = tokens["surface"]
    surface_secondary = tokens["surface_secondary"]
    border = tokens["border"]
    border_subtle = tokens["border_subtle"]
    text_primary = tokens["text_primary"]
    text_secondary = tokens["text_secondary"]
    text_dim = tokens["text_dim"]
    accent = tokens["accent"]
    hover = tokens["hover"]
    success = tokens["success"]
    success_bg = tokens["success_bg"]
    warning = tokens["warning"]
    warning_bg = tokens["warning_bg"]
    error = tokens["error"]
    error_bg = tokens["error_bg"]
    shadow = tokens["shadow"]

    css = f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* =========================================================================
           1. Global Layout & Theme Variables
           ========================================================================= */
        :root {{
            --bg: {surface};
            --bg-subtle: {surface_secondary};
            --card: {surface_secondary};
            --border: {border};
            --border-subtle: {border_subtle};
            --text: {text_primary};
            --text-muted: {text_secondary};
            --text-dim: {text_dim};
            --accent: {accent};
            --accent-subtle: {hover};
            --green: {success};
            --green-muted: {success_bg};
            --yellow: {warning};
            --yellow-muted: {warning_bg};
            --red: {error};
            --red-muted: {error_bg};
            --radius: 12px;
            --shadow: {shadow};
            --transition-smooth: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
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
            transition: background-color 0.3s ease, color 0.3s ease;
        }}

        /* App view padding limit */
        .block-container {{
            padding: 2rem 2.5rem 8rem !important; /* Bottom padding reserved for sticky input */
            max-width: 900px !important;
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

        /* =========================================================================
           2. Typography
           ========================================================================= */
        h1, h2, h3, h4, h5, h6 {{
            color: var(--text) !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
        }}
        p, li, span, label {{
            line-height: 1.6 !important;
        }}
        code {{
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 0.9em !important;
        }}

        /* =========================================================================
           3. Sidebar Cards
           ========================================================================= */
        [data-testid="stSidebar"] {{
            background-color: var(--bg-subtle) !important;
            border-right: 1px solid var(--border) !important;
        }}
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
            padding-top: 1.5rem !important;
            gap: 0.75rem !important;
        }}

        /* =========================================================================
           4. Header
           ========================================================================= */
        .brand-container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1rem;
            margin-bottom: 2rem;
        }}

        /* =========================================================================
           5. Chat Messages
           ========================================================================= */
        /* Space out native chat containers */
        div[data-testid="stChatMessage"] {{
            background-color: transparent !important;
            border: none !important;
            padding: 0.75rem 0 !important;
            animation: fadeIn 0.3s ease-out;
            gap: 12px !important;
        }}

        /* Target message avatar to be circular */
        div[data-testid="stChatMessageAvatar"] {{
            border-radius: 50% !important;
            background-color: var(--bg-subtle) !important;
            border: 1px solid var(--border) !important;
            width: 34px !important;
            height: 34px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 1.1rem !important;
        }}

        /* User specific message alignment and bubble shape */
        div[class*="st-key-msg-user"] div[data-testid="stChatMessage"] {{
            flex-direction: row-reverse !important;
        }}
        div[class*="st-key-msg-user"] div[data-testid="stChatMessageContent"] {{
            background-color: var(--accent-subtle) !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px 16px 4px 16px !important;
            padding: 0.75rem 1rem !important;
            box-shadow: 0 2px 4px var(--shadow);
            color: var(--text) !important;
        }}

        /* Assistant specific message bubble shape */
        div[class*="st-key-msg-assistant"] div[data-testid="stChatMessageContent"] {{
            background-color: var(--bg-subtle) !important;
            border: 1px solid var(--border) !important;
            border-radius: 16px 16px 16px 4px !important;
            padding: 0.75rem 1rem !important;
            box-shadow: 0 2px 4px var(--shadow);
            color: var(--text) !important;
        }}

        /* Message Action Buttons Layout */
        .message-action-row {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.5rem;
            padding-left: 2px;
        }}

        /* =========================================================================
           6. Welcome Screen
           ========================================================================= */
        .welcome-container {{
            text-align: center;
            padding: 3rem 1.5rem;
            max-width: 600px;
            margin: 0 auto;
            animation: fadeIn 0.4s ease-out;
        }}
        .welcome-logo {{
            font-size: 3rem;
            margin-bottom: 0.75rem;
        }}
        .welcome-title {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}
        .welcome-subtitle {{
            font-size: 1.1rem;
            color: var(--text-muted);
            margin-bottom: 2rem;
        }}
        
        /* Grid container for suggested prompts */
        .welcome-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-top: 1.5rem;
            text-align: left;
        }}

        /* =========================================================================
           7. Buttons & Form Fields
           ========================================================================= */
        /* Streamlit Button Overrides */
        .stButton button {{
            border-radius: 8px !important;
            border: 1px solid var(--border) !important;
            background-color: var(--bg-subtle) !important;
            color: var(--text) !important;
            transition: var(--transition-smooth) !important;
            font-size: 0.85rem !important;
            font-weight: 500 !important;
        }}
        .stButton button:hover {{
            border-color: var(--accent) !important;
            color: var(--accent) !important;
            background-color: var(--accent-subtle) !important;
            transform: translateY(-1px);
            box-shadow: 0 4px 6px var(--shadow);
        }}
        .stButton button:focus {{
            outline: 2px solid var(--accent) !important;
            outline-offset: 2px !important;
        }}

        /* =========================================================================
           8. Cards (Info Card Helpers)
           ========================================================================= */
        .info-card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 0.85rem 1.1rem;
            box-shadow: 0 1px 2px var(--shadow);
            transition: var(--transition-smooth);
        }}
        .info-card:hover {{
            border-color: var(--text-dim);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px var(--shadow);
        }}
        .info-card-label {{
            font-size: 0.72rem;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.2rem;
        }}
        .info-card-value {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
        }}
        .info-card-status {{
            font-size: 0.7rem;
            font-weight: 500;
            margin-top: 0.25rem;
            display: inline-flex;
            align-items: center;
            gap: 4px;
        }}

        /* Status colors */
        .status-online {{ color: var(--green); }}
        .status-offline {{ color: var(--red); }}
        .status-placeholder {{ color: var(--text-muted); font-style: italic; }}

        /* Status Badge Dot */
        .status-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            display: inline-block;
        }}
        .status-online .status-dot {{
            background-color: var(--green);
            box-shadow: 0 0 6px var(--green);
            animation: pulse 2s infinite;
        }}
        .status-offline .status-dot {{
            background-color: var(--red);
            box-shadow: 0 0 6px var(--red);
        }}

        /* =========================================================================
           9. Animations
           ========================================================================= */
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes pulse {{
            0% {{ transform: scale(0.9); opacity: 0.8; }}
            50% {{ transform: scale(1.1); opacity: 1; }}
            100% {{ transform: scale(0.9); opacity: 0.8; }}
        }}

        .pulse-dot {{
            display: inline-block;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--text-muted);
            margin: 0 2px;
            animation: pulse 1.4s infinite both;
        }}
        .pulse-dot:nth-child(2) {{ animation-delay: 0.2s; }}
        .pulse-dot:nth-child(3) {{ animation-delay: 0.4s; }}

        /* =========================================================================
           10. Chat Input & Future Actions Placeholder
           ========================================================================= */
        /* Style Streamlit chat input area sticky container */
        div[data-testid="stChatInput"] {{
            background-color: var(--bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 24px !important;
            padding: 4px 6px !important;
            box-shadow: 0 4px 12px var(--shadow) !important;
            transition: var(--transition-smooth);
        }}
        div[data-testid="stChatInput"]:focus-within {{
            border-color: var(--accent) !important;
            box-shadow: 0 4px 16px var(--accent-subtle) !important;
        }}

        /* Placeholder description for uploads/voice features */
        .input-placeholder-note {{
            font-size: 0.72rem;
            color: var(--text-dim);
            text-align: center;
            margin-top: 0.35rem;
            font-style: italic;
        }}

        /* =========================================================================
           11. Responsive Rules
           ========================================================================= */
        @media (max-width: 768px) {{
            .block-container {{
                padding: 1.5rem 1rem 7rem !important;
            }}
            .welcome-grid {{
                grid-template-columns: 1fr !important;
            }}
            .welcome-container {{
                padding: 1.5rem 0.5rem;
            }}
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
