import React from 'react';
import { useSystemStore } from '../stores/systemStore';
import {
  Activity,
  Cpu,
  HardDrive,
  Clock,
  Layers,
  Monitor,
  RefreshCw,
} from 'lucide-react';

export const SystemStatusPage: React.FC = () => {
  const [systemState] = useSystemStore();
  const metrics = systemState.metrics;

  if (!metrics) {
    return (
      <div className="p-8 text-center text-slate-500 text-xs">
        Connecting to system telemetry service...
      </div>
    );
  }

  const formatUptime = (seconds: number) => {
    const d = Math.floor(seconds / (3600 * 24));
    const h = Math.floor((seconds % (3600 * 24)) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${d > 0 ? `${d}d ` : ''}${h}h ${m}m`;
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <span>Windows System Telemetry</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Real-time hardware performance metrics, storage partitions, and active processes.
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono text-slate-400 bg-slate-900 px-3 py-1.5 rounded-xl border border-slate-800">
          <Monitor className="w-3.5 h-3.5 text-cyan-400" />
          <span>{metrics.os_name} {metrics.architecture}</span>
          <span className="text-slate-600">|</span>
          <Clock className="w-3.5 h-3.5 text-purple-400" />
          <span>Uptime: {formatUptime(metrics.uptime_seconds)}</span>
        </div>
      </div>

      {/* Top 3 Metric Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* CPU Overall */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-white">CPU Performance</h3>
            </div>
            <span className="font-mono text-xl font-bold text-cyan-400">{metrics.cpu_percent}%</span>
          </div>

          <div className="h-16 flex items-end gap-1 pt-2">
            {systemState.cpuHistory.map((val, idx) => (
              <div
                key={idx}
                className="flex-1 bg-cyan-500/30 hover:bg-cyan-400 rounded-t transition-all duration-300"
                style={{ height: `${Math.max(10, val)}%` }}
                title={`CPU: ${val}%`}
              />
            ))}
          </div>
          <div className="flex justify-between text-[11px] text-slate-500">
            <span>{metrics.cpu_cores_physical} Physical Cores</span>
            <span>{metrics.cpu_cores_logical} Logical Threads</span>
          </div>
        </div>

        {/* RAM Usage */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-white">RAM Utilization</h3>
            </div>
            <span className="font-mono text-xl font-bold text-purple-400">{metrics.memory_percent}%</span>
          </div>

          <div className="h-16 flex items-end gap-1 pt-2">
            {systemState.memoryHistory.map((val, idx) => (
              <div
                key={idx}
                className="flex-1 bg-purple-500/30 hover:bg-purple-400 rounded-t transition-all duration-300"
                style={{ height: `${Math.max(10, val)}%` }}
                title={`Memory: ${val}%`}
              />
            ))}
          </div>
          <div className="flex justify-between text-[11px] text-slate-500">
            <span>Used: {metrics.memory_used_gb} GB</span>
            <span>Total: {metrics.memory_total_gb} GB</span>
          </div>
        </div>

        {/* Storage Snapshot */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-semibold text-white">System Storage</h3>
            </div>
            <span className="font-mono text-xl font-bold text-emerald-400">
              {metrics.disks?.[0]?.percent || 0}%
            </span>
          </div>

          <div className="space-y-2 pt-2">
            {metrics.disks.map((d, i) => (
              <div key={i} className="text-xs">
                <div className="flex justify-between text-[11px] mb-1">
                  <span className="font-mono text-slate-300">{d.mountpoint} ({d.fstype})</span>
                  <span className="text-slate-400">{d.free_gb} GB free / {d.total_gb} GB</span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-400 h-full rounded-full"
                    style={{ width: `${d.percent}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Per-Core Breakdown */}
      <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white">Per-Core CPU Utilization</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {metrics.cpu_per_core.map((coreVal, i) => (
            <div key={i} className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 text-center">
              <span className="text-[11px] text-slate-400 font-mono block mb-1">Core {i}</span>
              <span className="text-sm font-bold text-cyan-300 font-mono">{coreVal}%</span>
              <div className="w-full bg-slate-800 h-1 rounded-full mt-2 overflow-hidden">
                <div
                  className="bg-cyan-400 h-full rounded-full transition-all duration-300"
                  style={{ width: `${coreVal}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Top 10 Running Processes */}
      <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Active Windows Processes</h3>
          <span className="text-xs text-slate-500">Sorted by CPU load</span>
        </div>

        <div className="border border-slate-800 rounded-xl overflow-hidden text-xs">
          <table className="w-full text-left font-mono">
            <thead className="bg-slate-900 border-b border-slate-800 text-slate-400 font-sans">
              <tr>
                <th className="p-3">PID</th>
                <th className="p-3">Process Name</th>
                <th className="p-3">CPU %</th>
                <th className="p-3">Memory %</th>
                <th className="p-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              {metrics.top_processes.map((proc) => (
                <tr key={proc.pid} className="hover:bg-slate-900/40">
                  <td className="p-3 text-slate-500">{proc.pid}</td>
                  <td className="p-3 text-white font-medium">{proc.name}</td>
                  <td className="p-3 text-cyan-300">{proc.cpu_percent}%</td>
                  <td className="p-3 text-purple-300">{proc.memory_percent}%</td>
                  <td className="p-3">
                    <span className="px-2 py-0.5 rounded bg-emerald-950/40 text-emerald-400 text-[10px] font-sans">
                      {proc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
