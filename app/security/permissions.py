"""
Permission layer — validates tool access before execution.
"""
from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.tools.base import AbstractTool, PermissionLevel
from app.utils.exceptions import ConfirmationRequiredError, PermissionDeniedError

logger = logging.getLogger(__name__)


class PermissionChecker:
    """
    Checks whether a tool may run based on:

    1. Allowed base paths  – filesystem tools must operate inside allowed roots.
    2. Confirmation gate   – HIGH-permission tools raise ConfirmationRequiredError
                             unless `confirmed=True` is passed.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def check(
        self,
        tool: AbstractTool,
        args: dict,
        *,
        confirmed: bool = False,
    ) -> None:
        """
        Raise PermissionDeniedError or ConfirmationRequiredError if the tool
        should not run.  Returns normally when the tool is allowed.

        Args:
            tool:      The tool about to execute.
            args:      The arguments the tool will receive.
            confirmed: True if the user has explicitly confirmed the action.
        """
        # 1. Explicitly disabled tool check
        if tool.name in (self._settings.disabled_tools or []):
            raise PermissionDeniedError(
                f"Tool '{tool.name}' has been disabled in security settings.",
                tool_name=tool.name,
            )

        # 2. Granular domain policy checks
        if tool.name in ("delete_folder", "delete_file") and not self._settings.allow_file_deletion:
            raise PermissionDeniedError(
                "File and folder deletion is disabled by security policy.",
                tool_name=tool.name,
            )

        if tool.name in ("open_url", "browser_open_url", "browser_search") and not self._settings.allow_browser_automation:
            raise PermissionDeniedError(
                "Browser automation is disabled by security policy.",
                tool_name=tool.name,
            )

        if tool.name == "send_whatsapp_message" and not self._settings.allow_whatsapp_messaging:
            raise PermissionDeniedError(
                "WhatsApp messaging is disabled by security policy.",
                tool_name=tool.name,
            )

        if tool.name in ("shutdown_computer", "restart_computer", "lock_computer") and not self._settings.allow_system_controls:
            raise PermissionDeniedError(
                "System controls (shutdown, restart, lock) are disabled by security policy.",
                tool_name=tool.name,
            )

        if tool.name == "run_command" and not self._settings.allow_shell_commands:
            raise PermissionDeniedError(
                "Shell command execution is disabled by security policy.",
                tool_name=tool.name,
            )

        # 3. Path safety & confirmation
        self._check_path_safety(tool, args)
        self._check_confirmation(tool, confirmed=confirmed)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_path_safety(self, tool: AbstractTool, args: dict) -> None:
        """Ensure any path argument stays within the allowed base paths."""
        allowed = [p.lower() for p in self._settings.allowed_base_paths]
        path_keys = ("folder_path", "file_path", "parent_path", "path")

        for key in path_keys:
            value: str | None = args.get(key)
            if not value:
                continue
            normalized = value.lower().replace("/", "\\")
            if not any(normalized.startswith(base) for base in allowed):
                raise PermissionDeniedError(
                    f"Path '{value}' is outside allowed base paths.",
                    tool_name=tool.name,
                )

    def _check_confirmation(self, tool: AbstractTool, *, confirmed: bool) -> None:
        """HIGH-risk tools require explicit confirmation."""
        if (
            tool.permission_level == PermissionLevel.HIGH
            and self._settings.agent_require_confirmation
            and not confirmed
        ):
            raise ConfirmationRequiredError(
                f"Tool '{tool.name}' requires explicit confirmation before running "
                f"(permission level: HIGH).",
                tool_name=tool.name,
            )


# ── Singleton ─────────────────────────────────────────────────────────────────

_checker: PermissionChecker | None = None


def get_permission_checker() -> PermissionChecker:
    global _checker
    if _checker is None:
        _checker = PermissionChecker()
    return _checker
