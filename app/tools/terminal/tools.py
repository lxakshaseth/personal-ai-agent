"""
Terminal tool — controlled subprocess execution with strict allowlisting.

Security model:
  1. ALLOW_SHELL_COMMANDS must be true in settings (default: false).
     When false, ALL terminal calls are rejected immediately.
  2. The first token of the command (the executable) MUST be in the
     ALLOWED_COMMANDS allowlist (default: python, node, npm, git, docker).
  3. The working directory, if provided, must pass path validation.
  4. shell=False is always used — no shell metacharacter injection.
  5. Output is captured and capped at 10 000 characters.
  6. The tool itself is HIGH permission and requires user confirmation.

Registered tools:
  run_command   HIGH   execute an approved command in a controlled subprocess
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agent.tool_registry import register_tool
from app.config.settings import get_settings
from app.security.path_validator import PathSecurityError, assert_not_protected
from app.tools.base import AbstractTool, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 10_000  # chars


class _RunCommandInput(BaseModel):
    command: str = Field(
        ...,
        min_length=1,
        description="Command to run, e.g. 'python --version' or 'git status'",
    )
    working_directory: str = Field(
        default="",
        description="Absolute path to run the command in. Defaults to user home.",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Timeout in seconds (1–300). Defaults to 30.",
    )


@register_tool
class RunCommandTool(AbstractTool):
    """
    Execute an approved shell command in a controlled subprocess.

    SECURITY:
    - Requires ALLOW_SHELL_COMMANDS=true in .env (default: false).
    - Only commands in ALLOWED_COMMANDS may run.
    - Never uses shell=True; arguments are parsed with shlex.
    - Requires explicit user confirmation (HIGH permission).
    """

    input_model = _RunCommandInput
    requires_confirmation: bool = True

    @property
    def name(self) -> str: return "run_command"
    @property
    def description(self) -> str:
        return (
            "Execute an approved command in a controlled terminal. "
            f"Only these executables are allowed by default: python, node, npm, git, docker. "
            "ALLOW_SHELL_COMMANDS must be enabled in settings. "
            "Requires explicit user confirmation. "
            "NEVER use for system administration commands or arbitrary scripts."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.HIGH
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command string, e.g. 'python --version', 'git status'",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Absolute path to run the command in (optional)",
                    "default": "",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in seconds (1–300)",
                    "default": 30,
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        settings = get_settings()

        # ── Gate 1: Shell commands globally disabled ───────────────────────────
        if not settings.allow_shell_commands:
            return ToolResult(
                success=False,
                output="",
                error=(
                    "Terminal execution is disabled. "
                    "Set ALLOW_SHELL_COMMANDS=true in your .env file to enable it. "
                    "This is a security measure to prevent unintended command execution."
                ),
            )

        raw_command: str = kwargs.get("command", "").strip()
        working_dir: str = kwargs.get("working_directory", "").strip()
        timeout: int = int(kwargs.get("timeout_seconds", 30))

        # ── Gate 2: Parse and validate the executable ──────────────────────────
        try:
            parts = shlex.split(raw_command, posix=False)
        except ValueError as e:
            return ToolResult(success=False, output="", error=f"Invalid command syntax: {e}")

        if not parts:
            return ToolResult(success=False, output="", error="Empty command.")

        executable = parts[0].strip().lower()
        # Strip extension for comparison (e.g. python.exe → python)
        exec_base = executable.replace(".exe", "").replace(".cmd", "").replace(".bat", "")

        allowed = [cmd.lower() for cmd in settings.allowed_commands]
        if exec_base not in allowed:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"Command '{parts[0]}' is not in the allowed commands list. "
                    f"Allowed: {', '.join(settings.allowed_commands)}. "
                    "Update ALLOWED_COMMANDS in .env to add more commands."
                ),
            )

        # ── Gate 3: Validate working directory ────────────────────────────────
        cwd: str | None = None
        if working_dir:
            try:
                cwd_path = assert_not_protected(working_dir, "run commands in")
                if not cwd_path.is_dir():
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Working directory not found: {working_dir}",
                    )
                cwd = str(cwd_path)
            except PathSecurityError as e:
                return ToolResult(success=False, output="", error=str(e))

        # ── Execute ────────────────────────────────────────────────────────────
        logger.info("run_command: %r (cwd=%s timeout=%ds)", raw_command, cwd, timeout)

        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds.",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
            returncode = proc.returncode

            if returncode == 0:
                output = stdout or "(no output)"
                return ToolResult(
                    success=True,
                    output=output,
                    data={"returncode": returncode, "stdout": stdout, "stderr": stderr},
                )
            else:
                combined = (stdout + "\n" + stderr).strip()
                return ToolResult(
                    success=False,
                    output=stdout,
                    error=f"Command exited with code {returncode}.\n{combined}"[:_MAX_OUTPUT],
                    data={"returncode": returncode, "stdout": stdout, "stderr": stderr},
                )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error=(
                    f"Executable '{parts[0]}' not found on PATH. "
                    "Make sure it is installed and accessible."
                ),
            )
        except Exception as e:
            logger.exception("run_command failed: %r", raw_command)
            return ToolResult(success=False, output="", error=f"Execution error: {e}")
