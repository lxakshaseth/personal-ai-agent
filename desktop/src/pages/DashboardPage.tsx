import React, { useState, useEffect, useCallback } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import {
  Mic,
  Send,
  Brain,
  Globe,
  Check,
  CheckCircle2,
  XCircle,
  Pause,
  Play,
  X,
  Sparkles,
} from 'lucide-react';
import { ExecutionTimeline } from '../components/timeline/ExecutionTimeline';
import { PlanApprovalCard } from '../components/plan/PlanApprovalCard';

interface DashboardPageProps {
  setActiveTab: (tab: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ setActiveTab }) => {
  const [state, store] = useAgentStore();
  const [inputCommand, setInputCommand] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [isListening, setIsListening] = useState(false);

  const handleStartListening = useCallback(async () => {
    if (isListening) return; // Prevent double-trigger
    setIsListening(true);

    // Immediately show listening indicator before API call
    store.addMessage({
      id: 'listening_' + Date.now(),
      sender: 'agent',
      text: '🎙 Listening... Speak your command now.',
      timestamp: Date.now(),
    });
    store.setStatus('listening', 'Listening for speech...');

    try {
      const res = await api.triggerListen();
      if (res.success && res.transcript) {
        // Show user's spoken command + agent response as chat messages
        store.addMessage({
          id: 'voice_user_' + Date.now(),
          sender: 'user',
          source: 'voice',
          text: res.transcript,
          timestamp: Date.now(),
        });
        store.addMessage({
          id: 'voice_agent_' + Date.now(),
          sender: 'agent',
          text: res.response ?? 'Done.',
          timestamp: Date.now(),
          tool_calls: res.tool_calls,
        });
        store.setStatus('online', 'Ready');
      } else if (res.error) {
        store.addMessage({
          id: 'notice_' + Date.now(),
          sender: 'agent',
          text: `🎤 ${res.error}`,
          timestamp: Date.now(),
        });
        store.setStatus('online', 'Ready');
      }
    } catch (err: any) {
      store.setStatus('online', 'Ready');
      store.addMessage({
        id: 'notice_' + Date.now(),
        sender: 'agent',
        text: `🎤 Microphone notice: ${err.message || 'Device not available. Use text box below.'}`,
        timestamp: Date.now(),
      });
    } finally {
      setIsListening(false);
    }
  }, [isListening, store]);

  // Ctrl+Space shortcut → Start Listening
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === 'Space' && !isListening) {
        e.preventDefault();
        handleStartListening();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleStartListening, isListening]);


  const handleRunCommand = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cmd = inputCommand.trim();
    if (!cmd || isExecuting) return;

    setIsExecuting(true);
    setInputCommand('');

    store.addMessage({
      id: 'u_' + Date.now(),
      sender: 'user',
      source: 'text',
      text: cmd,
      timestamp: Date.now(),
    });

    try {
      const res = await api.runCommand(cmd);
      store.addMessage({
        id: 'a_' + Date.now(),
        sender: 'agent',
        text: res.response,
        timestamp: Date.now(),
        tool_calls: res.tool_calls,
        error: res.error,
      });
    } catch (err: any) {
      store.addMessage({
        id: 'err_' + Date.now(),
        sender: 'agent',
        text: `Error: ${err.message}`,
        timestamp: Date.now(),
        error: err.message,
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const activeTask = state.activeTask || (state.tasks.length > 0 ? state.tasks[0] : null);

  const formatActivityTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  // Human friendly action text
  const formatActionText = (item: any) => {
    if (item.tool_calls && item.tool_calls.length > 0) {
      const tc = item.tool_calls[0];
      if (tc.tool === 'open_application') return `Opened ${tc.args.app_name || 'Application'}`;
      if (tc.tool === 'open_url') return `Opened ${tc.args.url || 'URL'}`;
      if (tc.tool === 'create_folder') return `Created folder ${tc.args.folder_path || ''}`;
      if (tc.tool === 'send_whatsapp_message') return `Sent WhatsApp message`;
      return `Executed ${tc.tool}`;
    }
    return item.command;
  };

  return (
    <div className="p-8 max-w-4xl mx-auto overflow-y-auto h-[calc(100vh-4rem)] space-y-6 select-none font-sans">
      {/* ────────────────────────────────────────────────────────────── */}
      {/* TOP HEADER: NOVA AI                      ● ONLINE             */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5">
          <Sparkles className="w-5 h-5 text-cyan-400" />
          <span className="text-xl font-bold tracking-wider text-white uppercase font-mono">
            NOVA AI
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`w-2.5 h-2.5 rounded-full ${
              state.status === 'offline'
                ? 'bg-zinc-500'
                : state.status === 'listening'
                ? 'bg-cyan-400 animate-pulse shadow-[0_0_12px_rgba(6,182,212,0.8)]'
                : state.status === 'thinking'
                ? 'bg-purple-400 animate-pulse shadow-[0_0_12px_rgba(168,85,247,0.8)]'
                : state.status === 'executing'
                ? 'bg-blue-400 animate-pulse shadow-[0_0_12px_rgba(59,130,246,0.8)]'
                : state.status === 'waiting_confirmation'
                ? 'bg-amber-400 animate-bounce shadow-[0_0_12px_rgba(245,158,11,0.8)]'
                : state.status === 'error'
                ? 'bg-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.8)]'
                : 'bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)]'
            }`}
          />
          <span className="text-xs font-mono font-bold uppercase tracking-widest text-slate-200">
            {state.status === 'waiting_confirmation' ? 'WAITING APPROVAL' : state.status.toUpperCase()}
          </span>
        </div>
      </div>

      {/* ────────────────────────────────────────────────────────────── */}
      {/* CENTER: AI AGENT CORE / ◉ READY / "How can I help you?"         */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="bg-gradient-to-b from-[#0c121e] to-[#070a12] border border-slate-800/80 rounded-2xl p-8 flex flex-col items-center justify-center text-center shadow-2xl relative overflow-hidden">
        <div className="absolute -top-24 w-96 h-48 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400 font-semibold mb-3">
          AI AGENT CORE
        </span>

        {/* ◉ READY Badge */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-slate-900/90 border border-cyan-500/30 text-cyan-300 text-xs font-mono font-semibold mb-4 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span>◉ {state.status === 'online' ? 'READY' : state.status.toUpperCase()}</span>
        </div>

        {/* Quote */}
        <h2 className="text-xl md:text-2xl font-medium text-white italic tracking-tight mb-6 font-serif">
          "How can I help you?"
        </h2>

        {/* [ 🎙 Start Listening ] Button */}
        <button
          onClick={handleStartListening}
          disabled={isListening}
          className={`group relative inline-flex items-center gap-3 px-8 py-3.5 rounded-2xl font-semibold text-sm shadow-xl transition-all border ${
            isListening
              ? 'bg-cyan-500/90 border-cyan-400/60 text-white shadow-cyan-500/40 animate-pulse cursor-not-allowed'
              : 'bg-gradient-to-r from-cyan-600 via-blue-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white shadow-cyan-950/60 hover:scale-105 active:scale-95 border-cyan-400/30'
          }`}
        >
          <Mic className={`w-5 h-5 text-cyan-200 ${!isListening && 'group-hover:scale-110'} transition-transform`} />
          <span>{isListening ? '🎙 Listening...' : 'Start Listening'}</span>
          {!isListening && (
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/30 text-cyan-200 border border-white/10">
              Ctrl + Space
            </span>
          )}
        </button>

        {/* Quick Text Input Bar */}
        <form onSubmit={handleRunCommand} className="w-full max-w-xl mt-6 flex items-center gap-2">
          <input
            type="text"
            value={inputCommand}
            onChange={(e) => setInputCommand(e.target.value)}
            placeholder="or type a command (e.g. 'Search YouTube for React tutorials')..."
            className="flex-1 bg-[#080c14] border border-slate-700/70 focus:border-cyan-500 rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 font-sans"
          />
          <button
            type="submit"
            disabled={isExecuting || !inputCommand.trim()}
            className="p-2.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 rounded-xl transition-colors"
            title="Execute (Ctrl + Enter)"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* ────────────────────────────────────────────────────────────── */}
      {/* PLAN APPROVAL CARD (When task requires confirmation)           */}
      {/* ────────────────────────────────────────────────────────────── */}
      {activeTask && activeTask.plan && (
        <PlanApprovalCard
          plan={activeTask.plan}
          taskId={activeTask.id}
          isExecuting={activeTask.status === 'RUNNING' || activeTask.status === 'executing'}
          onApprove={async (taskId) => {
            try {
              await api.approveTask(taskId);
              const updated = await api.getTask(taskId);
              if (updated) store.upsertTask(updated);
            } catch (err) {
              console.error('Failed to approve plan:', err);
            }
          }}
          onCancel={async (taskId) => {
            try {
              await api.cancelTask(taskId);
              const updated = await api.getTask(taskId);
              if (updated) store.upsertTask(updated);
            } catch (err) {
              console.error('Failed to cancel task:', err);
            }
          }}
        />
      )}

      {/* ────────────────────────────────────────────────────────────── */}
      {/* CURRENT TASK: Pipeline Steps (Planning / Tool / Completed)     */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-6 space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
            CURRENT TASK
          </span>
          {activeTask && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => api.cancelTask(activeTask.id)}
                className="text-[11px] text-slate-400 hover:text-rose-300 flex items-center gap-1 font-mono"
              >
                <X className="w-3 h-3" />
                <span>Cancel (Esc)</span>
              </button>
            </div>
          )}
        </div>

        <div className="text-sm font-semibold text-white">
          {activeTask ? activeTask.description : 'No task currently running'}
        </div>

        {/* 3 Pipeline Steps */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
          {/* 1. Planning */}
          <div
            className={`p-3.5 rounded-xl border flex items-center gap-3 transition-all ${
              activeTask?.steps?.[0]?.status === 'active'
                ? 'bg-cyan-950/40 border-cyan-500/60 text-cyan-200'
                : activeTask?.steps?.[0]?.status === 'completed'
                ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                : 'bg-slate-900/40 border-slate-800/60 text-slate-500'
            }`}
          >
            <Brain className="w-5 h-5 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-semibold">🧠 Planning</div>
              <div className="text-[10px] uppercase font-mono tracking-wider opacity-75">
                {activeTask?.steps?.[0]?.status || 'Idle'}
              </div>
            </div>
          </div>

          {/* 2. Tool / Browser */}
          <div
            className={`p-3.5 rounded-xl border flex items-center gap-3 transition-all ${
              activeTask?.steps?.[1]?.status === 'active'
                ? 'bg-cyan-950/40 border-cyan-500/60 text-cyan-200'
                : activeTask?.steps?.[1]?.status === 'completed'
                ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                : 'bg-slate-900/40 border-slate-800/60 text-slate-500'
            }`}
          >
            <Globe className="w-5 h-5 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-semibold">
                ⚙ {activeTask?.steps?.[1]?.name || 'Browser'}
              </div>
              <div className="text-[10px] uppercase font-mono tracking-wider opacity-75">
                {activeTask?.steps?.[1]?.status || 'Pending'}
              </div>
            </div>
          </div>

          {/* 3. Completed */}
          <div
            className={`p-3.5 rounded-xl border flex items-center gap-3 transition-all ${
              activeTask?.steps?.[2]?.status === 'completed' || activeTask?.status === 'completed'
                ? 'bg-emerald-950/20 border-emerald-800/40 text-emerald-300'
                : 'bg-slate-900/40 border-slate-800/60 text-slate-500'
            }`}
          >
            <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
            <div className="min-w-0">
              <div className="text-xs font-semibold">✓ Completed</div>
              <div className="text-[10px] uppercase font-mono tracking-wider opacity-75">
                {activeTask?.steps?.[2]?.status || 'Pending'}
              </div>
            </div>
          </div>
        </div>

        {/* Real-Time Agent Execution Visualization & Live Timeline */}
        <ExecutionTimeline className="mt-4" />
      </div>

      {/* ────────────────────────────────────────────────────────────── */}
      {/* RECENT ACTIVITY: List of recent completed actions with time     */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-6 space-y-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
            RECENT ACTIVITY
          </span>
          <button
            onClick={() => setActiveTab('history')}
            className="text-xs text-cyan-400 hover:text-cyan-300 font-medium"
          >
            Full History
          </button>
        </div>

        {state.history.length === 0 ? (
          <div className="space-y-2 text-xs font-mono text-slate-400">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40">
              <span className="text-slate-300">✓ Opened YouTube</span>
              <span className="text-slate-500">12:31</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40">
              <span className="text-slate-300">✓ Created folder</span>
              <span className="text-slate-500">12:29</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/40">
              <span className="text-slate-300">✓ Opened VS Code</span>
              <span className="text-slate-500">12:27</span>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {state.history.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/50 border border-slate-800/60 text-xs font-mono"
              >
                <div className="flex items-center gap-2 truncate pr-4">
                  <span className={item.success ? 'text-emerald-400' : 'text-rose-400'}>
                    {item.success ? '✓' : '✗'}
                  </span>
                  <span className="text-slate-200 truncate">{formatActionText(item)}</span>
                </div>
                <span className="text-slate-500 flex-shrink-0">
                  {formatActivityTime(item.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
