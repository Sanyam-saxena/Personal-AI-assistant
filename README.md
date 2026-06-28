# AI Assistant Backend

A production-ready **FastAPI** backend for a local AI assistant.  
Proxies chat requests to a locally running **Ollama** instance using the **Qwen3** model.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Setup](#setup)
- [Running the Server](#running-the-server)
- [API Reference](#api-reference)
- [Example Requests](#example-requests)
- [Configuration Reference](#configuration-reference)
- [Error Codes](#error-codes)
- [Log Format](#log-format)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.11 + | `python --version` |
| pip | latest | `pip install --upgrade pip` |
| [Ollama](https://ollama.ai/) | latest | must be running locally |
| Qwen3 model | — | `ollama pull qwen3` |

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                   # App factory, lifespan, global error handler
│   ├── core/
│   │   ├── config.py             # Settings (pydantic-settings + .env)
│   │   └── exceptions.py         # Domain exception hierarchy (single source of truth)
│   ├── middleware/
│   │   └── request_id.py         # Correlation ID, timing, access log, security headers
│   ├── models/
│   │   └── schemas.py            # Pydantic request / response models
│   ├── routes/
│   │   └── chat.py               # GET /health  GET /ready  POST /chat
│   ├── services/
│   │   └── ollama_service.py     # Pooled HTTP client for Ollama /api/generate
│   └── utils/
│       └── logger.py             # configure_logging(), RequestIDFilter, ContextVar
├── .gitignore                    # Prevents .env, __pycache__, venv from being committed
├── .env.example                  # Template — safe to commit
├── .env                          # Your local config — never commit this
├── requirements.txt
└── README.md
```

---

## Installation

### 1 — Navigate to the project directory

```bash
cd backend
```

### 2 — Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv venv && source venv/bin/activate

# Windows (PowerShell)
python -m venv venv && .\venv\Scripts\Activate.ps1
```

### 3 — Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Setup

### 1 — Configure environment variables

```bash
cp .env.example .env
```

The defaults in `.env.example` work without modification if Ollama runs on `localhost:11434`.  
See [Configuration Reference](#configuration-reference) for all options.

> ⚠ Never commit `.env` to version control. The included `.gitignore` prevents this.

### 2 — Pull the model and start Ollama

```bash
# First time only — downloads ~4 GB
ollama pull qwen3

# Start the Ollama server (listens on port 11434 by default)
ollama serve
```

---

## Running the Server

### Development (hot-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Expected startup output

```
2025-01-15 10:30:00 | INFO     | -------- | app.main | ==========================================================
2025-01-15 10:30:00 | INFO     | -------- | app.main |   AI Assistant Backend — starting up
2025-01-15 10:30:00 | INFO     | -------- | app.main | ==========================================================
2025-01-15 10:30:00 | INFO     | -------- | app.main |   Version           : 1.0.0
2025-01-15 10:30:00 | INFO     | -------- | app.main |   Ollama URL        : http://localhost:11434
2025-01-15 10:30:00 | INFO     | -------- | app.main |   Ollama model      : qwen3
2025-01-15 10:30:00 | INFO     | -------- | app.main |   Connect timeout   : 10s
2025-01-15 10:30:00 | INFO     | -------- | app.main |   Read timeout      : 60s
2025-01-15 10:30:00 | INFO     | -------- | app.main |   OpenAPI docs      : enabled  → /docs
2025-01-15 10:30:00 | INFO     | -------- | app.main |   CORS origins      : ['*']
```

Interactive API docs are at **<http://localhost:8000/docs>**

---

## API Reference

### `GET /health` — Liveness probe

Returns `200 OK` as long as the API process is alive.  
Does **not** ping Ollama — use `/ready` for that.

```json
{ "status": "healthy" }
```

---

### `GET /ready` — Readiness probe

Performs a lightweight probe against Ollama.  
Returns `200` when Ollama is reachable; `503` when it is not.  
Use this endpoint with container orchestrators (Kubernetes, Docker Swarm) to
stop routing traffic to instances that have lost their Ollama connection.

**200 OK**
```json
{ "status": "ready", "ollama": "reachable" }
```

**503 Service Unavailable**
```json
{ "detail": "Ollama is unreachable. Ensure the server is running: `ollama serve`" }
```

---

### `POST /chat` — Chat with the AI assistant

**Request body**

| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `message` | string | ✅ | 1 – 8 192 chars | The user's message |

```json
{ "message": "Explain the Turing test." }
```

**200 OK**
```json
{ "response": "The Turing test, proposed by Alan Turing in 1950…" }
```

**Error responses** — all share the shape `{ "detail": "…" }`

| Status | Meaning |
|---|---|
| `422` | Validation error — bad request body |
| `500` | Internal server error |
| `502` | Ollama returned an unexpected response |
| `503` | Ollama is unreachable |
| `504` | Ollama timed out |

---

## Example Requests

### cURL

```bash
# Liveness check
curl -X GET http://localhost:8000/health

# Readiness check
curl -X GET http://localhost:8000/ready

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?"}'
```

### Python (`requests`)

```python
import requests

BASE = "http://localhost:8000"

# Liveness
print(requests.get(f"{BASE}/health").json())

# Readiness
r = requests.get(f"{BASE}/ready")
if r.status_code == 503:
    print("Ollama is not running!")

# Chat
r = requests.post(f"{BASE}/chat", json={"message": "Tell me a joke."})
r.raise_for_status()
print(r.json()["response"])
```

### JavaScript (`fetch`)

```js
const r = await fetch("http://localhost:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: "Explain machine learning." }),
});
const data = await r.json();
console.log(data.response);
```

---

## Configuration Reference

All values are loaded from `.env` (real environment variables take priority).

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Base URL of the Ollama server |
| `OLLAMA_MODEL` | `qwen3` | Model tag for generation |
| `OLLAMA_CONNECT_TIMEOUT` | `10` | TCP handshake timeout (seconds) — detects "Ollama is down" quickly |
| `OLLAMA_READ_TIMEOUT` | `60` | Full response timeout (seconds) — accommodate slow generation |
| `APP_TITLE` | `AI Assistant Backend` | Title shown in OpenAPI docs |
| `APP_VERSION` | `1.0.0` | Semantic version string |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `CORS_ORIGINS` | `*` | `"*"` or comma-separated origins (e.g. `https://a.com,https://b.com`) |
| `OPENAPI_ENABLED` | `true` | `false` in production to hide `/docs`, `/redoc`, `/openapi.json` |

> **CORS note:** When `CORS_ORIGINS=*`, the server automatically sets `allow_credentials=false`.
> The Fetch specification forbids credentialed cross-origin requests to wildcard origins —
> browsers silently discard such responses. To enable cookies or `Authorization` headers,
> set an explicit origin list and `allow_credentials` will be enabled automatically.

---

## Error Codes

| HTTP | Exception | Cause |
|---|---|---|
| `422` | `ValidationError` | Request body failed schema validation |
| `500` | `Exception` | Unhandled server error |
| `502` | `OllamaResponseError` | Ollama returned HTTP 4xx/5xx or invalid JSON |
| `503` | `OllamaConnectionError` | TCP connection to Ollama failed |
| `504` | `OllamaTimeoutError` | Ollama exceeded `OLLAMA_READ_TIMEOUT` |

---

## Log Format

Every log line carries a **request correlation ID** (first 8 characters of the UUID4
assigned by `RequestIDMiddleware`) so you can grep all lines for a single request:

```
YYYY-MM-DD HH:MM:SS | LEVEL    | req-id   | module.name | message
```

Example for a successful chat request:

```
2025-01-15 10:31:05 | INFO     | -------- | app.main | OllamaService ready | model=qwen3 | …
2025-01-15 10:31:12 | INFO     | a3f7c291 | app.services.ollama_service | Ollama ← | tokens=89 | 7123ms
2025-01-15 10:31:12 | INFO     | a3f7c291 | app.middleware.request_id | POST /chat → 200 | 7134ms
```

The `--------` placeholder appears on startup/shutdown lines where no request is active.

---

## Troubleshooting

### `503` — Cannot connect to Ollama

```bash
ollama serve                             # start Ollama
curl http://localhost:11434/api/tags     # verify it's listening
```

Check `OLLAMA_URL` in `.env` if you're running Ollama on a non-default port.

### `502` — Model not found

```bash
ollama pull qwen3    # pull the model
ollama list          # verify it appears
```

If using a different model, update `OLLAMA_MODEL` in `.env`.

### `504` — Gateway timeout

Increase `OLLAMA_READ_TIMEOUT` in `.env`.  
The first request after starting Ollama is slower because the model loads into RAM.

### `422` — Validation error

Ensure the request body is `{"message": "…"}` (not `"prompt"` or `"text"`).  
`message` must be a non-empty string with at most 8 192 characters.

### Double log lines in output

Set `LOG_LEVEL=WARNING` for `uvicorn.access` to suppress Uvicorn's built-in access log.  
`RequestIDMiddleware` already provides richer access logging; both running simultaneously
produces duplicate lines.  The application's `configure_logging()` silences
`uvicorn.access` automatically.

---

## Production Hardening and Security

When deploying to production, follow these security best practices:

### 1. Reverse Proxy (SSRF, Slowloris, SSL/TLS)
Always run the application behind a production-grade reverse proxy (e.g., Nginx, Caddy, or an AWS Application Load Balancer).
- **SSL/TLS Termination**: Keep-alive and SSL/TLS should be terminated at the reverse proxy.
- **Slowloris DoS Mitigation**: Enforce client connection write/read timeouts at the proxy level.
- **SSRF Prevention**: If deploying the frontend, configure the `ENVIRONMENT=production` variable. This triggers strict URL checking in the API client to reject internal IP schemas (RFC 1918) and loopback interfaces.

### 2. Rate Limiting behind Proxies
If deploying behind a reverse proxy (like Cloudflare or Nginx), you must configure `TRUSTED_PROXIES` in the backend's `.env` (or environment variables) to be the IP address(es) of your proxy servers.
This ensures client rate limiting correctly uses the original client IP from `X-Forwarded-For` rather than the proxy's IP, while preventing clients from spoofing their IPs.

