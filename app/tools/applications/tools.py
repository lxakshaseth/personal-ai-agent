"""
Application tools — open and close desktop applications on Windows.

Registered tools:
  open_application   MEDIUM  launch an app by name or open its URL fallback
  close_application  HIGH    terminate an application's process(es)
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import urllib.parse
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agent.tool_registry import register_tool
from app.tools.applications.app_config import find_app, resolve_executable
from app.tools.base import AbstractTool, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)


class _OpenAppInput(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name or alias of the application to open")


class _CloseAppInput(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name of the application to close")
    force: bool = Field(default=False, description="Force-kill the process if it doesn't close gracefully")


@register_tool
class OpenApplicationTool(AbstractTool):
    """Launch a desktop application or open its web equivalent."""

    input_model = _OpenAppInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "open_application"
    @property
    def description(self) -> str:
        return (
            "Open an application on Windows. "
            "Supports: Chrome, VS Code, WhatsApp, Windows Terminal, Notepad, "
            "File Explorer, Edge, Firefox, Spotify, Discord, Slack, Notion, Teams, "
            "PowerShell, CMD, Calculator, Paint, YouTube, Gmail, GitHub, and more. "
            "Use when the user says 'open X' or 'launch X'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Application name (e.g. 'Chrome', 'VS Code', 'WhatsApp')",
                },
            },
            "required": ["app_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        app_name: str = kwargs.get("app_name", "").strip()
        app_def = find_app(app_name)

        if app_def is None:
            # Last-resort: try 'start' command directly
            logger.info("Unknown app %r — trying Windows 'start' command.", app_name)
            try:
                subprocess.Popen(
                    ["cmd", "/c", "start", "", app_name],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return ToolResult(
                    success=True,
                    output=f"Attempted to launch '{app_name}' via Windows start command.",
                )
            except Exception as e:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Application '{app_name}' not found and could not be launched: {e}",
                )

        # 1. Try exe candidates first
        exe = resolve_executable(app_def)
        if exe:
            try:
                subprocess.Popen(
                    [exe],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return ToolResult(
                    success=True,
                    output=f"Launched {app_def.names[0].title()}: {exe}",
                    data={"executable": exe},
                )
            except Exception as e:
                logger.warning("Failed to launch exe %r: %s", exe, e)

        # 2. Try Windows URI protocol (e.g. 'whatsapp:', 'calc:', 'spotify:') for UWP / Store apps
        if getattr(app_def, "protocol", None):
            try:
                os.startfile(app_def.protocol)  # type: ignore[attr-defined]
                return ToolResult(
                    success=True,
                    output=f"Launched {app_def.names[0].title()} (Desktop app via '{app_def.protocol}').",
                    data={"protocol": app_def.protocol},
                )
            except Exception as e:
                logger.debug("Protocol launch for %r failed: %s", app_def.protocol, e)

        # 3. URL fallback (opens in default browser)
        if app_def.url:
            try:
                os.startfile(app_def.url)  # type: ignore[attr-defined]
                return ToolResult(
                    success=True,
                    output=f"Opened {app_def.names[0].title()} in your default browser: {app_def.url}",
                    data={"url": app_def.url},
                )
            except Exception as e:
                return ToolResult(success=False, output="", error=str(e))

        return ToolResult(
            success=False,
            output="",
            error=(
                f"Could not find or launch '{app_name}'. "
                "The application may not be installed on this machine."
            ),
        )



@register_tool
class CloseApplicationTool(AbstractTool):
    """Terminate a running application by name (requires confirmation)."""

    input_model = _CloseAppInput
    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "close_application"
    @property
    def description(self) -> str:
        return (
            "Close / terminate a running application. "
            "This kills the process and may result in unsaved work being lost. "
            "Requires explicit user confirmation."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Name of the application to close"},
                "force": {"type": "boolean", "description": "Force-kill if graceful close fails", "default": False},
            },
            "required": ["app_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        app_name: str = kwargs.get("app_name", "").strip()
        force: bool = kwargs.get("force", False)
        app_def = find_app(app_name)

        process_name = (app_def.process_name if app_def else None) or f"{app_name}.exe"
        flag = "/F" if force else ""

        try:
            cmd = ["taskkill", "/IM", process_name]
            if force:
                cmd.append("/F")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    output=f"Closed {app_name} (process: {process_name}).",
                    data={"process": process_name},
                )
            else:
                stderr = result.stderr.strip()
                if "not found" in stderr.lower() or "no tasks" in stderr.lower():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"{app_name} does not appear to be running.",
                    )
                return ToolResult(success=False, output="", error=stderr or result.stdout.strip())
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Timed out trying to close {app_name}.")
        except Exception as e:
            logger.exception("close_application failed for %s", app_name)
            return ToolResult(success=False, output="", error=str(e))


class _WhatsAppMessageInput(BaseModel):
    message: str = Field(..., min_length=1, description="The message text to send")
    contact: Optional[str] = Field(
        default=None,
        description="Contact name or phone number (e.g. 'Aditya Tiwari' or '+919876543210')",
    )


@register_tool
class SendWhatsAppMessageTool(AbstractTool):
    """Send or compose a WhatsApp message using the WhatsApp Desktop application."""

    input_model = _WhatsAppMessageInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "send_whatsapp_message"
    @property
    def description(self) -> str:
        return (
            "Send or compose a WhatsApp message to a contact or phone number. "
            "Opens WhatsApp Desktop with the pre-filled message ready to send. "
            "Use when the user says 'send a WhatsApp message to X', 'message X on WhatsApp', "
            "or 'open WhatsApp and message X saying Y'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message text to send",
                },
                "contact": {
                    "type": "string",
                    "description": "Contact name or phone number (e.g. 'Aditya Tiwari' or '+919876543210')",
                },
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        contact: str = kwargs.get("contact", "") or ""
        message: str = kwargs.get("message", "").strip()

        if not message:
            return ToolResult(success=False, output="", error="Message cannot be empty.")

        encoded_msg = urllib.parse.quote(message)

        # Check if contact contains a numeric phone number
        digits = re.sub(r"[^\d+]", "", contact)
        if digits and len(digits) >= 7:
            # Phone number direct link
            uri = f"whatsapp://send?phone={digits}&text={encoded_msg}"
            target_desc = f"phone number {digits}"
        elif contact:
            uri = f"whatsapp://send?text={encoded_msg}"
            target_desc = f"contact '{contact}'"
        else:
            uri = f"whatsapp://send?text={encoded_msg}"
            target_desc = "WhatsApp"

        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            return ToolResult(
                success=True,
                output=f"Opened WhatsApp Desktop with pre-filled message for {target_desc}: \"{message}\".",
                data={"contact": contact, "message": message, "uri": uri},
            )
        except Exception as exc:
            # Fallback to WhatsApp Web if protocol fails
            web_url = f"https://web.whatsapp.com/send?text={encoded_msg}"
            if digits and len(digits) >= 7:
                web_url = f"https://web.whatsapp.com/send?phone={digits}&text={encoded_msg}"
            try:
                os.startfile(web_url)  # type: ignore[attr-defined]
                return ToolResult(
                    success=True,
                    output=f"Opened WhatsApp Web with message for {target_desc}: \"{message}\".",
                    data={"contact": contact, "message": message, "url": web_url},
                )
            except Exception as web_exc:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Failed to open WhatsApp Desktop ({exc}) and Web fallback ({web_exc}).",
                )

