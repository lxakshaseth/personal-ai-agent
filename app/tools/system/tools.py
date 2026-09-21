"""
System information tools — read-only system metrics via psutil.

Registered tools:
  system_information   LOW  OS, CPU, RAM, uptime summary
  cpu_usage            LOW  per-core and overall CPU percentage
  memory_usage         LOW  RAM and swap usage
  disk_usage           LOW  disk space per drive
  running_processes    LOW  list of running processes (top by CPU)
"""
from __future__ import annotations

import logging
import platform
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agent.tool_registry import register_tool
from app.tools.base import AbstractTool, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)

# ── psutil import with graceful fallback ──────────────────────────────────────
try:
    import psutil  # type: ignore
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    logger.warning("psutil is not installed — system tools will return limited info. Install with: pip install psutil")


def _psutil_required() -> ToolResult | None:
    if not _PSUTIL_AVAILABLE:
        return ToolResult(
            success=False,
            output="",
            error="psutil is not installed. Run: pip install psutil",
        )
    return None


@register_tool
class SystemInformationTool(AbstractTool):
    """Return an overview of the operating system, CPU, memory, and uptime."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "system_information"
    @property
    def description(self) -> str:
        return (
            "Get system information: OS version, CPU model, RAM, disk, and uptime. "
            "Use when the user asks 'what's my system info', 'tell me about this PC', etc."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        info: dict[str, Any] = {
            "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "machine": platform.machine(),
            "processor": platform.processor() or "Unknown",
            "python": platform.python_version(),
            "hostname": platform.node(),
        }
        lines = [
            f"OS:        {info['os']}",
            f"Machine:   {info['machine']}",
            f"Processor: {info['processor']}",
            f"Hostname:  {info['hostname']}",
            f"Python:    {info['python']}",
        ]

        if _PSUTIL_AVAILABLE:
            try:
                boot_ts = psutil.boot_time()
                uptime_secs = (datetime.now(tz=timezone.utc).timestamp()) - boot_ts
                uptime = str(timedelta(seconds=int(uptime_secs)))
                ram = psutil.virtual_memory()
                total_ram = ram.total / (1024 ** 3)
                available_ram = ram.available / (1024 ** 3)
                cpu_count = psutil.cpu_count(logical=True)
                info.update({
                    "uptime": uptime,
                    "ram_total_gb": round(total_ram, 2),
                    "ram_available_gb": round(available_ram, 2),
                    "cpu_cores": cpu_count,
                })
                lines += [
                    f"CPU Cores: {cpu_count} (logical)",
                    f"RAM:       {available_ram:.1f} GB free / {total_ram:.1f} GB total",
                    f"Uptime:    {uptime}",
                ]
            except Exception as e:
                logger.warning("psutil query failed: %s", e)

        return ToolResult(success=True, output="\n".join(lines), data=info)


@register_tool
class CPUUsageTool(AbstractTool):
    """Report current CPU utilisation (overall and per-core)."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "cpu_usage"
    @property
    def description(self) -> str:
        return "Get the current CPU usage percentage (overall and per-core). Useful for 'how busy is my CPU'."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _psutil_required()
        if err:
            return err
        try:
            overall = psutil.cpu_percent(interval=0.5)
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            freq = psutil.cpu_freq()
            freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
            lines = [f"Overall CPU: {overall}%", f"Frequency:   {freq_str}"]
            for i, pct in enumerate(per_core):
                lines.append(f"  Core {i}: {pct}%")
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"overall_pct": overall, "per_core_pct": per_core, "frequency_mhz": freq.current if freq else None},
            )
        except Exception as e:
            logger.exception("cpu_usage failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class MemoryUsageTool(AbstractTool):
    """Report RAM and swap usage."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "memory_usage"
    @property
    def description(self) -> str:
        return "Get current RAM and swap memory usage. Use for 'how much memory is being used'."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _psutil_required()
        if err:
            return err
        try:
            ram = psutil.virtual_memory()
            swap = psutil.swap_memory()
            gb = 1024 ** 3

            data = {
                "ram_total_gb": round(ram.total / gb, 2),
                "ram_used_gb": round(ram.used / gb, 2),
                "ram_available_gb": round(ram.available / gb, 2),
                "ram_percent": ram.percent,
                "swap_total_gb": round(swap.total / gb, 2),
                "swap_used_gb": round(swap.used / gb, 2),
                "swap_percent": swap.percent,
            }

            lines = [
                f"RAM:  {ram.used / gb:.1f} GB used / {ram.total / gb:.1f} GB total ({ram.percent}%)",
                f"Swap: {swap.used / gb:.1f} GB used / {swap.total / gb:.1f} GB total ({swap.percent}%)",
            ]
            return ToolResult(success=True, output="\n".join(lines), data=data)
        except Exception as e:
            logger.exception("memory_usage failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class DiskUsageTool(AbstractTool):
    """Report disk space usage for all mounted drives."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "disk_usage"
    @property
    def description(self) -> str:
        return "Get disk space usage for all drives. Use for 'how much disk space do I have'."
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _psutil_required()
        if err:
            return err
        try:
            gb = 1024 ** 3
            partitions = psutil.disk_partitions()
            lines = []
            data = []
            for p in partitions:
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    lines.append(
                        f"{p.mountpoint:<8} {usage.used / gb:.1f} GB used / {usage.total / gb:.1f} GB total ({usage.percent}%)"
                    )
                    data.append({
                        "drive": p.mountpoint,
                        "fs": p.fstype,
                        "total_gb": round(usage.total / gb, 2),
                        "used_gb": round(usage.used / gb, 2),
                        "free_gb": round(usage.free / gb, 2),
                        "percent": usage.percent,
                    })
                except (PermissionError, OSError):
                    lines.append(f"{p.mountpoint:<8} (access denied)")
            return ToolResult(success=True, output="\n".join(lines) or "No drives found.", data={"drives": data})
        except Exception as e:
            logger.exception("disk_usage failed")
            return ToolResult(success=False, output="", error=str(e))


@register_tool
class RunningProcessesTool(AbstractTool):
    """List the top running processes by CPU usage."""

    requires_confirmation: bool = False

    @property
    def name(self) -> str: return "running_processes"
    @property
    def description(self) -> str:
        return (
            "List currently running processes sorted by CPU usage. "
            "Use for 'what's running', 'which processes are active', 'is X running'."
        )
    @property
    def permission_level(self) -> PermissionLevel: return PermissionLevel.LOW
    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max number of processes to return", "default": 20},
                "filter_name": {"type": "string", "description": "Optional: filter by process name substring", "default": ""},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        err = _psutil_required()
        if err:
            return err
        limit: int = min(int(kwargs.get("limit", 20)), 100)
        filter_name: str = kwargs.get("filter_name", "").strip().lower()
        try:
            procs = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
                try:
                    info = proc.info
                    if filter_name and filter_name not in (info.get("name") or "").lower():
                        continue
                    procs.append(info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            # Brief stabilisation so cpu_percent is meaningful
            import time
            time.sleep(0.1)
            procs.sort(key=lambda p: p.get("cpu_percent") or 0, reverse=True)
            procs = procs[:limit]

            lines = [f"{'PID':>6}  {'CPU%':>5}  {'MEM%':>5}  NAME"]
            for p in procs:
                lines.append(
                    f"{p.get('pid', '?'):>6}  "
                    f"{(p.get('cpu_percent') or 0):>5.1f}  "
                    f"{(p.get('memory_percent') or 0):>5.1f}  "
                    f"{p.get('name', 'unknown')}"
                )

            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={"processes": procs, "count": len(procs)},
            )
        except Exception as e:
            logger.exception("running_processes failed")
            return ToolResult(success=False, output="", error=str(e))
