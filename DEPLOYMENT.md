# Deployment & Production Packaging Guide

This guide covers building, packaging, and installing NOVA AI Agent as a standalone Windows desktop application.

---

## 1. Production Architecture Overview

In production mode:
1. The **Python Backend** runs as a packaged background service or tray daemon listening on `127.0.0.1:8000`.
2. The **Desktop UI** runs inside a native Tauri window (or WebView2 wrapper) connecting to `http://127.0.0.1:8000` and `ws://127.0.0.1:8000/ws/events`.
3. If the backend is restarting or stopped, the desktop UI enters `● Backend Offline` mode without crashing and displays a `[ Reconnect ]` button.

---

## 2. Packaging the Python Backend

### 2.1 PyInstaller Standalone Executable
You can bundle the backend into a single executable `nova-backend.exe`:

```powershell
pip install pyinstaller

pyinstaller --noconfirm --onedir --windowed `
  --name "nova-backend" `
  --add-data "app;app" `
  --hidden-import "uvicorn" `
  --hidden-import "fastapi" `
  --hidden-import "groq" `
  --entrypoint "app/main.py"
```

### 2.2 Environment & Storage Directories
Ensure the following directories are configured on user machines:
- `%LOCALAPPDATA%\nova-agent\logs`
- `%LOCALAPPDATA%\nova-agent\tasks`
- `%LOCALAPPDATA%\nova-agent\memory`

These can be configured via environment variables:
```dos
NOVA_LOG_DIR=%LOCALAPPDATA%\nova-agent\logs
NOVA_MEMORY_FILE=%LOCALAPPDATA%\nova-agent\memory\short_term.json
```

---

## 3. Building the Desktop UI (Tauri / Vite)

### 3.1 Web Production Build
Generate optimized static production assets:
```powershell
cd desktop
npm run build
```
This generates the standalone SPA distribution under `desktop/dist/`.

### 3.2 Native Tauri Installer (.msi / .exe)
If building the native Windows desktop shell:
```powershell
cd desktop
npm run tauri build
```
The resulting MSI installer will be located in:
`desktop/src-tauri/target/release/bundle/msi/`

---

## 4. Windows Startup & Service Configuration

### Option A: Task Scheduler Auto-Start (Recommended)
Create a Windows Scheduled Task to launch the backend silently on user logon:
```powershell
$Action = New-ScheduledTaskAction -Execute "C:\Program Files\NOVA AI\nova-backend.exe"
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "NovaAIAgent" -Action $Action -Trigger $Trigger -Settings $Settings
```

### Option B: Windows Registry Run Key
Add the application to current user run key:
```powershell
New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
  -Name "NovaAIAgent" `
  -Value "C:\Program Files\NOVA AI\nova-backend.exe" `
  -PropertyType String -Force
```

---

## 5. Health Monitoring & Graceful Termination

- **Health Check Probe**: Monitor `GET http://127.0.0.1:8000/health`. Expect HTTP 200 `{"status": "ok"}`.
- **Readiness Probe**: Monitor `GET http://127.0.0.1:8000/ready`. Validates tool registry count, Groq API circuit state, and filesystem write access.
- **Graceful Shutdown**: Sending `SIGINT` or `SIGTERM` triggers the FastAPI `lifespan` shutdown handler:
  1. Stops active task pipelines.
  2. Closes Groq HTTP sessions cleanly.
  3. Disconnects connected WebSocket subscribers with code `1001` (Server shutdown).
  4. Flushes JSON log handlers and audit logs.
