"""
Unified Tool Registry — the single source of truth for all agent tools.

This module extends the base ToolRegistry with:
  - remove_tool()      : deregister a tool by name
  - list_tools()       : return ToolInfoSchema objects for all tools
  - get_tool()         : alias for get_or_raise (cleaner public API)
  - register_tool()    : class decorator (re-exported here for convenience)

All tool modules in app/tools/impl/ register via the @register_tool decorator.
The global singleton is accessible via get_tool_registry().
"""
from __future__ import annotations

import importlib
import logging
from typing import Iterator, Type

from app.agent.schemas import ToolInfoSchema, PermissionLevelSchema
from app.tools.base import AbstractTool, PermissionLevel
from app.utils.exceptions import ToolNotFoundError

logger = logging.getLogger(__name__)

# ── Modules that contain @register_tool classes ───────────────────────────────
# These are loaded at startup in order. Later entries overwrite earlier ones
# if they declare the same tool name — new tool packages supersede impl/*.
_TOOL_MODULES: list[str] = [
    # Legacy / utility tools
    "app.tools.impl.utility",       # get_current_time
    # Structured computer-control tool packages
    "app.tools.filesystem",         # 10 filesystem tools
    "app.tools.applications",       # open_application, close_application
    "app.tools.windows",            # open_url, lock, shutdown, restart, screenshot
    "app.tools.system",             # system_info, cpu, memory, disk, processes
    "app.tools.terminal",           # run_command (allowlist-controlled)
]


class AgentToolRegistry:
    """
    Registry for all agent tools.

    Provides:
      register_tool()  – class decorator / explicit registration
      get_tool()       – look up by name, raise if missing
      list_tools()     – return ToolInfoSchema list for all registered tools
      remove_tool()    – deregister a tool by name
      function_specs() – Groq/OpenAI function-calling specs
    """

    def __init__(self) -> None:
        self._tools: dict[str, AbstractTool] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, tool_cls: Type[AbstractTool]) -> Type[AbstractTool]:
        """
        Register a tool class.  Instantiates it and stores the instance.
        Returns the class unchanged so it can be used as a decorator.
        """
        instance: AbstractTool = tool_cls()
        if instance.name in self._tools:
            logger.warning("Tool %r already registered — overwriting.", instance.name)
        self._tools[instance.name] = instance
        logger.debug(
            "Registered tool %r (permission=%s)",
            instance.name,
            instance.permission_level.value,
        )
        return tool_cls

    def remove_tool(self, name: str) -> None:
        """
        Remove a tool from the registry.

        Args:
            name: The tool's snake_case name.

        Raises:
            ToolNotFoundError if the tool is not registered.
        """
        if name not in self._tools:
            raise ToolNotFoundError(
                f"Cannot remove tool {name!r}: not registered.", tool_name=name
            )
        del self._tools[name]
        logger.info("Tool %r removed from registry.", name)

    # ── Lookup ────────────────────────────────────────────────────────────────

    def get_tool(self, name: str) -> AbstractTool:
        """
        Return the registered tool instance for *name*.

        Raises:
            ToolNotFoundError if not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            available = ", ".join(self._tools) or "(none)"
            raise ToolNotFoundError(
                f"Tool {name!r} is not registered. Available: {available}",
                tool_name=name,
            )
        return tool

    def get(self, name: str) -> AbstractTool | None:
        """Return the tool instance for *name*, or None."""
        return self._tools.get(name)

    # Backwards-compat alias used by existing executor
    def get_or_raise(self, name: str) -> AbstractTool:
        return self.get_tool(name)

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_tools(self) -> list[ToolInfoSchema]:
        """Return ToolInfoSchema objects for every registered tool."""
        result: list[ToolInfoSchema] = []
        for tool in self._tools.values():
            result.append(
                ToolInfoSchema(
                    name=tool.name,
                    description=tool.description,
                    permission_level=PermissionLevelSchema(tool.permission_level.value),
                    requires_confirmation=getattr(tool, "requires_confirmation", False),
                    parameters_schema=tool.parameters_schema,
                )
            )
        return result

    def all(self) -> Iterator[AbstractTool]:
        """Iterate over all registered tool instances."""
        yield from self._tools.values()

    def names(self) -> list[str]:
        """Return a sorted list of registered tool names."""
        return sorted(self._tools.keys())

    def function_specs(self) -> list[dict]:
        """Return Groq/OpenAI function-calling specs for all tools."""
        return [tool.to_function_spec() for tool in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"AgentToolRegistry({self.names()})"


# ── Global singleton ──────────────────────────────────────────────────────────

_registry = AgentToolRegistry()


def get_tool_registry() -> AgentToolRegistry:
    """Return the global AgentToolRegistry singleton."""
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
        except Exception as exc:
            logger.exception("Unexpected error loading tool module %s", module_path)
