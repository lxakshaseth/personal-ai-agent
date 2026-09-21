import React, { useState, useEffect } from 'react';
import { SecuritySettings } from '../types/agent';
import { api } from '../services/api';
import {
  ShieldCheck,
  FolderLock,
  Terminal,
  Globe,
  Trash2,
  MessageCircle,
  Power,
  RefreshCw,
  Lock,
  Sliders,
  CheckCircle2,
} from 'lucide-react';

export const SecurityPage: React.FC = () => {
  const [security, setSecurity] = useState<SecuritySettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const loadSecurity = async () => {
    setIsLoading(true);
    try {
      const data = await api.getSecuritySettings();
      setSecurity(data);
    } catch (e) {
      console.error('Failed to load security settings', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadSecurity();
  }, []);

  const handleToggle = async (key: keyof SecuritySettings, currentValue: boolean) => {
    if (!security) return;
    setUpdatingKey(key);
    setSaveStatus(null);

    const newValue = !currentValue;
    try {
      const updated = await api.updateSecuritySettings({
        [key]: newValue,
      });
      setSecurity(updated);
      setSaveStatus(`Updated ${key} to ${newValue ? 'Enabled' : 'Disabled'}`);
      setTimeout(() => setSaveStatus(null), 3000);
    } catch (err: any) {
      console.error(`Failed to update ${key}`, err);
      alert(`Error updating ${key}: ${err.message || 'Request failed'}`);
    } finally {
      setUpdatingKey(null);
    }
  };

  if (isLoading || !security) {
    return (
      <div className="p-8 text-center text-slate-500 text-xs">
        Loading security policies...
      </div>
    );
  }

  const controls = [
    {
      key: 'allow_shell_commands' as const,
      label: 'Shell Access (Terminal)',
      description: 'Allow arbitrary command execution via Windows Terminal / PowerShell subprocesses.',
      icon: Terminal,
      value: security.allow_shell_commands,
      risk: 'HIGH RISK',
      riskColor: 'text-amber-400 bg-amber-950/40 border-amber-800/40',
    },
    {
      key: 'allow_file_deletion' as const,
      label: 'File Deletion',
      description: 'Allow permanent deletion of files (delete_file) and directories (delete_folder).',
      icon: Trash2,
      value: security.allow_file_deletion,
      risk: 'HIGH RISK',
      riskColor: 'text-rose-400 bg-rose-950/40 border-rose-800/40',
    },
    {
      key: 'allow_browser_automation' as const,
      label: 'Browser Automation',
      description: 'Allow opening URLs, browser launches, and web navigation actions.',
      icon: Globe,
      value: security.allow_browser_automation,
      risk: 'MODERATE',
      riskColor: 'text-cyan-400 bg-cyan-950/40 border-cyan-800/40',
    },
    {
      key: 'allow_whatsapp_messaging' as const,
      label: 'WhatsApp Messaging',
      description: 'Allow sending WhatsApp messages and interacting with messaging targets.',
      icon: MessageCircle,
      value: security.allow_whatsapp_messaging,
      risk: 'MODERATE',
      riskColor: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/40',
    },
    {
      key: 'allow_system_controls' as const,
      label: 'System Controls',
      description: 'Allow computer shutdown, system restart, and power-state management operations.',
      icon: Power,
      value: security.allow_system_controls,
      risk: 'CRITICAL',
      riskColor: 'text-purple-400 bg-purple-950/40 border-purple-800/40',
    },
  ];

  return (
    <div className="p-8 space-y-6 max-w-5xl mx-auto overflow-y-auto h-[calc(100vh-4rem)] select-none">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <span>Security & Sandboxing Controls</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Enforce granular Windows security policies, tool permissions, and interactive execution gates.
          </p>
        </div>

        <button
          onClick={loadSecurity}
          className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors"
          title="Refresh Policies"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Safety Posture Summary Banner */}
      <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/30 rounded-2xl p-6 flex items-center justify-between shadow-lg">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-emerald-500/20 border border-emerald-500/40 rounded-2xl text-emerald-400">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-white">Protected Execution Environment</h3>
            <p className="text-xs text-slate-300 mt-0.5">
              Path traversal is blocked, shell commands are disabled by default, and high-risk actions require interactive approval.
            </p>
          </div>
        </div>

        <div className="text-right">
          <span className="px-3 py-1 bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 rounded-full font-mono text-xs font-bold block">
            STRICT ENFORCEMENT
          </span>
          {saveStatus && (
            <span className="text-[11px] text-emerald-400 font-mono mt-1 block flex items-center gap-1 justify-end">
              <CheckCircle2 className="w-3 h-3" />
              <span>Saved</span>
            </span>
          )}
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────── */}
      {/* 5 GRANULAR DOMAIN TOGGLE CONTROLS                             */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Access & Execution Permissions</h3>
          </div>
          <span className="text-xs text-slate-500 font-mono">Enforced by backend PermissionChecker</span>
        </div>

        <div className="divide-y divide-slate-800/60">
          {controls.map((item) => {
            const Icon = item.icon;
            const isUpdating = updatingKey === item.key;
            return (
              <div key={item.key} className="py-4 flex items-center justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 mt-0.5">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-white">{item.label}</span>
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${item.riskColor}`}>
                        {item.risk}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-0.5 max-w-xl">{item.description}</p>
                  </div>
                </div>

                {/* Toggle Button */}
                <button
                  type="button"
                  disabled={isUpdating}
                  onClick={() => handleToggle(item.key, item.value)}
                  className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                    item.value ? 'bg-cyan-600' : 'bg-slate-800'
                  } ${isUpdating ? 'opacity-50' : ''}`}
                >
                  <span
                    className={`inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                      item.value ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            );
          })}

          {/* Interactive Confirmation Policy Toggle */}
          <div className="py-4 flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 mt-0.5">
                <Lock className="w-4 h-4 text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-white">Require Confirmation for Dangerous Tools</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded border text-emerald-400 bg-emerald-950/40 border-emerald-800/40">
                    GATEWAY
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5 max-w-xl">
                  Enforces interactive pop-up confirmation modals in desktop UI before executing HIGH-risk operations.
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={updatingKey === 'require_confirmation'}
              onClick={() => handleToggle('require_confirmation', security.require_confirmation)}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                security.require_confirmation ? 'bg-emerald-600' : 'bg-slate-800'
              }`}
            >
              <span
                className={`inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                  security.require_confirmation ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Allowed Base Paths */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <FolderLock className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Filesystem Sandboxed Roots</h3>
          </div>
          <p className="text-xs text-slate-400">
            Filesystem tools are strictly confined within these configured base directories. Access outside is blocked.
          </p>

          <div className="space-y-1.5 pt-2">
            {security.allowed_base_paths.map((p, idx) => (
              <div
                key={idx}
                className="bg-slate-950/70 border border-slate-800/80 rounded-lg p-2.5 font-mono text-xs text-cyan-300 flex items-center justify-between"
              >
                <span className="truncate pr-2">{p}</span>
                <span className="text-[10px] text-emerald-400 font-sans font-medium flex-shrink-0">ALLOWED</span>
              </div>
            ))}
          </div>
        </div>

        {/* Allowlisted Terminal Executables */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">Allowlisted Executables</h3>
          </div>
          <p className="text-xs text-slate-400">
            When shell commands are enabled, only these approved executables and safe CLI tools are permitted.
          </p>

          <div className="flex flex-wrap gap-1.5 pt-2">
            {security.allowed_commands.map((cmd) => (
              <span
                key={cmd}
                className="font-mono text-[11px] px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700/80 text-slate-300"
              >
                {cmd}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Risk Policies Table */}
      <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white">Operation Risk Classification</h3>
        <div className="border border-slate-800 rounded-xl overflow-hidden text-xs">
          <table className="w-full text-left">
            <thead className="bg-slate-900 border-b border-slate-800 text-slate-400">
              <tr>
                <th className="p-3 font-medium">Level</th>
                <th className="p-3 font-medium">Criteria & Examples</th>
                <th className="p-3 font-medium">Execution Policy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-300">
              <tr>
                <td className="p-3 font-bold text-emerald-400 font-mono">LOW</td>
                <td className="p-3">
                  Read-only operations: list directory, search files, screenshot, system info, memory inspection.
                </td>
                <td className="p-3 text-slate-400">Direct automatic execution.</td>
              </tr>
              <tr>
                <td className="p-3 font-bold text-blue-400 font-mono">MEDIUM</td>
                <td className="p-3">
                  Modifying non-destructive operations: open apps, create text files, lock screen, create folders.
                </td>
                <td className="p-3 text-slate-400">Permitted within sandboxed paths.</td>
              </tr>
              <tr>
                <td className="p-3 font-bold text-rose-400 font-mono">HIGH</td>
                <td className="p-3">
                  Potentially destructive actions: delete files/folders, shutdown/restart, terminal execution.
                </td>
                <td className="p-3 text-amber-300 font-medium">
                  Requires explicit interactive confirmation.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
