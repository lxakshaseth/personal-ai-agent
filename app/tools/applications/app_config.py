"""
Application configuration — maps user-friendly names to executable paths.

Priority order for each app:
  1. Environment-specific overrides (future: from .env)
  2. Common Windows installation paths (checked in order, first one wins)
  3. PATH-based lookup via shutil.which()

To add a new app, add an entry to APP_DEFINITIONS with:
  - names: list of user-facing aliases (lowercased)
  - candidates: ordered list of absolute paths to check
  - url: optional fallback URL to open in browser instead of launching exe
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Current user home directory (expands %USERPROFILE%)
_HOME = Path.home()
_LOCALAPPDATA = Path(_HOME, "AppData", "Local")
_APPDATA = Path(_HOME, "AppData", "Roaming")


@dataclass
class AppDefinition:
    """Metadata for a launchable application."""

    names: list[str]                    # user-facing aliases (lowercase)
    candidates: list[str] = field(default_factory=list)  # exe paths to try
    protocol: str | None = None         # Windows URI scheme (e.g. "whatsapp:", "calc:", "spotify:")
    url: str | None = None              # browser fallback URL
    process_name: str | None = None     # for close_application (task name)
    cli_name: str | None = None         # command name in PATH (fallback)


APP_DEFINITIONS: list[AppDefinition] = [
    AppDefinition(
        names=["chrome", "google chrome"],
        candidates=[
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(_LOCALAPPDATA / "Google" / "Chrome" / "Application" / "chrome.exe"),
        ],
        url="https://www.google.com",
        process_name="chrome.exe",
        cli_name="chrome",
    ),
    AppDefinition(
        names=["vscode", "vs code", "visual studio code", "code"],
        candidates=[
            str(_LOCALAPPDATA / "Programs" / "Microsoft VS Code" / "Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
        ],
        process_name="Code.exe",
        cli_name="code",
    ),
    AppDefinition(
        names=["whatsapp", "whats app", "whatsapp desktop"],
        candidates=[
            str(_LOCALAPPDATA / "WhatsApp" / "WhatsApp.exe"),
            str(_APPDATA / "WhatsApp" / "WhatsApp.exe"),
            str(_LOCALAPPDATA / "Microsoft" / "WindowsApps" / "WhatsApp.exe"),
        ],
        protocol="whatsapp:",
        url="https://web.whatsapp.com",
        process_name="WhatsApp.exe",
        cli_name="whatsapp",
    ),

    AppDefinition(
        names=["terminal", "windows terminal", "wt"],
        candidates=[
            str(_LOCALAPPDATA / "Microsoft" / "WindowsApps" / "wt.exe"),
        ],
        process_name="WindowsTerminal.exe",
        cli_name="wt",
    ),
    AppDefinition(
        names=["notepad", "notepad.exe"],
        candidates=[
            r"C:\Windows\notepad.exe",
            r"C:\Windows\System32\notepad.exe",
        ],
        process_name="notepad.exe",
        cli_name="notepad",
    ),
    AppDefinition(
        names=["explorer", "file explorer", "windows explorer", "files"],
        candidates=[
            r"C:\Windows\explorer.exe",
        ],
        process_name="explorer.exe",
        cli_name="explorer",
    ),
    AppDefinition(
        names=["edge", "microsoft edge"],
        candidates=[
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        process_name="msedge.exe",
        cli_name="msedge",
    ),
    AppDefinition(
        names=["firefox", "mozilla firefox"],
        candidates=[
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ],
        process_name="firefox.exe",
        cli_name="firefox",
    ),
    AppDefinition(
        names=["spotify"],
        candidates=[
            str(_APPDATA / "Spotify" / "Spotify.exe"),
            str(_LOCALAPPDATA / "Microsoft" / "WindowsApps" / "Spotify.exe"),
        ],
        protocol="spotify:",
        process_name="Spotify.exe",
        cli_name="spotify",
    ),

    AppDefinition(
        names=["discord"],
        candidates=[
            str(_LOCALAPPDATA / "Discord" / "Update.exe"),
        ],
        process_name="Discord.exe",
        cli_name="discord",
    ),
    AppDefinition(
        names=["slack"],
        candidates=[
            str(_LOCALAPPDATA / "slack" / "slack.exe"),
        ],
        process_name="slack.exe",
        cli_name="slack",
    ),
    AppDefinition(
        names=["notion"],
        candidates=[
            str(_LOCALAPPDATA / "Programs" / "Notion" / "Notion.exe"),
        ],
        process_name="Notion.exe",
        cli_name="notion",
    ),
    AppDefinition(
        names=["teams", "microsoft teams"],
        candidates=[
            str(_LOCALAPPDATA / "Microsoft" / "Teams" / "current" / "Teams.exe"),
            str(_APPDATA / "Microsoft" / "Teams" / "current" / "Teams.exe"),
        ],
        process_name="Teams.exe",
        cli_name="teams",
    ),
    AppDefinition(
        names=["powershell", "ps"],
        candidates=[
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            r"C:\Program Files\PowerShell\7\pwsh.exe",
        ],
        process_name="powershell.exe",
        cli_name="powershell",
    ),
    AppDefinition(
        names=["cmd", "command prompt", "command line"],
        candidates=[
            r"C:\Windows\System32\cmd.exe",
        ],
        process_name="cmd.exe",
        cli_name="cmd",
    ),
    AppDefinition(
        names=["calculator", "calc"],
        candidates=[
            r"C:\Windows\System32\calc.exe",
            r"C:\Windows\calc.exe",
        ],
        process_name="CalculatorApp.exe",
        cli_name="calc",
    ),
    AppDefinition(
        names=["paint", "mspaint"],
        candidates=[
            r"C:\Windows\System32\mspaint.exe",
        ],
        process_name="mspaint.exe",
        cli_name="mspaint",
    ),
    AppDefinition(
        names=["youtube"],
        url="https://www.youtube.com",
    ),
    AppDefinition(
        names=["gmail"],
        url="https://mail.google.com",
    ),
    AppDefinition(
        names=["github"],
        url="https://github.com",
    ),
]

# ── Lookup index ───────────────────────────────────────────────────────────────

_APP_INDEX: dict[str, AppDefinition] = {}
for _app in APP_DEFINITIONS:
    for _alias in _app.names:
        _APP_INDEX[_alias.lower()] = _app


def find_app(query: str) -> AppDefinition | None:
    """Return the AppDefinition for *query* (case-insensitive), or None."""
    return _APP_INDEX.get(query.strip().lower())


import functools


@functools.lru_cache(maxsize=128)
def _resolve_cached(candidates: tuple[str, ...], cli_name: str | None) -> str | None:
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    # PATH fallback
    if cli_name:
        found = shutil.which(cli_name)
        if found:
            return found
    return None


def resolve_executable(app: AppDefinition) -> str | None:
    """
    Return the first existing executable path for *app*, or None.
    Falls back to shutil.which() using cli_name.
    Cached via LRU to prevent redundant filesystem lookups.
    """
    return _resolve_cached(tuple(app.candidates), app.cli_name)

