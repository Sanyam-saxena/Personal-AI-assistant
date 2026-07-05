# Sam AI Assistant Frontend

A production-quality **Streamlit** frontend interface for the Sam AI Assistant, proxying requests to the backend.

---

## Features

- **ChatGPT-like UI**: Implements a clean, responsive, and visually appealing chat thread with message histories.
- **State Management**: Persists chat history in `st.session_state` to prevent data loss on re-renders.
- **Sidebar Diagnostics**: Shows real-time connection status (liveness checks), current model information, and message counters.
- **Robust API Client**: Integrates retry mechanisms with exponential backoff and timeout handling.
- **Theme-aware Styling**: Styled with a Glassmorphism/Zinc color scheme suitable for both light and dark modes.

---

## Project Structure

```
frontend/
├── app.py                # Main app entrypoint, layout, and event orchestration
├── assets/
│   └── README.md         # Documentation for reserved static branding assets
├── config/
│   ├── constants.py      # User-facing string configurations
│   └── theme.py          # Reusable UI colors and design tokens configuration
├── components/
│   ├── __init__.py       # Component imports and architectural placeholders
│   ├── custom_css.py     # HTML/CSS injection styles
│   ├── sidebar.py        # Sidebar widgets (health checks, stats, actions)
│   ├── header.py         # App header brand layout and theme toggling
│   ├── message_renderer.py # Chat message renderer
│   ├── chat_window.py    # Conversation history display stream
│   ├── input_box.py      # Chat query input box
│   └── status.py         # Backend connection warning alert UI
├── services/
│   └── api_client.py     # Type-hinted API Client communicating with FastAPI
├── utils/
│   └── logger.py         # Formatted logger configuration
├── .streamlit/
│   └── config.toml       # Streamlit theme parameters
└── requirements.txt      # Python package requirements
```

---

## Installation & Setup

### 1 — Navigate to the frontend directory
```bash
cd frontend
```

### 2 — Install dependencies
Ensure your virtual environment is active, then run:
```bash
pip install -r requirements.txt
```

### 3 — Configure Environment Variables
You can specify the backend service URL through the `BACKEND_URL` environment variable:
```bash
# Windows (PowerShell)
$env:BACKEND_URL="http://localhost:8000"

# macOS / Linux
export BACKEND_URL="http://localhost:8000"
```
If not specified, the client defaults to `http://localhost:8000`.

### 4 — Run the Application
Start the Streamlit application:
```bash
streamlit run app.py
```
By default, the application will be accessible at **<http://localhost:8501>**
