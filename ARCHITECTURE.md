# Architecture Overview — NOVA AI Agent

NOVA AI is a Windows-native desktop artificial intelligence computer agent. It pairs a high-performance **FastAPI** Python backend with a **React + TypeScript + Tailwind CSS** desktop application (with **Tauri** desktop shell integration).

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DESKTOP USER INTERFACE                           │
│  React 18 • TypeScript • Tailwind CSS • Lucide Icons • Tauri Native Shell    │
│                                                                             │
│  [ Dashboard / Control Center ]   [ Live Chat ]     [ Voice Interface ]     │
│  [ Real-Time Timeline ]           [ Plan Approvals] [ Confirmation Dialog ] │
│  [ Task & Pipeline Manager ]      [ Memory CRUD ]   [ System Telemetry ]    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / JSON (Port 8000)
                                       │ WebSocket Bi-Directional (/ws/events)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                           LOCAL BACKEND API LAYER                            │
│  FastAPI (Uvicorn) • Request-ID Correlation • Sliding-Window Rate Limiter   │
│  Global Exception Sanitizer • CORS Enforcement • Structured JSON Logging    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                                 AGENT CORE                                  │
│                                                                             │
│                     ┌────────────────────────────────┐                      │
│                     │        SUPERVISOR AGENT        │                      │
│                     │   Task Decomposition & Plan    │                      │
│                     └───────┬──────────────┬─────────┘                      │
│                             │              │                                │
│              ┌──────────────┴──────┐ ┌─────┴────────────────┐               │
│              │   Computer Agent    │ │    Browser Agent     │               │
│              │ (Apps, OS, Windows) │ │ (Navigation, Search) │               │
│              ├─────────────────────┤ ├──────────────────────┤               │
│              │     File Agent      │ │ Communication Agent  │               │
│              │ (I/O, Safe Paths)   │ │  (WhatsApp, Messages)│               │
│              └─────────────────────┘ └──────────────────────┘               │
│                                     │                                       │
│                        ┌────────────┴───────────┐                           │
│                        │      System Agent      │                           │
│                        │   (Telemetry & Info)   │                           │
│                        └────────────────────────┘                           │
│                                                                             │
│  • GroqPlanner (Function-calling with Groq API, Circuit Breaker, Retries)    │
│  • TaskManager (8-State lifecycle: Created → Planning → Approval → Running) │
│  • ConfirmationManager (TTL Tickets for High-Risk Destructive Operations)    │
│  • EventBus (Pub/Sub Event Streaming with Real-Time Sanitization)            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                         UNIFIED TOOL REGISTRY & SANDBOX                     │
│                                                                             │
│  ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────┐  │
│  │   Filesystem Tools    │ │   Application Tools   │ │   Windows Tools   │  │
│  │  create/delete/move/  │ │  open_app, close_app  │ │  open_url, lock,  │  │
│  │  search (Non-blocking)│ │  (LRU Cached Paths)   │ │  screenshot       │  │
│  └───────────────────────┘ └───────────────────────┘ └───────────────────┘  │
│  ┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────┐  │
│  │     System Tools      │ │    Terminal Tools     │ │    Voice Tools    │  │
│  │  cpu, memory, disk,   │ │  run_command          │ │  Whisper (STT)    │  │
│  │  processes            │ │  (Strict Allowlist)   │ │  TTS Engine       │  │
│  └───────────────────────┘ └───────────────────────┘ └───────────────────┘  │
│                                                                             │
│  Security Layer: Path Validator • Protected Dirs • Zero Secret Leakage      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Subsystems

### 2.1 Supervisor Agent & Specialist Workers
Tasks are evaluated by the **Supervisor Agent** to determine whether single-step execution or multi-step hierarchical orchestration is required:
1. **Simple Tasks**: Direct single-tool resolution via GroqPlanner function-calling.
2. **Complex Multi-Step Tasks**: Decomposed into formal `PlanStep`s assigned to specialist workers:
   - `Browser Agent`: Web search, video lookup, documentation navigation.
   - `Computer Agent`: Win32 application launching, window control, screen capture.
   - `File Agent`: Validated directory and file operations.
   - `Communication Agent`: Messaging and contact actions.
   - `System Agent`: Real-time hardware telemetry and diagnostic reports.

### 2.2 Groq Client & Circuit Breaker
- **GroqClient**: Powered by Groq models (e.g. `openai/gpt-oss-120b`, `llama-3.3-70b-versatile`).
- **Resilience Policy**:
  - 25-second HTTP request timeout.
  - Exponential backoff with random jitter on rate-limits (429) and transient network/server errors (500, 502, 503, 504).
  - **Circuit Breaker**: Automatically transitions through `CLOSED` → `OPEN` → `HALF_OPEN`. Protects against repeated cascade failures and prevents API quota exhaustion when external services degrade.

### 2.3 Middleware Stack
The FastAPI gateway applies production-grade middleware in a robust onion wrapper:
1. **CORSMiddleware**: Ensures all responses (including errors) permit local origins.
2. **RequestIDMiddleware**: Inspects incoming `X-Request-ID` or generates a unique correlation ID (`req_<hex>`), sets Python `contextvars` for thread/async propagation, and attaches the header to responses.
3. **GlobalExceptionMiddleware**: Traps unhandled exceptions, maps custom domain errors (`PermissionDeniedError`, `ToolNotFoundError`, `AgentBaseError`), redacts sensitive payloads, and yields structured JSON error envelopes.
4. **RateLimitMiddleware**: Sliding-window in-memory rate limiter protecting REST endpoints (120 requests/minute default per client IP), with automatic exemptions for health checks (`/health`, `/ready`) and WebSockets.

### 2.4 Real-Time Event Stream (`/ws/events`)
Bi-directional WebSocket streaming between UI and agent:
- Emits lifecycle events: `agent.started`, `agent.listening`, `agent.thinking`, `agent.planning`, `tool.started`, `tool.completed`, `confirmation.requested`, `confirmation.resolved`, `task.cancelled`.
- Enforces data sanitization at the pub/sub boundary, guaranteeing credentials, keys (`gsk_...`), bearer tokens, and passwords are never transmitted over the wire.
- Provides initial snapshot on connect or reconnect, including agent state, recent timeline events, and active confirmation tickets.

### 2.5 Security & Sandbox
- **Path Security Validator**: Enforces boundaries against allowed root directories (`C:\Users`, `C:\Temp`). Blocks drive roots (`C:\`), parent traversal (`../../`), and protected system paths (`C:\Windows`, `C:\Program Files`, etc.).
- **Interactive Confirmations**: High-risk operations (`delete_folder`, `delete_file`, `shutdown_computer`, `restart_computer`) create a `ConfirmationTicket` with a strict TTL. Execution is suspended until approved in the desktop UI.
- **Terminal Execution Controls**: Terminal tool enforces a strict command allowlist and rejects shell metacharacter chaining (`&`, `|`, `;`, `` ` ``).
