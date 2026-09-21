"""
Tool Registry — single source of truth for all available tools.

Usage (in a tool implementation module):

    from app.tools.registry import register_tool
    from app.tools.base import AbstractTool, PermissionLevel, ToolResult

    @register_tool
    class MyTool(AbstractTool):
        ...

The registry discovers tools automatically when their module is imported.
`load_all_tools()` handles the import side-effect.
"""
from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING, Iterator, Type

if TYPE_CHECKING:
    from app.tools.base import AbstractTool

logger = logging.getLogger(__name__)

# ── Known tool modules (add new ones here) ────────────────────────────────────
_TOOL_MODULES: list[str] = [
    "app.tools.impl.system",
    "app.tools.impl.browser",
]


class ToolRegistry:
    """
    Singleton registry that holds all registered tool classes.

    Tools are stored by their `name` property.  The registry is populated
    lazily when `load_all_tools()` is first called.
    """

    def __init__(self) -> None:
        self._tools: dict[str, AbstractTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool_cls: Type[AbstractTool]) -> Type[AbstractTool]:
        """Instantiate and register a tool class.  Returns the class unchanged."""
        instance: AbstractTool = tool_cls()
        if instance.name in self._tools:
            logger.warning(
                "Tool %r is already registered; overwriting.", instance.name
            )
        self._tools[instance.name] = instance
        logger.debug("Registered tool: %r (permission=%s)", instance.name, instance.permission_level.value)
        return tool_cls

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get(self, name: str) -> AbstractTool | None:
        """Return the tool instance for *name*, or None."""
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> AbstractTool:
        """Return the tool instance for *name*, raising if not found."""
        from app.utils.exceptions import ToolNotFoundError

        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(
                f"Tool {name!r} is not registered.",
                tool_name=name,
            )
        return tool

    def all(self) -> Iterator[AbstractTool]:
        """Iterate over all registered tool instances."""
        yield from self._tools.values()

    def function_specs(self) -> list[dict]:
        """Return Groq/OpenAI function-calling specs for all tools."""
        return [tool.to_function_spec() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


# ── Global singleton ──────────────────────────────────────────────────────────

_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """Return the global ToolRegistry singleton."""
    return _registry


def register_tool(cls: Type[AbstractTool]) -> Type[AbstractTool]:
    """Class decorator: register a tool with the global registry."""
    return _registry.register(cls)


def load_all_tools() -> None:
    """
    Import all known tool modules so their @register_tool decorators fire.
    Call once during application startup.
    """
    for module_path in _TOOL_MODULES:
        try:
            importlib.import_module(module_path)
            logger.debug("Loaded tool module: %s", module_path)
        except ImportError as exc:
            logger.error("Failed to import tool module %s: %s", module_path, exc)
