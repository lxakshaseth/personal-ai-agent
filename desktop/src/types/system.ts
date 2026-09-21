export interface DiskPartition {
  mountpoint: string;
  fstype: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  percent: number;
}

export interface ProcessMetric {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
}

export interface SystemMetrics {
  timestamp: number;
  uptime_seconds: number;
  os_name: string;
  os_version: string;
  architecture: string;
  cpu_percent: number;
  cpu_per_core: number[];
  cpu_cores_logical: number;
  cpu_cores_physical: number;
  memory_total_gb: number;
  memory_used_gb: number;
  memory_available_gb: number;
  memory_percent: number;
  swap_percent: number;
  disks: DiskPartition[];
  top_processes: ProcessMetric[];
}
