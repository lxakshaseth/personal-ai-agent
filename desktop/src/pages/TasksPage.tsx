import React, { useState, useEffect } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import { AgentTask } from '../types/agent';
import { PlanApprovalCard } from '../components/plan/PlanApprovalCard';
import {
  ListTodo,
  Play,
  Pause,
  XCircle,
  CheckCircle2,
  Brain,
  Globe,
  Monitor,
  Folder,
  MessageCircle,
  Cpu,
  Clock,
  Sparkles,
  Layers,
  Filter,
  Check,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

const FILTER_STATES = [
  'ALL',
  'WAITING_APPROVAL',
  'RUNNING',
  'PLANNING',
  'PAUSED',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
] as const;

export const TasksPage: React.FC = () => {
  const [state, store] = useAgentStore();
  const [selectedFilter, setSelectedFilter] = useState<string>('ALL');
  const [expandedTaskIds, setExpandedTaskIds] = useState<Record<string, boolean>>({});

  const refreshTasks = async () => {
    try {
      const data = await api.getTasks(selectedFilter === 'ALL' ? undefined : selectedFilter);
      store.setTasks(data);
    } catch (err) {
      console.error('Failed to load tasks', err);
    }
  };

  useEffect(() => {
    refreshTasks();
  }, [selectedFilter]);

  const handlePause = async (taskId: string) => {
    try {
      await api.pauseTask(taskId);
      refreshTasks();
    } catch (e) {
      console.error(e);
    }
  };

  const handleResume = async (taskId: string) => {
    try {
      await api.resumeTask(taskId);
      refreshTasks();
    } catch (e) {
      console.error(e);
    }
  };

  const handleCancel = async (taskId: string) => {
    try {
      await api.cancelTask(taskId);
      refreshTasks();
    } catch (e) {
      console.error(e);
    }
  };

  const handleApprove = async (taskId: string) => {
    try {
      await api.approveTask(taskId);
      refreshTasks();
    } catch (e) {
      console.error(e);
    }
  };

  const toggleExpand = (taskId: string) => {
    setExpandedTaskIds((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const filteredTasks = state.tasks.filter((t) => {
    if (selectedFilter === 'ALL') return true;
    return t.status.toUpperCase() === selectedFilter.toUpperCase();
  });

  const getSpecialistIcon = (specialist: string) => {
    const s = specialist.toLowerCase();
    if (s.includes('browser')) return <Globe className="w-3.5 h-3.5 text-sky-400" />;
    if (s.includes('computer')) return <Monitor className="w-3.5 h-3.5 text-indigo-400" />;
    if (s.includes('file')) return <Folder className="w-3.5 h-3.5 text-amber-400" />;
    if (s.includes('communication') || s.includes('whatsapp')) return <MessageCircle className="w-3.5 h-3.5 text-emerald-400" />;
    return <Cpu className="w-3.5 h-3.5 text-purple-400" />;
  };

  const getStatusBadge = (status: string) => {
    const s = status.toUpperCase();
    if (s === 'WAITING_APPROVAL') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold font-mono animate-pulse">
          WAITING APPROVAL
        </span>
      );
    }
    if (s === 'RUNNING' || s === 'EXECUTING') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 text-[10px] font-bold font-mono">
          RUNNING
        </span>
      );
    }
    if (s === 'COMPLETED') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold font-mono">
          COMPLETED
        </span>
      );
    }
    if (s === 'FAILED') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold font-mono">
          FAILED
        </span>
      );
    }
    if (s === 'PAUSED') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-slate-500/20 text-slate-300 border border-slate-500/40 text-[10px] font-bold font-mono">
          PAUSED
        </span>
      );
    }
    if (s === 'CANCELLED') {
      return (
        <span className="px-2.5 py-0.5 rounded-full bg-zinc-700 text-zinc-300 text-[10px] font-bold font-mono">
          CANCELLED
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 text-[10px] font-bold font-mono">
        {s}
      </span>
    );
  };

  return (
    <div className="p-8 space-y-6 max-w-6xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <ListTodo className="w-5 h-5 text-indigo-400" />
            <span>Agent Tasks & Multi-Step Workflows</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Supervisor-orchestrated task execution across specialized domain workers with persistent history.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="px-3 py-1 rounded-full bg-indigo-950/60 border border-indigo-800/60 text-indigo-300">
            {state.tasks.length} Total Tasks
          </span>
        </div>
      </div>

      {/* State Filter Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 border-b border-slate-800/80 font-mono text-xs">
        <Filter className="w-3.5 h-3.5 text-slate-500 mr-1" />
        {FILTER_STATES.map((st) => (
          <button
            key={st}
            onClick={() => setSelectedFilter(st)}
            className={`px-3 py-1 rounded-lg transition-all cursor-pointer whitespace-nowrap ${
              selectedFilter === st
                ? 'bg-indigo-600 text-white font-bold shadow-sm shadow-indigo-900/50'
                : 'bg-slate-900/80 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800'
            }`}
          >
            {st.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Tasks List */}
      <div className="space-y-4">
        {filteredTasks.length === 0 ? (
          <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500 text-xs font-mono">
            No tasks found with state "{selectedFilter}".
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isWaitingApproval = task.status.toUpperCase() === 'WAITING_APPROVAL';
            const isRunning = task.status.toUpperCase() === 'RUNNING' || task.status === 'executing';
            const isPaused = task.status.toUpperCase() === 'PAUSED';
            const isExpanded = !!expandedTaskIds[task.id];

            return (
              <div
                key={task.id}
                className={`bg-[#0b1019] border rounded-2xl p-6 transition-all ${
                  isWaitingApproval
                    ? 'border-amber-500/50 shadow-xl shadow-amber-950/30'
                    : isRunning
                    ? 'border-indigo-500/50 shadow-xl shadow-indigo-950/30'
                    : 'border-slate-800/80 shadow-md'
                }`}
              >
                {/* Header info */}
                <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[10px] font-mono text-slate-500">#{task.id.slice(0, 8)}</span>
                      {getStatusBadge(task.status)}
                      {task.is_complex && (
                        <span className="px-2 py-0.5 rounded-full bg-purple-500/10 border border-purple-500/30 text-purple-300 text-[10px] font-mono flex items-center gap-1">
                          <Layers className="w-3 h-3" />
                          Multi-Step Plan
                        </span>
                      )}
                    </div>
                    <h4 className="text-base font-semibold text-white pt-1">{task.description}</h4>
                    {task.result && (
                      <p className="text-xs text-slate-400 font-mono mt-1 line-clamp-2">{task.result}</p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {isWaitingApproval && (
                      <button
                        onClick={() => handleApprove(task.id)}
                        className="px-4 py-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-emerald-950/40 cursor-pointer"
                      >
                        <Play className="w-3.5 h-3.5 fill-current" />
                        <span>Approve & Execute</span>
                      </button>
                    )}

                    {isRunning && (
                      <button
                        onClick={() => handlePause(task.id)}
                        className="px-3.5 py-1.5 bg-amber-600/80 hover:bg-amber-600 text-white rounded-xl text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                      >
                        <Pause className="w-3.5 h-3.5" />
                        <span>Pause</span>
                      </button>
                    )}

                    {isPaused && (
                      <button
                        onClick={() => handleResume(task.id)}
                        className="px-3.5 py-1.5 bg-emerald-600/80 hover:bg-emerald-600 text-white rounded-xl text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>Resume</span>
                      </button>
                    )}

                    {(isWaitingApproval || isRunning || isPaused) && (
                      <button
                        onClick={() => handleCancel(task.id)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-rose-950/50 hover:text-rose-300 text-slate-400 border border-slate-700 rounded-xl text-xs font-medium flex items-center gap-1 cursor-pointer"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        <span>Cancel</span>
                      </button>
                    )}

                    {task.plan && (
                      <button
                        onClick={() => toggleExpand(task.id)}
                        className="p-1.5 text-slate-400 hover:text-white rounded-lg bg-slate-800/60 border border-slate-700 cursor-pointer"
                        title={isExpanded ? 'Collapse Plan' : 'Inspect Plan'}
                      >
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    )}
                  </div>
                </div>

                {/* Plan Approval Inline Card when Waiting */}
                {isWaitingApproval && task.plan && (
                  <div className="mt-4 pt-4 border-t border-amber-500/20">
                    <PlanApprovalCard
                      plan={task.plan}
                      taskId={task.id}
                      onApprove={handleApprove}
                      onCancel={handleCancel}
                    />
                  </div>
                )}

                {/* Detailed Plan Steps for Running/Completed Tasks */}
                {task.plan && (!isWaitingApproval || isExpanded) && (
                  <div className="mt-4 pt-4 border-t border-slate-800/80 space-y-2 font-mono">
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                      <span className="font-semibold text-slate-300">Plan Steps:</span>
                      <span>{task.plan.steps.length} operations</span>
                    </div>

                    <div className="space-y-2">
                      {task.plan.steps.map((step) => (
                        <div
                          key={step.id || step.index}
                          className="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-slate-900/60 border border-slate-800/80 text-xs"
                        >
                          <div className="flex items-start gap-2.5">
                            <span className="w-5 h-5 flex items-center justify-center rounded bg-slate-800 text-[11px] text-slate-400 font-bold shrink-0">
                              {step.index}
                            </span>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-slate-200 font-medium">{step.action}</span>
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px]">
                                  {getSpecialistIcon(step.specialist)}
                                  {step.specialist}
                                </span>
                              </div>
                              <div className="text-[11px] text-slate-500 mt-0.5">
                                Tool: <span className="text-indigo-300">{step.tool_name}</span>
                              </div>
                              {step.output && (
                                <div className="text-[10px] text-slate-400 mt-1 p-1.5 bg-black/30 rounded border border-slate-800">
                                  {step.output}
                                </div>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-2 shrink-0 text-[11px]">
                            {step.duration_seconds && (
                              <span className="text-slate-500">{step.duration_seconds}s</span>
                            )}
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                step.status === 'COMPLETED'
                                  ? 'text-emerald-300 bg-emerald-950/40 border border-emerald-800/40'
                                  : step.status === 'RUNNING'
                                  ? 'text-indigo-300 bg-indigo-950/40 border border-indigo-800/40 animate-pulse'
                                  : step.status === 'FAILED'
                                  ? 'text-rose-300 bg-rose-950/40 border border-rose-800/40'
                                  : 'text-slate-500 bg-slate-800'
                              }`}
                            >
                              {step.status}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Footer Metrics */}
                <div className="mt-4 pt-3 border-t border-slate-800/50 flex items-center justify-between text-[11px] font-mono text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Duration: {task.duration_seconds}s</span>
                  </span>
                  <span>{new Date(task.created_at * 1000).toLocaleString()}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
