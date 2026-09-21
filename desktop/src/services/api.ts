import {
  AgentConfig,
  AgentTask,
  AuditLogEntry,
  CommandHistoryItem,
  ConfirmationTicket,
  SecuritySettings,
  ToolInfo,
} from '../types/agent';
import { SystemMetrics } from '../types/system';

const API_BASE = 'http://127.0.0.1:8000';

async function fetchJSON<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status} ${res.statusText}`;
    try {
      const err = await res.json();
      if (err.detail) detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail);
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  // Health & Readiness
  checkHealth: () => fetchJSON<{ status: string; service: string; version: string }>('/health'),
  checkReadiness: () => fetchJSON<{ status: string; service: string; version: string; checks: Record<string, any> }>('/ready'),

  // Status
  getStatus: () =>
    fetchJSON<{
      status: string;
      detail: string;
      active_model: string;
      voice_enabled: boolean;
      stt_provider: string;
      tts_provider: string;
      wake_word: string;
      wake_word_enabled: boolean;
    }>('/agent/status'),

  // Run command
  runCommand: (command: string, confirmed = false, sessionId?: string) =>
    fetchJSON<{
      success: boolean;
      response: string;
      tool_calls: Array<{
        tool: string;
        args: Record<string, any>;
        success: boolean;
        output: string;
        error?: string | null;
      }>;
      error?: string | null;
    }>('/agent/run', {
      method: 'POST',
      body: JSON.stringify({ command, confirmed, session_id: sessionId }),
    }),

  // Tools
  getTools: () => fetchJSON<{ count: number; tools: ToolInfo[] }>('/agent/tools'),
  executeTool: (toolName: string, args: Record<string, any> = {}, confirmed = false) =>
    fetchJSON<{ tool: string; success: boolean; output: string; error?: string | null }>(
      `/agent/tools/${encodeURIComponent(toolName)}/execute`,
      {
        method: 'POST',
        body: JSON.stringify({ args, confirmed }),
      }
    ),

  // Confirmations
  getConfirmations: () => fetchJSON<ConfirmationTicket[]>('/agent/confirmations/pending'),
  respondConfirmation: (ticketId: string, approved: boolean) =>
    fetchJSON<{ status: string; ticket_id: string; approved: boolean }>(
      `/agent/confirmations/${encodeURIComponent(ticketId)}/respond`,
      {
        method: 'POST',
        body: JSON.stringify({ approved }),
      }
    ),

  // History
  getHistory: () => fetchJSON<CommandHistoryItem[]>('/agent/history'),
  clearHistory: () => fetchJSON<{ status: string }>('/agent/history', { method: 'DELETE' }),

  // Memory
  getMemory: () => fetchJSON<Record<string, any>>('/agent/memory'),
  setMemory: (key: string, value: any, ttl?: number) =>
    fetchJSON<{ status: string; key: string }>('/agent/memory', {
      method: 'POST',
      body: JSON.stringify({ key, value, ttl }),
    }),
  deleteMemory: (key: string) =>
    fetchJSON<{ status: string; key: string }>(`/agent/memory/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    }),
  clearMemory: () => fetchJSON<{ status: string }>('/agent/memory', { method: 'DELETE' }),

  // Security
  getSecuritySettings: () => fetchJSON<SecuritySettings>('/agent/security/settings'),
  updateSecuritySettings: (settings: Partial<SecuritySettings>) =>
    fetchJSON<SecuritySettings>('/agent/security/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    }),
  getAuditLogs: (limit = 100) => fetchJSON<AuditLogEntry[]>(`/agent/logs/audit?limit=${limit}`),

  // Tasks
  getTasks: (state?: string) =>
    fetchJSON<AgentTask[]>(state ? `/agent/tasks?state=${encodeURIComponent(state)}` : '/agent/tasks'),
  getTask: (taskId: string) => fetchJSON<AgentTask>(`/agent/tasks/${encodeURIComponent(taskId)}`),
  getActiveTask: () => fetchJSON<AgentTask | null>('/agent/tasks/active'),
  approveTask: (taskId: string) =>
    fetchJSON<{ success: boolean; task_id: string; response: string; steps: any[] }>(
      `/agent/tasks/${encodeURIComponent(taskId)}/approve`,
      { method: 'POST' }
    ),
  pauseTask: (taskId: string) => fetchJSON<{ status: string; task_id: string }>(`/agent/tasks/${encodeURIComponent(taskId)}/pause`, { method: 'POST' }),
  resumeTask: (taskId: string) => fetchJSON<{ status: string; task_id: string }>(`/agent/tasks/${encodeURIComponent(taskId)}/resume`, { method: 'POST' }),
  cancelTask: (taskId: string) => fetchJSON<{ status: string; task_id: string }>(`/agent/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }),
  cancelActiveTask: () => fetchJSON<{ status: string }>('/agent/cancel', { method: 'POST' }),

  // Config
  getConfig: () => fetchJSON<AgentConfig>('/agent/config'),
  updateConfig: (updates: Partial<AgentConfig>) =>
    fetchJSON<{ status: string; config: AgentConfig }>('/agent/config', {
      method: 'POST',
      body: JSON.stringify(updates),
    }),

  // Voice
  triggerListen: () =>
    fetchJSON<{
      success: boolean;
      transcript?: string;
      response?: string;
      tool_calls?: any[];
      error?: string;
    }>('/agent/voice/listen', { method: 'POST' }),
  speakText: (text: string) =>
    fetchJSON<{ status: string; text: string }>('/agent/voice/speak', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // System
  getSystemMetrics: () => fetchJSON<SystemMetrics>('/system/metrics'),
};
