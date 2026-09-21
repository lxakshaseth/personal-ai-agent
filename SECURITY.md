# Security Policy & Safeguards — NOVA AI Agent

Security is a foundational design constraint of the NOVA AI Agent project. Because the agent executes on personal workstations and interacts with the host operating system, rigorous safeguards are applied across all boundaries.

---

## 1. Zero Secret Leakage Policy

1. **API Keys & Credentials**:
   - `GROQ_API_KEY` is loaded exclusively from `.env` or system environment variables into memory on the backend.
   - It is **never** sent to the desktop UI, included in HTTP response bodies, or returned via status endpoints.
   - The desktop client only sees configured status (e.g. `api_key_configured: true`), never raw secret values.

2. **Automated Redaction Engine**:
   - The `app.utils.sanitizer` module provides recursive regex-based and key-based redaction:
     - Groq API keys (`gsk_...`)
     - OpenAI API keys (`sk-...`)
     - Bearer authorization headers and JWTs (`Bearer ...`, `eyJ...`)
     - Sensitive keys: `api_key`, `secret`, `password`, `token`, `cookie`, `session_id`, `private_key`.
   - **Log Redaction**: `_JSONFormatter` in `app.utils.logger` automatically passes every log record through the redaction engine before writing to disk or console.
   - **WebSocket Redaction**: Every broadcast event sent via `EventBus` passes through `sanitize_payload()` before serialization.

---

## 2. Path Security & Traversal Prevention

1. **Allowed Roots**:
   - Filesystem tools only operate within explicit whitelist directories configured in `settings.allowed_base_paths` (by default: `C:\Users`, `C:\Temp`).
2. **Path Traversal Protection**:
   - All input paths are resolved to their canonical real path via `Path(p).resolve()`.
   - Traversal attempts (e.g. `../../Windows/System32`, `..\..\..\AppData`) are immediately trapped and blocked.
3. **Protected System Directories**:
   - An immutable blocklist prevents modification or deletion of:
     - `C:\Windows`, `C:\Windows\System32`, `C:\Windows\SysWOW64`
     - `C:\Program Files`, `C:\Program Files (x86)`
     - `C:\ProgramData`, `C:\Recovery`, `C:\System Volume Information`
     - `C:\$Recycle.Bin`, `C:\boot`, `C:\EFI`
   - Attempting to target drive roots (e.g. `C:\`, `D:\`) raises `PathSecurityError`.

---

## 3. Sandboxed Execution & Input Validation

1. **Pydantic Validation**:
   - Every tool strictly enforces typed Pydantic models on all arguments before execution.
   - Missing, malformed, or extra parameters trigger immediate rejection.
2. **Terminal Shell Controls**:
   - Shell command execution via `run_command` enforces a strict allowlist of benign utilities.
   - Command chaining characters (`&`, `|`, `;`, `` ` ``), redirection operators (`>`, `<`), and arbitrary code interpreters (`python -c`, `powershell -enc`) are blocked.
   - The LLM's natural language output is **never** piped directly into a shell interpreter.
3. **Destructive Action Confirmation**:
   - Tools with `HIGH` permission levels (`delete_folder`, `delete_file`, `shutdown_computer`, `restart_computer`) cannot execute automatically.
   - The system pauses and generates a `ConfirmationTicket` with a 120-second TTL.
   - Execution only resumes if the user explicitly approves the action in the desktop UI.

---

## 4. Network & Local API Protections

1. **Loopback Binding**:
   - The FastAPI backend binds exclusively to `127.0.0.1` (localhost), preventing exposure to local area networks.
2. **Rate Limiting**:
   - An in-memory sliding-window limiter blocks rapid burst loops and DDoS-like loops (120 req/min default per IP).
   - Rejected requests receive `429 Too Many Requests` with a standard `Retry-After` header.
3. **Request ID Tracing**:
   - Every incoming request receives an `X-Request-ID` correlation header tracked via Python `contextvars`.
   - All structured logs, audit records, and error traces correlate to this ID for forensic review.

---

## 5. Reporting Security Issues

If you discover a potential vulnerability or security flaw, please do not open a public GitHub issue. Send a detailed report to the security team or maintainer with reproduction steps.
