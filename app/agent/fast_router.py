"""
Fast Deterministic Intent Router for NOVA AI.

Routes common, unambiguous commands and greetings directly to tool execution or
instant conversational responses WITHOUT spending an LLM round trip (~0-5ms latency).
For ambiguous, natural language, or multi-step requests, falls back to Groq.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ResponseMode(str, Enum):
    CHAT = "CHAT"
    COMMAND = "COMMAND"
    TASK = "TASK"


@dataclass
class FastRouteMatch:
    matched: bool
    mode: ResponseMode = ResponseMode.COMMAND
    tool_name: Optional[str] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    direct_response: Optional[str] = None
    conversational_prefix: Optional[str] = None


# Common website shortcuts
WEBSITE_MAP: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitter": "https://twitter.com",
    "x": "https://x.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "amazon": "https://www.amazon.com",
    "linkedin": "https://www.linkedin.com",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://www.wikipedia.org",
    "whatsapp": "https://web.whatsapp.com",
}

# Common desktop applications
APP_MAP: dict[str, str] = {
    "chrome": "Chrome",
    "google chrome": "Chrome",
    "vs code": "VS Code",
    "vscode": "VS Code",
    "code": "VS Code",
    "visual studio code": "VS Code",
    "notepad": "Notepad",
    "calculator": "Calculator",
    "calc": "Calculator",
    "file explorer": "Explorer",
    "explorer": "Explorer",
    "terminal": "Terminal",
    "powershell": "PowerShell",
    "cmd": "Command Prompt",
    "command prompt": "Command Prompt",
    "paint": "Paint",
    "spotify": "Spotify",
    "task manager": "Task Manager",
    "whatsapp": "WhatsApp",
    "whats app": "WhatsApp",
}

# Conversational greetings & pleasantries (CHAT mode)
GREETINGS_RESPONSES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"^(?:hi|hey|hello|yo|howdy)(?:\s+nova|\s+there|\s+assistant)?[.!]?$", re.I),
        "Hey! What can I help you with?",
    ),
    (
        re.compile(r"^(?:good\s+(?:morning|afternoon|evening))(?:\s+nova)?[.!]?$", re.I),
        "Good day! How can I assist you today?",
    ),
    (
        re.compile(r"^(?:who\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do)[?.]?$", re.I),
        "I am NOVA, your Windows AI desktop assistant. I can open apps, search websites, manage files, and control your system.",
    ),
    (
        re.compile(r"^(?:how\s+are\s+you|how's\s+it\s+going|how\s+are\s+things)[?.]?$", re.I),
        "All systems operational and ready. What would you like to do?",
    ),
    (
        re.compile(r"^(?:thanks|thank\s+you|thx)(?:\s+nova)?[.!]?$", re.I),
        "You're very welcome! Let me know if you need anything else.",
    ),
    (
        re.compile(
            r"^(?:end|stop|exit|quit|bye|goodbye|good\s+bye|stop\s+listening|end\s+listening|"
            r"stop\s+conversation|end\s+conversation|khatam|khatam\s+karo|band\s+karo|alvida)[.!]?$",
            re.I,
        ),
        "Goodbye! Voice session ended.",
    ),
]

EXIT_COMMAND_PATTERN = re.compile(
    r"^(?:end|stop|exit|quit|bye|goodbye|good\s+bye|stop\s+listening|end\s+listening|"
    r"stop\s+conversation|end\s+conversation|khatam|khatam\s+karo|band\s+karo|alvida)[.!]?$",
    re.I,
)


def is_exit_command(text: str) -> bool:
    """Check if the given command is an exit / end conversation command."""
    return bool(EXIT_COMMAND_PATTERN.match(text.strip().lower()))


def parse_whatsapp_intent(command: str) -> Optional[tuple[str, str]]:
    """Extract contact and message from natural language WhatsApp commands."""
    cmd = command.strip()
    m = re.match(
        r"^(?:open\s+whatsapp\s+(?:and\s+)?(?:message|text|send\s+message\s+to)|send\s+(?:a\s+)?whatsapp(?:\s+message)?\s+to|whatsapp)\s+([a-zA-Z0-9_\+]+)(?:\s+(?:saying|with\s+message|message)?\s*(.*))?$",
        cmd,
        re.I,
    )
    if m:
        contact = m.group(1).strip()
        msg = (m.group(2) or "").strip() or "Hello"
        return contact, msg

    m = re.match(
        r"^(?:message|text|send\s+message\s+to)\s+([a-zA-Z0-9_\+]+)\s+(?:on|via)\s+whatsapp(?:\s+(?:saying|with\s+message)?\s*(.*))?$",
        cmd,
        re.I,
    )
    if m:
        contact = m.group(1).strip()
        msg = (m.group(2) or "").strip() or "Hello"
        return contact, msg

    return None


class FastRouter:
    """
    Lightweight intent router evaluated prior to Groq LLM planning.
    """

    @classmethod
    def match(cls, command: str) -> FastRouteMatch:
        cmd = command.strip().lower()
        if not cmd:
            return FastRouteMatch(matched=False)

        # ── 0a. WhatsApp Instant Actions (0ms bypass) ─────────────────────────
        wa_intent = parse_whatsapp_intent(command)
        if wa_intent:
            contact, msg = wa_intent
            prefix = f"Opening WhatsApp to message {contact}." if msg == "Hello" else f"Sending WhatsApp message to {contact}: \"{msg}\"."
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="send_whatsapp_message",
                arguments={"contact": contact, "message": msg},
                conversational_prefix=prefix,
            )

        # ── 0b. Multi-step or combined commands must go to Supervisor / LLM ───
        if re.search(r"\b(?:and\s+then|then|and\s+also|after\s+that)\b", cmd) or "," in cmd or ";" in cmd:
            return FastRouteMatch(matched=False)

        # ── 1. Pure Chat / Greetings (0ms latency, warm & conversational) ─────
        for pattern, reply in GREETINGS_RESPONSES:
            if pattern.match(cmd):
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.CHAT,
                    direct_response=reply,
                )

        # ── 2. Open Special Folders: "open downloads", "open desktop" ─────────
        if re.search(r"^(?:open|show)\s+downloads$", cmd):
            downloads = str(Path.home() / "Downloads")
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="open_folder",
                arguments={"folder_path": downloads},
                conversational_prefix="Opening your Downloads folder.",
            )

        # ── 3. Screen Capture ─────────────────────────────────────────────────
        if re.search(r"^(?:take\s+(?:a\s+)?screenshot|capture\s+(?:the\s+)?screen|screenshot)$", cmd):
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="take_screenshot",
                arguments={},
                conversational_prefix="Taking a screenshot now.",
            )

        # ── 5. System Stats (CPU, RAM, Info) ──────────────────────────────────
        if re.search(r"^(?:system\s+info|system\s+information|pc\s+info)$", cmd):
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="system_information",
                arguments={},
                conversational_prefix="Checking system information.",
            )

        if re.search(r"^(?:cpu(?:\s+usage)?|check\s+cpu)$", cmd):
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="cpu_usage",
                arguments={},
                conversational_prefix="Checking CPU usage.",
            )

        if re.search(r"^(?:memory(?:\s+usage)?|ram(?:\s+usage)?)$", cmd):
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="memory_usage",
                arguments={},
                conversational_prefix="Checking memory usage.",
            )

        # ── 6. Lock Workstation ───────────────────────────────────────────────
        if re.search(r"^(?:lock\s+(?:the\s+)?(?:computer|pc|screen|workstation)|lock)$", cmd):
            return FastRouteMatch(
                matched=True,
                mode=ResponseMode.COMMAND,
                tool_name="lock_computer",
                arguments={},
                conversational_prefix="Locking your computer.",
            )

        # ── 6. YouTube Searches: "search youtube for [query]" or "find [query] on youtube" ─
        yt_search_match = re.search(
            r"^(?:search\s+youtube\s+for|find\s+(.+?)\s+on\s+youtube|play\s+(.+?)\s+on\s+youtube)\s*(.*)$",
            cmd,
        )
        if yt_search_match:
            # Extract query
            groups = [g for g in yt_search_match.groups() if g]
            query = " ".join(groups).strip()
            if query:
                encoded_q = query.replace(" ", "+")
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.COMMAND,
                    tool_name="open_url",
                    arguments={"url": f"https://www.youtube.com/results?search_query={encoded_q}"},
                    conversational_prefix=f"Searching YouTube for {query}.",
                )

        # ── 7. Open Website / URL: "open youtube", "open youtube in chrome" ────
        open_site_match = re.search(r"^(?:open|launch|go\s+to|visit)\s+([a-z0-9\.\-\_]+)(?:\s+(?:in|on)\s+(?:chrome|browser|edge))?[.!]?$", cmd)
        if open_site_match:
            target = open_site_match.group(1).lower()

            # Known shortcut?
            if target in WEBSITE_MAP:
                url = WEBSITE_MAP[target]
                name_cap = target.capitalize()
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.COMMAND,
                    tool_name="open_url",
                    arguments={"url": url},
                    conversational_prefix=f"Sure, opening {name_cap}.",
                )

            # Is it a domain like example.com?
            if re.match(r"^[a-z0-9\-]+\.(?:com|org|net|io|dev|app|ai|edu|gov|co|in)$", target):
                url = f"https://{target}"
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.COMMAND,
                    tool_name="open_url",
                    arguments={"url": url},
                    conversational_prefix=f"Opening {target}.",
                )

        # ── 8. Open Known Applications: "open notepad", "open chrome", "open vs code" ─
        open_app_match = re.search(r"^(?:open|launch|start|run)\s+([a-z0-9\s]+?)(?:\s+application|\s+app)?[.!]?$", cmd)
        if open_app_match:
            app_query = open_app_match.group(1).strip().lower()
            if app_query in APP_MAP:
                app_name = APP_MAP[app_query]
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.COMMAND,
                    tool_name="open_application",
                    arguments={"app_name": app_name},
                    conversational_prefix=f"Sure, opening {app_name}.",
                )

        # ── 9. Simple Folder Creation: "create a folder called AI Projects" ─────
        # (Only if single action; complex commands with "and" go to Supervisor)
        if not re.search(r"\b(?:and|then|also)\b", cmd):
            folder_match = re.search(
                r"^(?:create|make)\s+(?:a\s+)?folder\s+(?:called\s+|named\s+)?['\"]?([a-zA-Z0-9_\-\s]+?)['\"]?(?:\s+(?:on|in)\s+(?:the\s+|my\s+)?(desktop|downloads|documents))?[.!]?$",
                cmd,
            )
            if folder_match:
                raw_folder_name = folder_match.group(1).strip().strip("'\"")
                loc_param = (folder_match.group(2) or "").lower()

                # Clean any lingering location suffixes inside the name
                for suffix, loc_target in [
                    (r"\s+on\s+(?:the\s+|my\s+)?desktop$", "desktop"),
                    (r"\s+in\s+(?:the\s+|my\s+)?downloads$", "downloads"),
                    (r"\s+in\s+(?:the\s+|my\s+)?documents$", "documents"),
                ]:
                    if re.search(suffix, raw_folder_name, re.I):
                        raw_folder_name = re.sub(suffix, "", raw_folder_name, flags=re.I).strip()
                        loc_param = loc_target
                        break

                if raw_folder_name:
                    if loc_param == "downloads":
                        base_dir = Path.home() / "Downloads"
                    elif loc_param == "documents":
                        base_dir = Path.home() / "Documents"
                    else:
                        base_dir = Path.home() / "Desktop"

                    target_path = str(base_dir / raw_folder_name) if base_dir.exists() else str(Path.home() / raw_folder_name)
                    return FastRouteMatch(
                        matched=True,
                        mode=ResponseMode.COMMAND,
                        tool_name="create_folder",
                        arguments={"folder_path": target_path},
                        conversational_prefix=f"Done. I created the folder {raw_folder_name}.",
                    )

            # ── 10. Simple File Creation: "create file test.txt in C:/... with content 'xyz'" ─
            file_match = re.search(
                r"^(?:create|make|write)\s+(?:a\s+)?file\s+['\"]?([a-zA-Z0-9_\-\.]+)['\"]?\s+(?:in|at)\s+['\"]?([a-zA-Z0-9_\-\.:/\\\s]+?)['\"]?(?:\s+with\s+content\s+['\"]?(.*?)['\"]?)?[.!]?$",
                command.strip(),
                re.IGNORECASE,
            )
            if file_match:
                filename = file_match.group(1).strip()
                folder_part = file_match.group(2).strip().strip("'\"")
                content = (file_match.group(3) or "").strip().strip("'\"")
                target_path = str(Path(folder_part) / filename)
                return FastRouteMatch(
                    matched=True,
                    mode=ResponseMode.COMMAND,
                    tool_name="create_file",
                    arguments={"file_path": target_path, "content": content},
                    conversational_prefix=f"Done. I created the file {filename}.",
                )

        # No fast-path match -> pass to Groq LLM
        return FastRouteMatch(matched=False)
