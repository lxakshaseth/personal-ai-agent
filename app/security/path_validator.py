"""
Path security module — validates and sanitises file-system paths.

Provides one public function: validate_path()

Every filesystem tool MUST call validate_path() before touching the disk.

Protection rules
----------------
1. Paths are resolved to their real absolute form (eliminates ../.. traversal).
2. The resolved path must be a sub-path of at least one entry in
   settings.allowed_base_paths (default: C:\\Users, C:\\Temp).
3. The resolved path must NOT be inside any known Windows system directory.
4. The path must not be the root of a drive (e.g. C:\\).
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Collection

from app.utils.exceptions import PermissionDeniedError

# ── Hard-coded system directories that are always off-limits ──────────────────
# Normalised to lowercase for case-insensitive comparison on Windows.
_ALWAYS_PROTECTED: frozenset[str] = frozenset(
    p.lower()
    for p in [
        "C:\\Windows",
        "C:\\Windows\\System32",
        "C:\\Windows\\SysWOW64",
        "C:\\Windows\\WinSxS",
        "C:\\Program Files",
        "C:\\Program Files (x86)",
        "C:\\ProgramData",
        "C:\\System Volume Information",
        "C:\\Recovery",
        "C:\\boot",
        r"C:\$Recycle.Bin",
        r"C:\$WinREAgent",
        r"C:\EFI",
        os.environ.get("SYSTEMROOT", "C:\\Windows"),
        os.environ.get("PROGRAMFILES", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
    ]
    if p
)


class PathSecurityError(PermissionDeniedError):
    """Raised when a path fails security validation."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.path = path


def _normalise(path: Path) -> str:
    """Return a lowercase, backslash-normalised string for case-insensitive Windows comparison."""
    return str(path).lower().replace("/", "\\").rstrip("\\")


def _is_protected(resolved: Path) -> bool:
    """Return True if *resolved* is or lives inside a protected system directory."""
    rstr = _normalise(resolved)
    for protected in _ALWAYS_PROTECTED:
        p = protected.rstrip("\\")
        # exact match or child
        if rstr == p or rstr.startswith(p + "\\"):
            return True
    return False


def _is_drive_root(resolved: Path) -> bool:
    """Return True for bare drive roots like C:\\ or D:\\."""
    parts = resolved.parts
    return len(parts) == 1 and parts[0].endswith("\\")


def validate_path(
    path_str: str,
    allowed_paths: Collection[str],
    *,
    operation: str = "access",
) -> Path:
    """
    Validate a path for safety and return the resolved absolute Path.

    Args:
        path_str:      Raw path string provided by the user or LLM.
        allowed_paths: Iterable of root directories the agent may use
                       (from settings.allowed_base_paths).
        operation:     Human-readable verb used in error messages (e.g. 'delete').

    Returns:
        The resolved absolute pathlib.Path object.

    Raises:
        PathSecurityError: On any security violation.
    """
    if not path_str or not path_str.strip():
        raise PathSecurityError("Path must not be empty.", path=path_str)

    # ── Resolve to real absolute path ─────────────────────────────────────────
    try:
        # Use resolve(strict=False) — we don't require the path to exist yet
        # (e.g. when creating a new file), but we still normalise it fully.
        resolved = Path(path_str).resolve()
    except (OSError, ValueError) as exc:
        raise PathSecurityError(
            f"Invalid path {path_str!r}: {exc}", path=path_str
        ) from exc

    # ── Reject bare drive roots ────────────────────────────────────────────────
    if _is_drive_root(resolved):
        raise PathSecurityError(
            f"Cannot {operation} a drive root: {resolved}", path=str(resolved)
        )

    # ── Reject protected system directories ────────────────────────────────────
    if _is_protected(resolved):
        raise PathSecurityError(
            f"Cannot {operation} inside a protected system directory: {resolved}",
            path=str(resolved),
        )

    # ── Check against the allowed-paths whitelist ──────────────────────────────
    if allowed_paths:
        rstr = _normalise(resolved)
        for allowed in allowed_paths:
            try:
                allowed_resolved = _normalise(Path(allowed).resolve())
                if rstr == allowed_resolved or rstr.startswith(allowed_resolved + "\\"):
                    return resolved  # ✓ allowed
            except (OSError, ValueError):
                continue  # skip malformed allowed-path entry

        raise PathSecurityError(
            f"Path {resolved!r} is outside the allowed directories. "
            f"Allowed roots: {list(allowed_paths)}",
            path=str(resolved),
        )

    return resolved


def assert_not_protected(path_str: str, operation: str = "access") -> Path:
    """
    Validate a path ONLY against the protected-system-directory list,
    without enforcing the allowed_base_paths whitelist.

    Used by read-only tools (list_directory, search_files) that may
    legitimately look outside user directories.
    """
    try:
        resolved = Path(path_str).resolve()
    except (OSError, ValueError) as exc:
        raise PathSecurityError(f"Invalid path: {exc}", path=path_str) from exc

    if _is_drive_root(resolved):
        raise PathSecurityError(
            f"Cannot {operation} a drive root: {resolved}", path=str(resolved)
        )
    if _is_protected(resolved):
        raise PathSecurityError(
            f"Cannot {operation} inside a system directory: {resolved}",
            path=str(resolved),
        )
    return resolved
