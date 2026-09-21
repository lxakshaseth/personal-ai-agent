# Troubleshooting & Diagnostics Guide — NOVA AI Agent

This guide covers diagnosing and resolving common operational issues with NOVA AI Agent.

---

## 1. Quick Diagnostics Checklist

| Symptom | Probable Cause | Quick Check / Resolution |
| :--- | :--- | :--- |
| **`● Backend Offline` in Desktop UI** | FastAPI backend is not running on port 8000 | Run `.venv\Scripts\python -m uvicorn app.main:app --port 8000` and click `[ Reconnect ]`. |
| **`Invalid or expired Groq API key`** | Missing or incorrect `GROQ_API_KEY` in `.env` | Verify key starts with `gsk_` in `.env` and restart backend. |
| **`Circuit breaker open` error** | External Groq API down or multiple 429 rate limits | Wait for 20s cooldown period; check Groq status page. |
| **`Access is denied: Path is outside allowed roots`** | Target directory not permitted by security policy | Configure `ALLOWED_BASE_PATHS` in `.env` to include your working folders. |
| **`No microphone detected. Using keyboard text mode.`** | Missing hardware audio device or sounddevice driver | Working as intended: agent gracefully falls back to text terminal input. |
| **`Application not found and could not be launched`** | Application executable is not in default path or PATH | Add custom exe path in `app/tools/applications/app_config.py` or install app. |

---

## 2. Common Issues & Solutions

### Issue 1: Groq API Authentication & Expired Keys
**Error in logs**:
```
Groq chat_completion_with_tools failed [invalid_api_key]: Invalid or expired Groq API key.
```
**Fix**:
1. Check your `.env` file in the project root:
   ```env
   GROQ_API_KEY=gsk_your_actual_key_here
   ```
2. Check that the key does not contain accidental leading/trailing spaces or quotes.
3. Test key using the readiness probe:
   ```powershell
   curl http://127.0.0.1:8000/ready
   ```

---

### Issue 2: Backend Offline / Desktop UI Connection Refused
**Symptoms**:
- Desktop header displays `● Backend Offline`.
- Reconnect button spins and remains disconnected.

**Fix**:
1. Verify whether Uvicorn is active on port 8000:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
   ```
2. If another process is occupying port 8000:
   ```powershell
   Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force
   ```
3. Start the backend:
   ```powershell
   .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Click `[ Reconnect ]` in the desktop UI.

---

### Issue 3: Path Traversal & Protected Directory Violations
**Error in response**:
```
PermissionDeniedError: Path 'C:\Windows\System32\cmd.exe' is in a protected system directory and cannot be modified.
```
**Reason**:
The agent enforces strict sandboxing rules to protect Windows system integrity.
- Never target `C:\Windows`, `C:\Program Files`, or drive roots like `C:\`.
- If you need the agent to manage files in a non-standard drive (e.g. `D:\Projects`), add it to `ALLOWED_BASE_PATHS` in `.env`:
  ```env
  ALLOWED_BASE_PATHS=["C:\\Users", "C:\\Temp", "D:\\Projects"]
  ```

---

### Issue 4: Rate Limiting (HTTP 429 Too Many Requests)
**Error**:
```json
{
  "error": "Rate limit exceeded. Try again in 12 seconds.",
  "retry_after": 12,
  "request_id": "req_8b91a27e"
}
```
**Fix**:
- The API applies a sliding-window rate limit (120 req/min). Wait the indicated `retry_after` seconds.
- The health endpoints `/health` and `/ready` are exempt from rate limiting and can always be polled.

---

### Issue 5: Audio Input / Microphone Fallback
**Console Notice**:
```
[Notice] No microphone detected. Using keyboard text mode.
```
**Explanation**:
NOVA AI includes automatic fallback detection. If no input recording device is detected (or when running over remote desktop sessions / VMs), the system automatically operates in interactive text prompt mode without throwing fatal exceptions.

---

## 3. Viewing Diagnostic Logs

Logs are formatted in structured JSON:
- Default log path: `logs/app.log`
- View recent log stream:
  ```powershell
  Get-Content logs/app.log -Tail 30
  ```
- All sensitive tokens and keys in logs are automatically redacted as `[REDACTED]`.
