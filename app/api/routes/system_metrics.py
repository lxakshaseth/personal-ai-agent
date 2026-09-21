"""
System metrics API route for desktop monitoring.
"""
from __future__ import annotations

import logging
import platform
import time
from typing import Any

import psutil
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["System"])

_BOOT_TIME = psutil.boot_time()


class DiskPartitionMetric(BaseModel):
    mountpoint: str
    fstype: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class ProcessMetric(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str


class SystemMetricsResponse(BaseModel):
    timestamp: float
    uptime_seconds: float
    os_name: str
    os_version: str
    architecture: str
    cpu_percent: float
    cpu_per_core: list[float]
    cpu_cores_logical: int
    cpu_cores_physical: int
    memory_total_gb: float
    memory_used_gb: float
    memory_available_gb: float
    memory_percent: float
    swap_percent: float
    disks: list[DiskPartitionMetric]
    top_processes: list[ProcessMetric]


@router.get("/metrics", response_model=SystemMetricsResponse)
async def get_system_metrics() -> SystemMetricsResponse:
    """Return real-time hardware telemetry and running processes."""
    # CPU
    cpu_per_core = psutil.cpu_percent(interval=0.05, percpu=True)
    cpu_overall = sum(cpu_per_core) / len(cpu_per_core) if cpu_per_core else 0.0

    # Memory
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    # Disks
    disks: list[DiskPartitionMetric] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(
                DiskPartitionMetric(
                    mountpoint=part.mountpoint,
                    fstype=part.fstype,
                    total_gb=round(usage.total / (1024**3), 2),
                    used_gb=round(usage.used / (1024**3), 2),
                    free_gb=round(usage.free / (1024**3), 2),
                    percent=usage.percent,
                )
            )
        except (PermissionError, OSError):
            continue

    # Top processes
    procs: list[ProcessMetric] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = p.info
            procs.append(
                ProcessMetric(
                    pid=info["pid"],
                    name=info["name"] or "Unknown",
                    cpu_percent=round(info["cpu_percent"] or 0.0, 1),
                    memory_percent=round(info["memory_percent"] or 0.0, 1),
                    status=info["status"] or "running",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort top processes by CPU and limit to 10
    top_procs = sorted(procs, key=lambda x: (x.cpu_percent, x.memory_percent), reverse=True)[:10]

    return SystemMetricsResponse(
        timestamp=time.time(),
        uptime_seconds=round(time.time() - _BOOT_TIME, 1),
        os_name=platform.system(),
        os_version=platform.version(),
        architecture=platform.machine(),
        cpu_percent=round(cpu_overall, 1),
        cpu_per_core=[round(c, 1) for c in cpu_per_core],
        cpu_cores_logical=psutil.cpu_count(logical=True) or 1,
        cpu_cores_physical=psutil.cpu_count(logical=False) or 1,
        memory_total_gb=round(mem.total / (1024**3), 2),
        memory_used_gb=round(mem.used / (1024**3), 2),
        memory_available_gb=round(mem.available / (1024**3), 2),
        memory_percent=mem.percent,
        swap_percent=swap.percent,
        disks=disks,
        top_processes=top_procs,
    )
