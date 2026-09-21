# Personal AI Agent 🤖

A **production-oriented, voice-controlled AI agent** for Windows, powered by **Groq** (LLaMA 3.3 70B) and built with **FastAPI**.

> Give it natural-language commands — it plans and executes them on your computer.

---

## ✨ Example Commands

| Command | Tool Used |
|---|---|
| `"Open YouTube"` | `open_application` |
| `"Open VS Code"` | `open_application` |
| `"Create a folder called AI Projects"` | `create_folder` |
| `"Delete the test folder"` | `delete_folder` (HIGH — asks confirmation) |
| `"Open my Downloads folder"` | `open_folder` |
| `"Search YouTube for React tutorials"` | `browser_search` |

---

## 🏗️ Architecture

```
Voice Input → STT (Whisper)
                  ↓
            Natural Language Command
                  ↓
         GroqPlanner (LLaMA 3.3 70B)
         (function-calling + tool schemas)
                  ↓
         ToolExecutor
           ├── PermissionChecker
           ├── AuditLogger (JSONL)
           └── Tool.execute()
                  ↓
         Computer Control
         (subprocess / os.startfile / Playwright)
                  ↓
         TTS Response (pyttsx3)
```

### Key Design Principles

- **Clean Architecture** — Business logic in `agent/`, infrastructure in `services/`, `tools/`
- **Modular Tool Registry** — Add a tool by creating a class decorated with `@register_tool`
- **Permission Layer** — LOW / MEDIUM / HIGH risk levels; HIGH requires user confirmation
- **Audit Logging** — Every tool call is appended to `logs/audit.jsonl`
- **No hardcoded secrets** — Everything via Pydantic Settings + `.env`

---

## 📁 Project Structure

```
personal-ai-agent/
├── app/
│   ├── main.py              # FastAPI app factory + lifespan
│   ├── config/settings.py   # Pydantic Settings (env-based)
│   ├── api/routes/
│   │   ├── health.py        # GET /health
│   │   └── agent.py         # POST /agent/run, GET /agent/tools
│   ├── agent/
│   │   ├── base.py          # AbstractAgent interface
│   │   ├── planner.py       # GroqPlanner (LLM function-calling)
│   │   ├── executor.py      # ToolExecutor
│   │   └── agent.py         # PersonalAgent (concrete impl)
│   ├── tools/
│   │   ├── base.py          # AbstractTool + ToolResult
│   │   ├── registry.py      # ToolRegistry + @register_tool
│   │   └── impl/
│   │       ├── system.py    # open_application, open_folder, create_folder, delete_folder
│   │       └── browser.py   # browser_search, browser_open_url
│   ├── voice/
│   │   ├── stt.py           # SpeechToText ABC + WhisperSTT
│   │   └── tts.py           # TextToSpeech ABC + Pyttsx3TTS
│   ├── security/
│   │   ├── permissions.py   # PermissionChecker
│   │   └── audit.py         # AuditLogger (JSONL)
│   ├── memory/store.py      # MemoryStore ABC + InMemoryStore
│   ├── browser/automation.py # BrowserController (Playwright)
│   └── services/groq_client.py  # Async Groq wrapper
├── tests/
├── scripts/start.ps1
├── logs/
├── .env.example
├── requirements.txt
└── pyproject.toml
```

---

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.12+
- A Groq API key → [console.groq.com](https://console.groq.com)

### 2. Clone & set up

```powershell
cd personal-ai-agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure

```powershell
Copy-Item .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_...
```

### 4. Run

```powershell
uvicorn app.main:app --reload
# OR
.\scripts\start.ps1 -Reload
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## 🔌 API

### `GET /health`
```json
{"status": "ok", "service": "personal-ai-agent", "version": "0.1.0"}
```

### `POST /agent/run`
```json
// Request
{
  "command": "Search YouTube for React tutorials",
  "confirmed": false
}

// Response
{
  "success": true,
  "response": "Opened search results for 'React tutorials' on Youtube.",
  "tool_calls": [
    {
      "tool": "browser_search",
      "args": {"site": "youtube", "query": "React tutorials"},
      "success": true,
      "output": "Opened search results for 'React tutorials' on Youtube.",
      "error": null
    }
  ]
}
```

### `GET /agent/tools`
Lists all registered tools with their permission levels.

---

## 🛠️ Adding a New Tool

1. Create a file in `app/tools/impl/`
2. Subclass `AbstractTool` and decorate with `@register_tool`
3. Add the module path to `_TOOL_MODULES` in `app/tools/registry.py`

```python
from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.tools.registry import register_tool

@register_tool
class MyTool(AbstractTool):
    @property
    def name(self): return "my_tool"

    @property
    def description(self): return "Does something useful."

    @property
    def permission_level(self): return PermissionLevel.MEDIUM

    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        target = kwargs["target"]
        # ... do the thing ...
        return ToolResult(success=True, output=f"Done: {target}")
```

---

## 🔒 Security

| Feature | Implementation |
|---|---|
| No hardcoded secrets | Pydantic Settings + `.env` |
| Permission levels | LOW / MEDIUM / HIGH per tool |
| Confirmation gate | HIGH tools blocked unless `confirmed=true` |
| Path safety | Tools restricted to `ALLOWED_BASE_PATHS` |
| Audit log | Append-only `logs/audit.jsonl` |

---

## 🧪 Tests

```powershell
pytest tests/ -v
```

---

## 🗺️ Roadmap

- [ ] WhatsApp message sending (via Playwright)
- [ ] "Run my backend" tool (configurable project runner)
- [ ] Voice capture loop (sounddevice → Whisper → agent → pyttsx3)
- [ ] PostgreSQL conversation history
- [ ] Redis-backed session memory
- [ ] Electron / Tauri desktop UI
