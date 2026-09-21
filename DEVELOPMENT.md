# Developer Guide — NOVA AI Agent

This guide covers setting up, developing, testing, and debugging the NOVA AI Agent system locally.

---

## 1. Prerequisites

- **Python**: 3.12 or 3.13 (64-bit Windows)
- **Node.js**: v18.0+ and npm
- **Rust / Cargo**: (Optional, required only for native Tauri shell build)
- **Groq API Key**: Obtain from [https://console.groq.com](https://console.groq.com)

---

## 2. Environment Setup

### 2.1 Backend Setup
```powershell
# 1. Clone repository and navigate to root
cd C:\Users\<Username>\Desktop\agent\personal-ai-agent

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1

# 3. Install core dependencies
pip install -e ".[voice,browser,gui,dev]"

# 4. Configure environment variables
# Copy .env.example if available or edit .env:
# GROQ_API_KEY=gsk_...
# GROQ_MODEL=openai/gpt-oss-120b
# HOST=127.0.0.1
# PORT=8000
```

### 2.2 Desktop UI Setup
```powershell
# Navigate to desktop directory
cd desktop

# Install dependencies
npm install
```

---

## 3. Running Locally

### Option A: Running the Backend
From project root:
```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Check health:
- Liveness: `curl http://127.0.0.1:8000/health`
- Readiness: `curl http://127.0.0.1:8000/ready`
- Interactive API Docs: `http://127.0.0.1:8000/docs`

### Option B: Running the Desktop Frontend (Vite Dev Server)
From `desktop/` directory:
```powershell
npm run dev
```
Access the control center at `http://localhost:5173`.

### Option C: Voice Controller CLI
To run standalone voice loop:
```powershell
.venv\Scripts\python -m app.voice.voice_controller
```

---

## 4. Running Tests

### Python Backend Tests
Run the complete test suite:
```powershell
.venv\Scripts\pytest tests/ -v
```

Run specific test files:
```powershell
# Production resilience tests
.venv\Scripts\pytest tests/test_production_resilience.py -v

# 15 Operational scenario tests
.venv\Scripts\pytest tests/test_production_scenarios.py -v
```

### Desktop UI Build Validation
Verify TypeScript types and Vite production compilation:
```powershell
cd desktop
npm run build
```

---

## 5. Code Quality & Standards

- **Formatting & Linting**:
  ```powershell
  .venv\Scripts\ruff check app tests
  .venv\Scripts\ruff format app tests
  ```
- **Type Checking**:
  ```powershell
  .venv\Scripts\mypy app
  ```
- **Logging**:
  Always use `get_logger(__name__)`. Do not use plain `print()`. Extra fields passed via `extra={...}` are preserved in JSON logs.
