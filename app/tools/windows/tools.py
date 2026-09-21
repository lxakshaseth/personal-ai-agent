"""
Windows OS tools — system-level actions.

Registered tools:
  open_url          LOW    open a URL in the default browser
  lock_computer     MEDIUM lock the Windows workstation
  shutdown_computer HIGH   shut down the PC (destructive, requires confirmation)
  restart_computer  HIGH   restart the PC (destructive, requires confirmation)
  take_screenshot   LOW    capture the current screen and save to disk
"""
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.tool_registry import register_tool
from app.tools.base import AbstractTool, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)


class _OpenURLInput(BaseModel):
    url: str = Field(..., min_length=4, description="URL to open")

class _ShutdownInput(BaseModel):
    delay_seconds: int = Field(default=30, ge=0, le=3600)
    message: str = Field(default="System shutdown initiated by AI agent.")

class _RestartInput(BaseModel):
    delay_seconds: int = Field(default=30, ge=0, le=3600)
    message: str = Field(default="System restart initiated by AI agent.")

class _ScreenshotInput(BaseModel):
    save_path: str = Field(
        default="",
        description="Absolute path to save the screenshot. Defaults to Desktop.",
    )


@register_tool
class OpenURLTool(AbstractTool):
    """Open a URL in the default web browser."""

    input_model = _OpenURLInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "open_url"
    @property
    def description(self) -> str:
        return (
            "Open a URL in the default web browser. "
            "Use for 'go to https://...', 'open this link', or navigating to any website."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL including scheme (https://...)"},
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        url: str = kwargs.get("url", "").strip()
        if not url.startswith(("http://", "https://", "ftp://")):
            url = "https://" + url
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return ToolResult(success=True, output=f"Opened: {url}", data={"url": url})
        except Exception as e:
            logger.exception("open_url failed for %r", url)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class LockComputerTool(AbstractTool):
    """Lock the Windows workstation immediately."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "lock_computer"
    @property
    def description(self) -> str:
        return "Lock the Windows screen immediately. Use when the user says 'lock my computer' or 'lock the screen'."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            return ToolResult(success=True, output="Computer locked successfully.")
        except Exception as e:
            logger.exception("lock_computer failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class ShutdownComputerTool(AbstractTool):
    """Schedule a system shutdown — DESTRUCTIVE, requires confirmation."""

    input_model = _ShutdownInput
    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "shutdown_computer"
    @property
    def description(self) -> str:
        return (
            "Shut down the computer after a configurable delay (default 30 seconds). "
            "This will close all applications and power off the PC. "
            "REQUIRES explicit user confirmation. Use only when the user explicitly says 'shut down' or 'power off'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "delay_seconds": {"type": "integer", "description": "Seconds before shutdown (0–3600)", "default": 30},
                "message": {"type": "string", "description": "Message shown before shutdown", "default": "System shutdown initiated by AI agent."},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        delay: int = int(kwargs.get("delay_seconds", 30))
        message: str = kwargs.get("message", "System shutdown initiated by AI agent.")
        try:
            subprocess.run(
                ["shutdown", "/s", "/t", str(delay), "/c", message[:512]],
                check=True,
                capture_output=True,
                text=True,
            )
            return ToolResult(
                success=True,
                output=f"Shutdown scheduled in {delay} second(s). Run 'shutdown /a' to cancel.",
                data={"delay_seconds": delay},
            )
        except subprocess.CalledProcessError as e:
            return ToolResult(success=False, output="", error=e.stderr or str(e))
        except Exception as e:
            logger.exception("shutdown_computer failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class RestartComputerTool(AbstractTool):
    """Schedule a system restart — DESTRUCTIVE, requires confirmation."""

    input_model = _RestartInput
    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "restart_computer"
    @property
    def description(self) -> str:
        return (
            "Restart the computer after a configurable delay (default 30 seconds). "
            "REQUIRES explicit user confirmation. Use only when the user says 'restart' or 'reboot'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "delay_seconds": {"type": "integer", "default": 30},
                "message": {"type": "string", "default": "System restart initiated by AI agent."},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        delay: int = int(kwargs.get("delay_seconds", 30))
        message: str = kwargs.get("message", "System restart initiated by AI agent.")
        try:
            subprocess.run(
                ["shutdown", "/r", "/t", str(delay), "/c", message[:512]],
                check=True,
                capture_output=True,
                text=True,
            )
            return ToolResult(
                success=True,
                output=f"Restart scheduled in {delay} second(s). Run 'shutdown /a' to cancel.",
                data={"delay_seconds": delay},
            )
        except subprocess.CalledProcessError as e:
            return ToolResult(success=False, output="", error=e.stderr or str(e))
        except Exception as e:
            logger.exception("restart_computer failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class TakeScreenshotTool(AbstractTool):
    """Capture the current screen and save it as a PNG file."""

    input_model = _ScreenshotInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "take_screenshot"
    @property
    def description(self) -> str:
        return (
            "Take a screenshot of the current screen and save it as a PNG. "
            "Optionally specify a save path; defaults to the Desktop."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "save_path": {
                    "type": "string",
                    "description": "Absolute path including filename (e.g. C:\\Users\\X\\Desktop\\shot.png). Defaults to Desktop.",
                    "default": "",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        save_path: str = kwargs.get("save_path", "").strip()
        if not save_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = str(Path.home() / "Desktop" / f"screenshot_{ts}.png")

        try:
            import pyautogui  # type: ignore
            screenshot = pyautogui.screenshot()
            screenshot.save(save_path)
            return ToolResult(
                success=True,
                output=f"Screenshot saved to: {save_path}",
                data={"path": save_path},
            )
        except ImportError:
            # Fallback: use Windows built-in PrintScreen via ctypes + PIL if available
            try:
                from PIL import ImageGrab  # type: ignore
                img = ImageGrab.grab()
                img.save(save_path)
                return ToolResult(success=True, output=f"Screenshot saved to: {save_path}", data={"path": save_path})
            except ImportError:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Screenshot requires pyautogui or Pillow. "
                        "Install with: pip install pyautogui"
                    ),
                )
        except Exception as e:
            logger.exception("take_screenshot failed")
            return ToolResult(success=False, output="", error=str(e))
