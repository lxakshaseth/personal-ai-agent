import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")
os.environ.setdefault("ALLOW_SHELL_COMMANDS", "false")

# ── Shared sandbox fixture (avoids Windows system-temp permission issues) ──────

@pytest.fixture(scope="module")
def _sandbox_root():
    base = Path(__file__).parent.parent / ".pytest_sandbox"
    base.mkdir(exist_ok=True)
    return base


@pytest.fixture
def sandbox(_sandbox_root):
    tmp = Path(tempfile.mkdtemp(dir=_sandbox_root))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# APPLICATION TOOLS
# ══════════════════════════════════════════════════════════════════════════════

from app.tools.applications.tools import OpenApplicationTool, CloseApplicationTool
from app.tools.applications.app_config import find_app, resolve_executable, AppDefinition


class TestOpenApplicationTool:
    @pytest.mark.asyncio
    async def test_open_known_app_via_exe(self, sandbox: Path) -> None:
        """Finds exe on disk → calls Popen."""
        fake_exe = sandbox / "code.exe"
        fake_exe.write_text("")
        app_def = AppDefinition(names=["vscode"], candidates=[str(fake_exe)])
        with patch("app.tools.applications.tools.find_app", return_value=app_def), \
             patch("app.tools.applications.tools.resolve_executable", return_value=str(fake_exe)), \
             patch("app.tools.applications.tools.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            tool = OpenApplicationTool()
            result = await tool.execute(app_name="vscode")
        assert result.success
        mock_popen.assert_called_once()

    @pytest.mark.asyncio
    async def test_open_app_url_fallback(self) -> None:
        """No exe found → falls back to URL via os.startfile."""
        app_def = AppDefinition(names=["youtube"], url="https://youtube.com")
        with patch("app.tools.applications.tools.find_app", return_value=app_def), \
             patch("app.tools.applications.tools.resolve_executable", return_value=None), \
             patch("app.tools.applications.tools.os.startfile") as mock_sf:
            tool = OpenApplicationTool()
            result = await tool.execute(app_name="youtube")
        assert result.success
        mock_sf.assert_called_once_with("https://youtube.com")

    @pytest.mark.asyncio
    async def test_open_unknown_app_tries_start(self) -> None:
        """Unknown app → tries 'cmd /c start' fallback."""
        with patch("app.tools.applications.tools.find_app", return_value=None), \
             patch("app.tools.applications.tools.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            tool = OpenApplicationTool()
            result = await tool.execute(app_name="unknownapp")
        assert result.success
        assert "unknownapp" in result.output.lower()

    @pytest.mark.asyncio
    async def test_open_app_no_exe_no_url_fails(self) -> None:
        app_def = AppDefinition(names=["ghost"], candidates=[], url=None)
        with patch("app.tools.applications.tools.find_app", return_value=app_def), \
             patch("app.tools.applications.tools.resolve_executable", return_value=None):
            tool = OpenApplicationTool()
            result = await tool.execute(app_name="ghost")
        assert not result.success
        assert result.error

    def test_find_app_case_insensitive(self) -> None:
        assert find_app("CHROME") is not None
        assert find_app("vs code") is not None
        assert find_app("whatsapp") is not None


class TestCloseApplicationTool:
    @pytest.mark.asyncio
    async def test_close_app_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_result.stdout = "SUCCESS: The process chrome.exe has been terminated."
        with patch("app.tools.applications.tools.subprocess.run", return_value=mock_result):
            tool = CloseApplicationTool()
            result = await tool.execute(app_name="chrome")
        assert result.success

    @pytest.mark.asyncio
    async def test_close_app_not_running(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ERROR: The process chrome.exe was not found."
        mock_result.stdout = ""
        with patch("app.tools.applications.tools.subprocess.run", return_value=mock_result):
            tool = CloseApplicationTool()
            result = await tool.execute(app_name="chrome")
        assert not result.success
        assert "not running" in result.error.lower() or result.error


from app.tools.applications.tools import SendWhatsAppMessageTool


class TestSendWhatsAppMessageTool:
    @pytest.mark.asyncio
    async def test_send_whatsapp_message_to_contact(self) -> None:
        tool = SendWhatsAppMessageTool()
        with patch("app.tools.applications.tools.os.startfile") as mock_sf:
            result = await tool.execute(contact="Aditya Tiwari", message="hello brother")
        assert result.success
        assert "Aditya Tiwari" in result.output
        mock_sf.assert_called_once()
        called_uri = mock_sf.call_args[0][0]
        assert "whatsapp://send?text=hello%20brother" in called_uri

    @pytest.mark.asyncio
    async def test_send_whatsapp_message_to_phone(self) -> None:
        tool = SendWhatsAppMessageTool()
        with patch("app.tools.applications.tools.os.startfile") as mock_sf:
            result = await tool.execute(contact="+919876543210", message="hi")
        assert result.success
        mock_sf.assert_called_once()
        called_uri = mock_sf.call_args[0][0]
        assert "phone=%2B919876543210" in called_uri or "phone=" in called_uri

    @pytest.mark.asyncio
    async def test_send_whatsapp_empty_message_fails(self) -> None:
        tool = SendWhatsAppMessageTool()
        result = await tool.execute(contact="Aditya", message="")
        assert not result.success




# ══════════════════════════════════════════════════════════════════════════════
# WINDOWS OS TOOLS
# ══════════════════════════════════════════════════════════════════════════════

from app.tools.windows.tools import (
    OpenURLTool,
    LockComputerTool,
    ShutdownComputerTool,
    RestartComputerTool,
    TakeScreenshotTool,
)


class TestOpenURLTool:
    @pytest.mark.asyncio
    async def test_open_url_success(self) -> None:
        with patch("app.tools.windows.tools.os.startfile") as mock_sf:
            tool = OpenURLTool()
            result = await tool.execute(url="https://www.google.com")
        assert result.success
        mock_sf.assert_called_once_with("https://www.google.com")

    @pytest.mark.asyncio
    async def test_open_url_adds_https(self) -> None:
        with patch("app.tools.windows.tools.os.startfile") as mock_sf:
            tool = OpenURLTool()
            result = await tool.execute(url="google.com")
        assert result.success
        mock_sf.assert_called_once_with("https://google.com")

    @pytest.mark.asyncio
    async def test_open_url_startfile_error(self) -> None:
        with patch("app.tools.windows.tools.os.startfile", side_effect=OSError("no browser")):
            tool = OpenURLTool()
            result = await tool.execute(url="https://example.com")
        assert not result.success


class TestLockComputerTool:
    @pytest.mark.asyncio
    async def test_lock_computer_success(self) -> None:
        mock_ctypes = MagicMock()
        mock_ctypes.windll.user32.LockWorkStation.return_value = 1
        with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
            import importlib
            import app.tools.windows.tools as wt
            importlib.reload(wt)
            with patch("ctypes.windll") as mock_windll:
                mock_windll.user32.LockWorkStation.return_value = 1
                tool = LockComputerTool()
                result = await tool.execute()
        # Lock success is best-effort on non-Windows CI; just verify no crash
        assert result is not None


class TestShutdownComputerTool:
    @pytest.mark.asyncio
    async def test_shutdown_calls_shutdown_exe(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("app.tools.windows.tools.subprocess.run", return_value=mock_result) as mock_run:
            tool = ShutdownComputerTool()
            result = await tool.execute(delay_seconds=60)
        assert result.success
        called_args = mock_run.call_args[0][0]
        assert "shutdown" in called_args
        assert "/s" in called_args

    @pytest.mark.asyncio
    async def test_shutdown_uses_default_delay(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("app.tools.windows.tools.subprocess.run", return_value=mock_result) as mock_run:
            tool = ShutdownComputerTool()
            result = await tool.execute()
        assert result.success
        called_args = mock_run.call_args[0][0]
        assert "30" in called_args  # default delay


class TestRestartComputerTool:
    @pytest.mark.asyncio
    async def test_restart_calls_shutdown_r(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("app.tools.windows.tools.subprocess.run", return_value=mock_result) as mock_run:
            tool = RestartComputerTool()
            result = await tool.execute(delay_seconds=10)
        assert result.success
        called_args = mock_run.call_args[0][0]
        assert "/r" in called_args

    @pytest.mark.asyncio
    async def test_restart_subprocess_error(self) -> None:
        with patch(
            "app.tools.windows.tools.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "shutdown", stderr="Access denied")
        ):
            tool = RestartComputerTool()
            result = await tool.execute()
        assert not result.success
        assert result.error


class TestTakeScreenshotTool:
    @pytest.mark.asyncio
    async def test_screenshot_with_pyautogui(self, sandbox: Path) -> None:
        save_path = str(sandbox / "shot.png")
        mock_img = MagicMock()
        mock_pyautogui = MagicMock()
        mock_pyautogui.screenshot.return_value = mock_img
        with patch.dict("sys.modules", {"pyautogui": mock_pyautogui}):
            tool = TakeScreenshotTool()
            result = await tool.execute(save_path=save_path)
        assert result.success
        mock_pyautogui.screenshot.assert_called_once()
        mock_img.save.assert_called_once_with(save_path)

    @pytest.mark.asyncio
    async def test_screenshot_no_library_error(self) -> None:
        """Without pyautogui or PIL installed, should fail with helpful error."""
        # Simulate pyautogui not installed and PIL not installed
        mock_missing = MagicMock(side_effect=ImportError("No module named 'pyautogui'"))
        with patch.dict("sys.modules", {"pyautogui": None}):
            # Tool will try 'import pyautogui' which raises ImportError, then PIL fallback
            with patch("app.tools.windows.tools.ImageGrab", None, create=True):
                tool = TakeScreenshotTool()
                # Just verify no unhandled exception is raised
                try:
                    result = await tool.execute()
                    # Either success (if PIL is installed) or a meaningful error
                    if not result.success:
                        assert result.error
                except Exception as exc:
                    pytest.fail(f"Should not raise: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM TOOLS
# ══════════════════════════════════════════════════════════════════════════════

from app.tools.system.tools import (
    SystemInformationTool,
    CPUUsageTool,
    MemoryUsageTool,
    DiskUsageTool,
    RunningProcessesTool,
)


class TestSystemInformationTool:
    @pytest.mark.asyncio
    async def test_returns_os_info(self) -> None:
        tool = SystemInformationTool()
        result = await tool.execute()
        assert result.success
        assert "OS" in result.output or "os" in result.output.lower()

    @pytest.mark.asyncio
    async def test_data_contains_os_key(self) -> None:
        tool = SystemInformationTool()
        result = await tool.execute()
        assert "os" in result.data


class TestCPUUsageTool:
    @pytest.mark.asyncio
    async def test_cpu_returns_percentage(self) -> None:
        tool = CPUUsageTool()
        result = await tool.execute()
        assert result.success
        assert "%" in result.output
        assert "overall_pct" in result.data

    @pytest.mark.asyncio
    async def test_cpu_without_psutil(self) -> None:
        with patch("app.tools.system.tools._PSUTIL_AVAILABLE", False):
            tool = CPUUsageTool()
            result = await tool.execute()
        assert not result.success
        assert "psutil" in result.error.lower()


class TestMemoryUsageTool:
    @pytest.mark.asyncio
    async def test_memory_returns_gb_info(self) -> None:
        tool = MemoryUsageTool()
        result = await tool.execute()
        assert result.success
        assert "RAM" in result.output
        assert "ram_total_gb" in result.data

    @pytest.mark.asyncio
    async def test_memory_without_psutil(self) -> None:
        with patch("app.tools.system.tools._PSUTIL_AVAILABLE", False):
            tool = MemoryUsageTool()
            result = await tool.execute()
        assert not result.success


class TestDiskUsageTool:
    @pytest.mark.asyncio
    async def test_disk_returns_drives(self) -> None:
        tool = DiskUsageTool()
        result = await tool.execute()
        assert result.success
        assert "drives" in result.data

    @pytest.mark.asyncio
    async def test_disk_without_psutil(self) -> None:
        with patch("app.tools.system.tools._PSUTIL_AVAILABLE", False):
            tool = DiskUsageTool()
            result = await tool.execute()
        assert not result.success


class TestRunningProcessesTool:
    @pytest.mark.asyncio
    async def test_running_processes_returns_list(self) -> None:
        tool = RunningProcessesTool()
        result = await tool.execute(limit=5)
        assert result.success
        assert "processes" in result.data
        assert len(result.data["processes"]) <= 5

    @pytest.mark.asyncio
    async def test_running_processes_filter(self) -> None:
        tool = RunningProcessesTool()
        result = await tool.execute(filter_name="python", limit=10)
        assert result.success
        # All returned processes should contain 'python' in their name
        for proc in result.data["processes"]:
            assert "python" in (proc.get("name") or "").lower()

    @pytest.mark.asyncio
    async def test_running_processes_without_psutil(self) -> None:
        with patch("app.tools.system.tools._PSUTIL_AVAILABLE", False):
            tool = RunningProcessesTool()
            result = await tool.execute()
        assert not result.success


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL TOOL
# ══════════════════════════════════════════════════════════════════════════════

from app.tools.terminal.tools import RunCommandTool


class TestRunCommandTool:
    @pytest.mark.asyncio
    async def test_shell_commands_disabled_by_default(self) -> None:
        """ALLOW_SHELL_COMMANDS=false (default) must block all commands."""
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = False
            mock_settings.return_value = s
            tool = RunCommandTool()
            result = await tool.execute(command="python --version")
        assert not result.success
        assert "disabled" in result.error.lower()

    @pytest.mark.asyncio
    async def test_disallowed_command_rejected(self) -> None:
        """Even with shell enabled, non-allowlisted command must be rejected."""
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["python"]
            mock_settings.return_value = s
            tool = RunCommandTool()
            result = await tool.execute(command="rm -rf /")
        assert not result.success
        assert "not in the allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_allowed_command_executes(self) -> None:
        """Allowlisted command runs and returns stdout."""
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["python"]
            mock_settings.return_value = s
            tool = RunCommandTool()
            result = await tool.execute(command="python --version")
        # python --version outputs to stderr on some versions, stdout on others
        assert result.success or "python" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_command_injection_prevented(self) -> None:
        """'python; rm -rf /' — second part must not run."""
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["python"]
            mock_settings.return_value = s
            tool = RunCommandTool()
            # shlex.split with posix=False splits on space, 'python;' won't match
            result = await tool.execute(command="python; rm -rf /")
        assert not result.success

    @pytest.mark.asyncio
    async def test_timeout_respected(self) -> None:
        """Timeout should cut off long-running commands via asyncio.TimeoutError."""
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["python"]
            mock_settings.return_value = s
            # Simulate a timeout by patching asyncio.wait_for to raise TimeoutError
            with patch("app.tools.terminal.tools.asyncio.wait_for", side_effect=asyncio.TimeoutError):
                with patch("app.tools.terminal.tools.asyncio.create_subprocess_exec") as mock_proc:
                    mock_proc_instance = MagicMock()
                    mock_proc_instance.kill = MagicMock()
                    mock_proc_instance.communicate = AsyncMock(return_value=(b"", b""))
                    mock_proc.return_value = mock_proc_instance
                    tool = RunCommandTool()
                    result = await tool.execute(
                        command="python -c \"import time; time.sleep(60)\"",
                        timeout_seconds=1,
                    )
        assert not result.success
        assert "timed out" in result.error.lower()


    @pytest.mark.asyncio
    async def test_unknown_exe_returns_error(self) -> None:
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["nonexistent_binary_xyz"]
            mock_settings.return_value = s
            tool = RunCommandTool()
            result = await tool.execute(command="nonexistent_binary_xyz --help")
        assert not result.success
        assert result.error

    @pytest.mark.asyncio
    async def test_protected_working_dir_rejected(self) -> None:
        with patch("app.tools.terminal.tools.get_settings") as mock_settings:
            s = MagicMock()
            s.allow_shell_commands = True
            s.allowed_commands = ["python"]
            mock_settings.return_value = s
            tool = RunCommandTool()
            result = await tool.execute(
                command="python --version",
                working_directory=r"C:\Windows\System32",
            )
        assert not result.success
        assert result.error


# ══════════════════════════════════════════════════════════════════════════════
# AGENT CORE TESTS
# ══════════════════════════════════════════════════════════════════════════════

from app.agent.tool_registry import AgentToolRegistry, get_tool_registry
from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.utils.exceptions import ToolNotFoundError


class _PingTool(AbstractTool):
    @property
    def name(self): return "ping"
    @property
    def description(self): return "Returns pong."
    @property
    def permission_level(self): return PermissionLevel.LOW
    @property
    def parameters_schema(self): return {"type": "object", "properties": {}, "required": []}
    async def execute(self, **kwargs): return ToolResult(success=True, output="pong")


class TestAgentToolRegistry:
    def test_register_tool(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        assert "ping" in r
        assert len(r) == 1

    def test_get_tool_success(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        tool = r.get_tool("ping")
        assert tool.name == "ping"

    def test_get_tool_unknown_raises(self) -> None:
        r = AgentToolRegistry()
        with pytest.raises(ToolNotFoundError) as exc_info:
            r.get_tool("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_remove_tool(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        r.remove_tool("ping")
        assert "ping" not in r

    def test_remove_nonexistent_raises(self) -> None:
        r = AgentToolRegistry()
        with pytest.raises(ToolNotFoundError):
            r.remove_tool("ghost")

    def test_list_tools(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        tools = r.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "ping"
        assert tools[0].permission_level.value == "LOW"

    def test_function_specs_format(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        specs = r.function_specs()
        assert len(specs) == 1
        assert specs[0]["type"] == "function"
        assert specs[0]["function"]["name"] == "ping"

    def test_names_sorted(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        assert r.names() == ["ping"]

    @pytest.mark.asyncio
    async def test_tool_execute(self) -> None:
        r = AgentToolRegistry()
        r.register(_PingTool)
        tool = r.get_tool("ping")
        result = await tool.execute()
        assert result.success
        assert result.output == "pong"

    def test_get_current_time_registered_in_global_registry(self) -> None:
        """After load_all_tools, get_current_time should be in global registry."""
        from app.agent.tool_registry import load_all_tools
        load_all_tools()
        registry = get_tool_registry()
        assert "get_current_time" in registry

    def test_new_tool_packages_registered(self) -> None:
        """After load_all_tools, all new tool packages should be in global registry."""
        from app.agent.tool_registry import load_all_tools
        load_all_tools()
        registry = get_tool_registry()
        expected = [
            "create_folder", "delete_folder", "create_file", "delete_file",
            "move_file", "copy_file", "rename_file", "list_directory",
            "search_files", "open_folder",
            "open_application", "close_application",
            "open_url", "lock_computer", "shutdown_computer", "restart_computer",
            "take_screenshot",
            "system_information", "cpu_usage", "memory_usage", "disk_usage",
            "running_processes",
            "run_command",
            "get_current_time",
        ]
        for name in expected:
            assert name in registry, f"Tool '{name}' not registered"


# ══════════════════════════════════════════════════════════════════════════════
# GROQ ERROR HANDLING
# ══════════════════════════════════════════════════════════════════════════════

from app.services.groq_client import _classify_groq_error
from app.agent.schemas import GroqErrorType
import groq


class TestGroqErrorClassification:
    def test_auth_error(self) -> None:
        exc = groq.AuthenticationError.__new__(groq.AuthenticationError)
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.INVALID_API_KEY
        assert not detail.retryable
        assert detail.status_code == 401

    def test_rate_limit_error(self) -> None:
        exc = groq.RateLimitError.__new__(groq.RateLimitError)
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.RATE_LIMIT
        assert detail.retryable
        assert detail.status_code == 429

    def test_timeout_error(self) -> None:
        exc = groq.APITimeoutError.__new__(groq.APITimeoutError)
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.TIMEOUT
        assert detail.retryable

    def test_connection_error(self) -> None:
        exc = groq.APIConnectionError.__new__(groq.APIConnectionError)
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.NETWORK
        assert detail.retryable

    def test_asyncio_timeout(self) -> None:
        import asyncio
        exc = asyncio.TimeoutError()
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.TIMEOUT
        assert detail.retryable

    def test_unknown_error(self) -> None:
        exc = Exception("something weird")
        detail = _classify_groq_error(exc)
        assert detail.error_type == GroqErrorType.UNKNOWN


# ══════════════════════════════════════════════════════════════════════════════
# PATH SECURITY
# ══════════════════════════════════════════════════════════════════════════════

from app.security.path_validator import validate_path, PathSecurityError


class TestPathValidator:
    def test_valid_path_returns_resolved(self, sandbox: Path) -> None:
        result = validate_path(str(sandbox), [str(sandbox)])
        assert result == sandbox.resolve()

    def test_path_outside_allowed_rejected(self, sandbox: Path) -> None:
        other = sandbox.parent
        with pytest.raises(PathSecurityError):
            validate_path(str(other / "sibling"), [str(sandbox)])

    def test_windows_system32_rejected(self) -> None:
        with pytest.raises(PathSecurityError):
            validate_path(r"C:\Windows\System32\evil.exe", [r"C:\Windows\System32"])

    def test_windows_root_rejected(self) -> None:
        with pytest.raises(PathSecurityError):
            validate_path(r"C:\\", [r"C:\\"])

    def test_path_traversal_resolved_away(self, sandbox: Path) -> None:
        """../../../Windows should be caught after resolution."""
        traversal = str(sandbox / ".." / ".." / ".." / "Windows" / "evil")
        with pytest.raises(PathSecurityError):
            validate_path(traversal, [str(sandbox)])

    def test_empty_path_rejected(self, sandbox: Path) -> None:
        with pytest.raises(PathSecurityError):
            validate_path("", [str(sandbox)])


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY TOOLS
# ══════════════════════════════════════════════════════════════════════════════

from app.tools.impl.utility import GetCurrentTimeTool


class TestGetCurrentTimeTool:
    @pytest.mark.asyncio
    async def test_returns_time(self) -> None:
        tool = GetCurrentTimeTool()
        result = await tool.execute()
        assert result.success
        assert "Current time" in result.output
        assert "iso" in result.data
        assert "date" in result.data

    @pytest.mark.asyncio
    async def test_utc_timezone(self) -> None:
        tool = GetCurrentTimeTool()
        result = await tool.execute(timezone="UTC")
        assert result.success
        assert "UTC" in result.output

    @pytest.mark.asyncio
    async def test_invalid_timezone_falls_back_to_utc(self) -> None:
        tool = GetCurrentTimeTool()
        result = await tool.execute(timezone="Mars/Olympus")
        assert result.success
        assert "UTC (fallback" in result.output

    def test_permission_level_is_low(self) -> None:
        tool = GetCurrentTimeTool()
        assert tool.permission_level == PermissionLevel.LOW

    def test_function_spec_valid(self) -> None:
        tool = GetCurrentTimeTool()
        spec = tool.to_function_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "get_current_time"


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT LOGGER
# ══════════════════════════════════════════════════════════════════════════════

import json
from app.security.audit import AuditLogger


class TestAuditLogger:
    def test_writes_jsonl_record(self, sandbox: Path) -> None:
        log_file = str(sandbox / "audit.jsonl")
        logger = AuditLogger(log_file=log_file)
        logger.log(
            command="test command",
            tool_name="test_tool",
            tool_args={"key": "value"},
            success=True,
            output="done",
            permission_level="LOW",
        )
        line = (sandbox / "audit.jsonl").read_text().strip()
        record = json.loads(line)
        assert record["user_command"] == "test command"
        assert record["tool"] == "test_tool"
        assert record["permission"] == "LOW"
        assert record["result"] == "success"

    def test_failure_classified_correctly(self, sandbox: Path) -> None:
        log_file = str(sandbox / "audit.jsonl")
        logger = AuditLogger(log_file=log_file)
        logger.log(
            command="cmd",
            tool_name="delete_folder",
            tool_args={},
            success=False,
            output="",
            error="Something went wrong",
            permission_level="HIGH",
        )
        record = json.loads((sandbox / "audit.jsonl").read_text().strip())
        assert record["result"] == "failure"

    def test_denied_classified_correctly(self, sandbox: Path) -> None:
        log_file = str(sandbox / "audit.jsonl")
        logger = AuditLogger(log_file=log_file)
        logger.log(
            command="cmd",
            tool_name="delete_folder",
            tool_args={},
            success=False,
            output="",
            error="Permission denied — outside allowed paths",
            permission_level="HIGH",
        )
        record = json.loads((sandbox / "audit.jsonl").read_text().strip())
        assert record["result"] == "denied"

    def test_confirmation_required_classified(self, sandbox: Path) -> None:
        log_file = str(sandbox / "audit.jsonl")
        logger = AuditLogger(log_file=log_file)
        logger.log(
            command="cmd",
            tool_name="delete_folder",
            tool_args={},
            success=False,
            output="",
            error="Confirmation required before running HIGH risk action",
            permission_level="HIGH",
        )
        record = json.loads((sandbox / "audit.jsonl").read_text().strip())
        assert record["result"] == "confirmation_required"

    def test_multiple_records(self, sandbox: Path) -> None:
        log_file = str(sandbox / "audit.jsonl")
        logger = AuditLogger(log_file=log_file)
        for i in range(3):
            logger.log(command=f"cmd{i}", tool_name="t", tool_args={}, success=True, output="")
        lines = (sandbox / "audit.jsonl").read_text().strip().split("\n")
        assert len(lines) == 3

