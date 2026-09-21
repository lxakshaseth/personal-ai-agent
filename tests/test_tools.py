"""
Test: Tool registry and tool interface.
"""
import os
import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.tools.registry import ToolRegistry, get_registry, load_all_tools


# ── Helpers ───────────────────────────────────────────────────────────────────

class _EchoTool(AbstractTool):
    """Minimal concrete tool for testing."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes the input text."

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output=kwargs.get("text", ""))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_tool_registration() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool)
    assert "echo" in registry
    assert len(registry) == 1


def test_tool_get() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool)
    tool = registry.get("echo")
    assert tool is not None
    assert tool.name == "echo"


def test_tool_get_missing() -> None:
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None


def test_tool_get_or_raise_missing() -> None:
    from app.utils.exceptions import ToolNotFoundError

    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get_or_raise("nonexistent")


def test_function_spec_format() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool)
    specs = registry.function_specs()
    assert len(specs) == 1
    spec = specs[0]
    assert spec["type"] == "function"
    assert spec["function"]["name"] == "echo"
    assert "parameters" in spec["function"]


@pytest.mark.asyncio
async def test_echo_tool_execute() -> None:
    tool = _EchoTool()
    result = await tool.execute(text="hello world")
    assert result.success is True
    assert result.output == "hello world"


def test_load_all_tools_populates_registry() -> None:
    """After load_all_tools(), the global registry should have tools."""
    load_all_tools()
    registry = get_registry()
    assert len(registry) > 0
    assert "open_application" in registry
    assert "open_folder" in registry
    assert "create_folder" in registry
    assert "delete_folder" in registry
    assert "browser_search" in registry
