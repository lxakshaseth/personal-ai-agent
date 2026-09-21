"""
Filesystem tools — safe, path-validated operations on the Windows filesystem.

All tools enforce:
  1. Path security via app.security.path_validator
  2. Pydantic input validation via input_model
  3. Confirmation requirement for destructive operations (HIGH permission)

Registered tools:
  create_folder   MEDIUM  create a new directory
  delete_folder   HIGH    delete a directory tree (destructive)
  create_file     MEDIUM  create or overwrite a text file
  delete_file     HIGH    delete a single file (destructive)
  move_file       MEDIUM  move or rename a file/folder
  copy_file       MEDIUM  copy a file to a destination
  rename_file     MEDIUM  rename a file or folder in-place
  search_files    LOW     find files by glob pattern
  open_folder     LOW     open a folder in Windows Explorer
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.tool_registry import register_tool
from app.config.settings import get_settings
from app.security.path_validator import PathSecurityError, validate_path, assert_not_protected
from app.tools.base import AbstractTool, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _allowed() -> list[str]:
    return get_settings().allowed_base_paths


def _vp(path_str: str, op: str = "access") -> Path:
    """Shorthand: validate path against allowed_base_paths."""
    return validate_path(path_str, _allowed(), operation=op)


# ── Input models ───────────────────────────────────────────────────────────────

class _FolderPathInput(BaseModel):
    folder_path: str = Field(..., min_length=1)

class _CreateFolderInput(BaseModel):
    folder_path: str = Field(..., min_length=1, description="Absolute path of the folder to create")
    exist_ok: bool = Field(default=True)

class _CreateFileInput(BaseModel):
    file_path: str = Field(..., min_length=1)
    content: str = Field(default="", description="Text content to write")
    overwrite: bool = Field(default=False)

class _MoveInput(BaseModel):
    source: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)

class _CopyInput(BaseModel):
    source: str = Field(..., min_length=1)
    destination: str = Field(..., min_length=1)

class _RenameInput(BaseModel):
    path: str = Field(..., min_length=1)
    new_name: str = Field(..., min_length=1, description="New name (not full path) of the item")

class _ListDirInput(BaseModel):
    folder_path: str = Field(..., min_length=1)

class _SearchInput(BaseModel):
    folder_path: str = Field(..., min_length=1)
    pattern: str = Field(..., min_length=1, description="Glob pattern, e.g. '*.py' or 'test_*'")
    recursive: bool = Field(default=True)

class _OpenFolderInput(BaseModel):
    folder_path: str = Field(default="", description="Absolute path or well-known name (downloads, desktop…)")


# ── Well-known folder map ──────────────────────────────────────────────────────

_KNOWN_FOLDERS: dict[str, str] = {
    "downloads": str(Path.home() / "Downloads"),
    "documents": str(Path.home() / "Documents"),
    "desktop":   str(Path.home() / "Desktop"),
    "pictures":  str(Path.home() / "Pictures"),
    "music":     str(Path.home() / "Music"),
    "videos":    str(Path.home() / "Videos"),
    "home":      str(Path.home()),
}


# ── Tools ──────────────────────────────────────────────────────────────────────

@register_tool
class CreateFolderTool(AbstractTool):
    """Create a new directory (and any missing parents)."""

    input_model = _CreateFolderInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "create_folder"
    @property
    def description(self) -> str:
        return (
            "Create a new folder/directory. "
            "Use when the user says 'create a folder called X' or 'make a directory named Y at <path>'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {"type": "string", "description": "Absolute path of the folder to create"},
                "exist_ok": {"type": "boolean", "description": "Don't error if folder already exists", "default": True},
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _vp(kwargs["folder_path"], "create")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        try:
            await asyncio.to_thread(path.mkdir, parents=True, exist_ok=kwargs.get("exist_ok", True))
            return ToolResult(success=True, output=f"Folder created: {path}", data={"path": str(path)})
        except Exception as e:
            logger.exception("create_folder failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class DeleteFolderTool(AbstractTool):
    """Delete a folder and all its contents — DESTRUCTIVE and irreversible."""

    input_model = _FolderPathInput
    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "delete_folder"
    @property
    def description(self) -> str:
        return (
            "Permanently delete a folder and ALL its contents. "
            "This is irreversible. Requires explicit user confirmation. "
            "NEVER call unless the user explicitly asks to delete a specific folder."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {"type": "string", "description": "Absolute path of the folder to delete"},
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _vp(kwargs["folder_path"], "delete")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not path.exists():
            return ToolResult(success=False, output="", error=f"Folder not found: {path}")
        if not path.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")
        try:
            await asyncio.to_thread(shutil.rmtree, path)
            return ToolResult(success=True, output=f"Deleted folder: {path}", data={"deleted": str(path)})
        except Exception as e:
            logger.exception("delete_folder failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class CreateFileTool(AbstractTool):
    """Create or overwrite a text file with provided content."""

    input_model = _CreateFileInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "create_file"
    @property
    def description(self) -> str:
        return (
            "Create a new text file at a given path with optional content. "
            "Use for 'create a file called X.txt with content Y'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path of the file to create"},
                "content": {"type": "string", "description": "Text content to write", "default": ""},
                "overwrite": {"type": "boolean", "description": "Overwrite if file exists", "default": False},
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _vp(kwargs["file_path"], "create")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        overwrite = kwargs.get("overwrite", False)
        if path.exists() and not overwrite:
            return ToolResult(success=False, output="", error=f"File already exists: {path}. Set overwrite=true to replace it.")
        try:
            def _write():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(kwargs.get("content", ""), encoding="utf-8")
            await asyncio.to_thread(_write)
            return ToolResult(success=True, output=f"File created: {path}", data={"path": str(path)})
        except Exception as e:
            logger.exception("create_file failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class DeleteFileTool(AbstractTool):
    """Delete a single file — DESTRUCTIVE."""

    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "delete_file"
    @property
    def description(self) -> str:
        return (
            "Permanently delete a single file. Irreversible. "
            "Requires explicit user confirmation."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path of the file to delete"},
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = _vp(kwargs.get("file_path", ""), "delete")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not path.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        if path.is_dir():
            return ToolResult(success=False, output="", error=f"Path is a directory, use delete_folder: {path}")
        try:
            await asyncio.to_thread(path.unlink)
            return ToolResult(success=True, output=f"Deleted file: {path}", data={"deleted": str(path)})
        except Exception as e:
            logger.exception("delete_file failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class MoveFileTool(AbstractTool):
    """Move or relocate a file or folder to a new location."""

    input_model = _MoveInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "move_file"
    @property
    def description(self) -> str:
        return "Move a file or folder from source to destination. Also works for folders."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source absolute path"},
                "destination": {"type": "string", "description": "Destination absolute path"},
            },
            "required": ["source", "destination"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            src = _vp(kwargs["source"], "move")
            dst = _vp(kwargs["destination"], "move")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not src.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {src}")
        try:
            def _move():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
            await asyncio.to_thread(_move)
            return ToolResult(success=True, output=f"Moved {src} → {dst}", data={"source": str(src), "destination": str(dst)})
        except Exception as e:
            logger.exception("move_file failed %s → %s", src, dst)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class CopyFileTool(AbstractTool):
    """Copy a file (or folder tree) to a destination."""

    input_model = _CopyInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "copy_file"
    @property
    def description(self) -> str:
        return "Copy a file or folder to a new destination path."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source absolute path"},
                "destination": {"type": "string", "description": "Destination absolute path"},
            },
            "required": ["source", "destination"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            src = _vp(kwargs["source"], "copy")
            dst = _vp(kwargs["destination"], "copy")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not src.exists():
            return ToolResult(success=False, output="", error=f"Source not found: {src}")
        try:
            def _copy():
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
            await asyncio.to_thread(_copy)
            return ToolResult(success=True, output=f"Copied {src} → {dst}", data={"source": str(src), "destination": str(dst)})
        except Exception as e:
            logger.exception("copy_file failed %s → %s", src, dst)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class RenameFileTool(AbstractTool):
    """Rename a file or folder in its current location."""

    input_model = _RenameInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "rename_file"
    @property
    def description(self) -> str:
        return "Rename a file or folder. Provide the current path and the new name (not the full new path)."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.MEDIUM
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Current absolute path of the item"},
                "new_name": {"type": "string", "description": "New name for the item (just the filename, not full path)"},
            },
            "required": ["path", "new_name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            src = _vp(kwargs["path"], "rename")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        new_name: str = kwargs.get("new_name", "").strip()
        if not new_name or "/" in new_name or "\\" in new_name:
            return ToolResult(success=False, output="", error="new_name must be a plain name, not a path.")
        if not src.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {src}")
        dst = src.parent / new_name
        try:
            dst_validated = _vp(str(dst), "rename")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        try:
            await asyncio.to_thread(src.rename, dst)
            return ToolResult(success=True, output=f"Renamed {src.name} → {new_name}", data={"old": str(src), "new": str(dst)})
        except Exception as e:
            logger.exception("rename_file failed %s → %s", src, dst)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class ListDirectoryTool(AbstractTool):
    """List the contents of a directory."""

    input_model = _ListDirInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "list_directory"
    @property
    def description(self) -> str:
        return "List files and folders inside a directory. Shows name, type, and size."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {"type": "string", "description": "Absolute path to list"},
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw = kwargs.get("folder_path", "")
        # Resolve well-known names
        resolved_raw = _KNOWN_FOLDERS.get(raw.strip().lower(), raw)
        try:
            path = assert_not_protected(resolved_raw, "list")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not path.exists() or not path.is_dir():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            lines = []
            data_entries = []
            for e in entries:
                kind = "FILE" if e.is_file() else "DIR "
                size = e.stat().st_size if e.is_file() else ""
                size_str = f"  ({size:,} bytes)" if size != "" else ""
                lines.append(f"[{kind}] {e.name}{size_str}")
                data_entries.append({"name": e.name, "type": "file" if e.is_file() else "dir"})
            output = "\n".join(lines) if lines else "(empty directory)"
            return ToolResult(success=True, output=output, data={"path": str(path), "entries": data_entries, "count": len(lines)})
        except Exception as e:
            logger.exception("list_directory failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class SearchFilesTool(AbstractTool):
    """Search for files matching a glob pattern inside a directory."""

    input_model = _SearchInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "search_files"
    @property
    def description(self) -> str:
        return (
            "Search for files matching a pattern inside a directory. "
            "Pattern uses glob syntax: '*.py', 'test_*', '**/*.txt'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Glob pattern like '*.py' or 'readme*'"},
                "recursive": {"type": "boolean", "description": "Search subdirectories", "default": True},
            },
            "required": ["folder_path", "pattern"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            path = assert_not_protected(kwargs["folder_path"], "search")
        except PathSecurityError as e:
            return ToolResult(success=False, output="", error=str(e))
        if not path.is_dir():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")
        pattern: str = kwargs.get("pattern", "*")
        recursive: bool = kwargs.get("recursive", True)
        try:
            glob_fn = path.rglob if recursive else path.glob
            matches = sorted(glob_fn(pattern))[:200]  # cap at 200 results
            if not matches:
                return ToolResult(success=True, output=f"No files matching '{pattern}' found in {path}.", data={"matches": []})
            lines = [str(m.relative_to(path)) for m in matches]
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"matches": [str(m) for m in matches], "count": len(matches)},
            )
        except Exception as e:
            logger.exception("search_files failed in %s", path)
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class OpenFolderTool(AbstractTool):
    """Open a folder in Windows Explorer."""

    input_model = _OpenFolderInput
    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "open_folder"
    @property
    def description(self) -> str:
        return (
            "Open a folder in Windows Explorer. "
            "Accepts absolute paths or well-known names: "
            "downloads, documents, desktop, pictures, music, videos, home."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "folder_path": {
                    "type": "string",
                    "description": "Absolute path or well-known name (downloads, desktop, documents…)",
                },
            },
            "required": ["folder_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        raw: str = kwargs.get("folder_path", "").strip()
        folder = _KNOWN_FOLDERS.get(raw.lower(), raw)
        path = Path(folder)
        if not path.exists():
            return ToolResult(success=False, output="", error=f"Folder not found: {path}")
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return ToolResult(success=True, output=f"Opened folder: {path}", data={"path": str(path)})
        except Exception as e:
            logger.exception("open_folder failed for %s", path)
            return ToolResult(success=False, output="", error=str(e))
