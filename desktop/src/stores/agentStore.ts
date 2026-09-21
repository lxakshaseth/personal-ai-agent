import { useState, useEffect } from 'react';
import { AgentStatusType, AgentTask, ChatMessage, CommandHistoryItem, ConfirmationTicket } from '../types/agent';
import { TimelineItem, ActiveExecutionState } from '../types/timeline';
import { api } from '../services/api';
import { wsClient } from '../services/websocket';

interface AgentState {
  status: AgentStatusType;
  statusDetail: string;
  isConnected: boolean;
  activeModel: string;
  messages: ChatMessage[];
  history: CommandHistoryItem[];
  tasks: AgentTask[];
  activeTask: AgentTask | null;
  pendingConfirmations: ConfirmationTicket[];
  currentTool: string | null;
  voiceTranscript: string;
  timeline: TimelineItem[];
  activeExecution: ActiveExecutionState | null;
}

const defaultState: AgentState = {
  status: 'offline',
  statusDetail: 'Connecting to agent backend...',
  isConnected: false,
  activeModel: 'openai/gpt-oss-120b',
  messages: [
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello! I am NOVA AI, your Windows AI Agent. How can I help you today?',
      timestamp: Date.now(),
    },
  ],
  history: [],
  tasks: [],
  activeTask: null,
  pendingConfirmations: [],
  currentTool: null,
  voiceTranscript: '',
  timeline: [],
  activeExecution: null,
};

type Listener = (state: AgentState) => void;
let state: AgentState = { ...defaultState };
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((listener) => listener(state));
}

export const agentStore = {
  getState: () => state,
  setState: (partial: Partial<AgentState>) => {
    state = { ...state, ...partial };
    notify();
  },
  subscribe: (listener: Listener) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },

  // Actions
  addMessage: (msg: ChatMessage) => {
    state = { ...state, messages: [...state.messages, msg] };
    notify();
  },
  updateMessage: (id: string, updates: Partial<ChatMessage>) => {
    state = {
      ...state,
      messages: state.messages.map((m) => (m.id === id ? { ...m, ...updates } : m)),
    };
    notify();
  },
  setStatus: (status: AgentStatusType, detail?: string) => {
    state = {
      ...state,
      status,
      statusDetail: detail || status.replace('_', ' ').toUpperCase(),
    };
    notify();
  },
  setConnected: (connected: boolean) => {
    state = {
      ...state,
      isConnected: connected,
      status: connected ? (state.status === 'offline' ? 'online' : state.status) : 'offline',
      statusDetail: connected ? 'Connected to local agent backend' : 'Backend offline (localhost:8000)',
    };
    notify();
  },
  setConfirmations: (tickets: ConfirmationTicket[]) => {
    state = { ...state, pendingConfirmations: tickets };
    notify();
  },
  addConfirmation: (ticket: ConfirmationTicket) => {
    state = {
      ...state,
      pendingConfirmations: [...state.pendingConfirmations.filter((t) => t.ticket_id !== ticket.ticket_id), ticket],
      status: 'waiting_confirmation',
      statusDetail: `Approval required for ${ticket.tool_name}`,
    };
    notify();
  },
  resolveConfirmation: (ticketId: string) => {
    const updated = state.pendingConfirmations.filter((t) => t.ticket_id !== ticketId);
    state = {
      ...state,
      pendingConfirmations: updated,
      status: updated.length > 0 ? 'waiting_confirmation' : 'online',
      statusDetail: updated.length > 0 ? `Approval required` : 'Ready',
    };
    notify();
  },
  setTasks: (tasks: AgentTask[]) => {
    const active = tasks.find((t) => ['planning', 'executing', 'paused'].includes(t.status)) || null;
    state = { ...state, tasks, activeTask: active };
    notify();
  },
  upsertTask: (task: AgentTask) => {
    const existingIndex = state.tasks.findIndex((t) => t.id === task.id);
    let updatedTasks: AgentTask[];
    if (existingIndex >= 0) {
      updatedTasks = [...state.tasks];
      updatedTasks[existingIndex] = task;
    } else {
      updatedTasks = [task, ...state.tasks];
    }
    const active = updatedTasks.find((t) => ['planning', 'executing', 'paused'].includes(t.status)) || null;
    state = { ...state, tasks: updatedTasks, activeTask: active };
    notify();
  },

  // ── Real-Time Timeline Actions ─────────────────────────────────────────────
  addTimelineItem: (item: TimelineItem) => {
    const maxItems = 200;
    // Check if an item with the same event & tool is already in running state
    const existingIndex = state.timeline.findIndex(
      (t) => t.id === item.id || (t.event === item.event && t.tool === item.tool && t.status === 'running')
    );

    let newTimeline: TimelineItem[];
    if (existingIndex >= 0) {
      newTimeline = [...state.timeline];
      newTimeline[existingIndex] = { ...newTimeline[existingIndex], ...item };
    } else {
      newTimeline = [...state.timeline, item];
    }

    if (newTimeline.length > maxItems) {
      newTimeline = newTimeline.slice(newTimeline.length - maxItems);
    }
    state = { ...state, timeline: newTimeline };
    notify();
  },

  updateTimelineItem: (id: string, partial: Partial<TimelineItem>) => {
    state = {
      ...state,
      timeline: state.timeline.map((item) => (item.id === id ? { ...item, ...partial } : item)),
    };
    notify();
  },

  clearTimeline: () => {
    state = { ...state, timeline: [] };
    notify();
  },

  setActiveExecution: (exec: ActiveExecutionState | null) => {
    state = { ...state, activeExecution: exec };
    notify();
  },

  cancelCurrentTask: async () => {
    // 1. Send WebSocket cancellation
    wsClient.send('cancel_task', { task_id: state.activeExecution?.taskId });
    // 2. Call REST cancellation
    try {
      await api.cancelActiveTask();
    } catch (e) {
      console.warn('REST cancel failed, WS cancel sent', e);
    }

    // 3. Update local state
    if (state.activeExecution) {
      state = {
        ...state,
        activeExecution: {
          ...state.activeExecution,
          status: 'cancelled',
          currentOperation: 'Execution cancelled by user',
        },
      };
      notify();
    }

    // 4. Add cancellation timeline item
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    agentStore.addTimelineItem({
      id: 'cancel_' + Date.now(),
      event: 'task_cancelled',
      timestamp: timeStr,
      rawTimestamp: Date.now(),
      title: 'Task cancelled by user',
      status: 'cancelled',
      error: 'Cancelled',
    });
  },

  reconnect: async (): Promise<boolean> => {
    try {
      state = {
        ...state,
        statusDetail: 'Reconnecting to local backend (localhost:8000)...',
      };
      notify();
      const health = await api.checkHealth();
      if (health && health.status === 'ok') {
        wsClient.connect();
        agentStore.setConnected(true);
        return true;
      }
      agentStore.setConnected(false);
      return false;
    } catch {
      agentStore.setConnected(false);
      return false;
    }
  },
};

export function useAgentStore(): [AgentState, typeof agentStore] {
  const [localState, setLocalState] = useState<AgentState>(agentStore.getState());

  useEffect(() => {
    return agentStore.subscribe((newState) => {
      setLocalState(newState);
    });
  }, []);

  return [localState, agentStore];
}
