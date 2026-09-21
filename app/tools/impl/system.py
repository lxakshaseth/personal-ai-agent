"""
System tools — Windows computer-control actions.

Registered tools:
  - open_application   : Launch an installed application by name
  - open_folder        : Open a folder in Windows Explorer
  - create_folder      : Create a new directory
  - delete_folder      : Delete a directory (HIGH permission)
  - list_directory     : List files in a directory
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)

# ── Known application shortcuts ───────────────────────────────────────────────
# Maps common names → executable / shell command.
# Extend this dict or rely on the fallback `start` command.
_APP_MAP: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "notepad": "notepad",
    "calculator": "calc",
    "explorer": "explorer",
    "file explorer": "explorer",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "spotify": "spotify",
    "discord": "discord",
    "whatsapp": "whatsapp",
    "outlook": "outlook",
    "teams": "teams",
    "slack": "slack",
    "notion": "notion",
}


@register_tool
class OpenApplicationTool(AbstractTool):
    """Launch an application or open a URL by its common name."""

    @property
    def name(self) -> str:
        return "open_application"

    @property
    def description(self) -> str:
        return (
            "Open an application on the user's Windows computer or navigate to a website. "
            "Use this when the user says 'open <app_name>' or 'launch <app_name>'."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.MEDIUM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application or website to open (e.g. 'YouTube', 'VS Code')",
                }
            },
            "required": ["app_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        app_name: str = kwargs.get("app_name", "").strip().lower()
        if not app_name:
            return ToolResult(success=False, output="", error="app_name is required")

        target = _APP_MAP.get(app_name, app_name)

        try:
            if target.startswith("http://") or target.startswith("https://"):
                os.startfile(target)  # type: ignore[attr-defined]
                return ToolResult(success=True, output=f"Opened {target} in default browser.")

            # Try via subprocess / Windows 'start' command
            subprocess.Popen(
                ["cmd", "/c", "start", "", target],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ToolResult(success=True, output=f"Launched '{app_name}'.")
        except Exception as exc:
            logger.exception("Failed to open application %r", app_name)
            return ToolResult(success=False, output="", error=str(exc))


@register_tool
class OpenFolderTool(AbstractTool):
    """Open a folder in Windows Explorer."""

    @property
    def name(self) -> str:
        return "open_folder"

    @property
    def description(self) -> str:
        return (
            "Open a specific folder in Windows Explorer. "
            "Use for 'open my Downloads folder', 'show me Documents', etc."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": (
                        "Absolute path OR a well-known folder name "
                        "(downloads, documents, desktop, pictures, music, videos, home)"
                    ),
                }
            },
            "required": ["folder_path"],
        }

    _KNOWN_FOLDERS: dict[str, str] = {
        "downloads": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
        "desktop": str(Path.home() / "Desktop"),
        "pictures": str(Path.home() / "Pictures"),
        "music": str(Path.home() / "Music"),
        "videos": str(Path.home() / "Videos"),
        "home": str(Path.home()),
    }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw: str = kwargs.get("folder_path", "").strip()
        folder = self._KNOWN_FOLDERS.get(raw.lower(), raw)
        path = Path(folder)

        if not path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Folder does not exist: {folder}",
            )

        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return ToolResult(success=True, output=f"Opened folder: {path}")
        except Exception as exc:
            logger.exception("Failed to open folder %r", folder)
            return ToolResult(success=False, output="", error=str(exc))


@register_tool
class CreateFolderTool(AbstractTool):
    """Create a new directory."""

    @property
    def name(self) -> str:
        return "create_folder"

    @property
    def description(self) -> str:
        return (
            "Create a new folder/directory on the computer. "
            "Use for 'create a folder called X' or 'make a directory named Y'."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.MEDIUM

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_name": {
                    "type": "string",
                    "description": "Name of the folder to create",
                },
                "parent_path": {
                    "type": "string",
                    "description": (
                        "Parent directory path. Defaults to the user's Desktop."
                    ),
                    "default": str(Path.home() / "Desktop"),
                },
            },
            "required": ["folder_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        folder_name: str = kwargs.get("folder_name", "").strip()
        parent_path: str = kwargs.get("parent_path", str(Path.home() / "Desktop"))

        if not folder_name:
            return ToolResult(success=False, output="", error="folder_name is required")

        target = Path(parent_path) / folder_name
        try:
            target.mkdir(parents=True, exist_ok=True)
            return ToolResult(
                success=True,
                output=f"Created folder: {target}",
                data={"path": str(target)},
            )
        except Exception as exc:
            logger.exception("Failed to create folder %r", target)
            return ToolResult(success=False, output="", error=str(exc))


@register_tool
class DeleteFolderTool(AbstractTool):
    """Delete a directory and its contents (HIGH permission)."""

    @property
    def name(self) -> str:
        return "delete_folder"

    @property
    def description(self) -> str:
        return (
            "Delete a folder and all its contents permanently. "
            "This is a destructive, irreversible operation. "
            "Use only when the user explicitly asks to delete a folder."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.HIGH

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "Absolute path of the folder to delete",
                }
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        folder_path: str = kwargs.get("folder_path", "").strip()
        if not folder_path:
            return ToolResult(success=False, output="", error="folder_path is required")

        path = Path(folder_path)
        if not path.exists():
            return ToolResult(
                success=False,
                output="",
                error=f"Folder not found: {folder_path}",
            )
        if not path.is_dir():
            return ToolResult(
                success=False,
                output="",
                error=f"Path is not a directory: {folder_path}",
            )

        try:
            shutil.rmtree(path)
            return ToolResult(
                success=True,
                output=f"Deleted folder: {path}",
                data={"deleted_path": str(path)},
            )
        except Exception as exc:
            logger.exception("Failed to delete folder %r", folder_path)
            return ToolResult(success=False, output="", error=str(exc))


@register_tool
class ListDirectoryTool(AbstractTool):
    """List the contents of a directory."""

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "List the files and folders inside a directory."

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "Absolute path of the directory to list",
                }
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        folder_path: str = kwargs.get("folder_path", "").strip()
        path = Path(folder_path)

        if not path.exists() or not path.is_dir():
            return ToolResult(
                success=False, output="", error=f"Directory not found: {folder_path}"
            )

        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            lines = [
                f"{'[DIR] ' if e.is_dir() else '[FILE]'} {e.name}"
                for e in entries
            ]
            output = "\n".join(lines) if lines else "(empty directory)"
            return ToolResult(
                success=True,
                output=output,
                data={"entries": [e.name for e in entries]},
            )
        except Exception as exc:
            logger.exception("Failed to list directory %r", folder_path)
            return ToolResult(success=False, output="", error=str(exc))
