import React, { useState } from 'react';
import { ComplexPlan, PlanStep } from '../../types/agent';
import {
  Globe,
  Monitor,
  Folder,
  MessageCircle,
  Cpu,
  Play,
  X,
  Layers,
  Sparkles,
  Loader2,
  CheckCircle2,
} from 'lucide-react';

interface PlanApprovalCardProps {
  plan: ComplexPlan;
  taskId?: string;
  onApprove?: (taskId: string) => Promise<void> | void;
  onCancel?: (taskId: string) => Promise<void> | void;
  isExecuting?: boolean;
}

const getSpecialistIcon = (specialist: string) => {
  const s = specialist.toLowerCase();
  if (s.includes('browser')) return <Globe className="w-4 h-4 text-sky-400" />;
  if (s.includes('computer')) return <Monitor className="w-4 h-4 text-indigo-400" />;
  if (s.includes('file')) return <Folder className="w-4 h-4 text-amber-400" />;
  if (s.includes('communication') || s.includes('whatsapp')) return <MessageCircle className="w-4 h-4 text-emerald-400" />;
  return <Cpu className="w-4 h-4 text-purple-400" />;
};

const getSpecialistBadgeClass = (specialist: string) => {
  const s = specialist.toLowerCase();
  if (s.includes('browser')) return 'bg-sky-500/10 border-sky-500/30 text-sky-300';
  if (s.includes('computer')) return 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300';
  if (s.includes('file')) return 'bg-amber-500/10 border-amber-500/30 text-amber-300';
  if (s.includes('communication') || s.includes('whatsapp')) return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300';
  return 'bg-purple-500/10 border-purple-500/30 text-purple-300';
};

export const PlanApprovalCard: React.FC<PlanApprovalCardProps> = ({
  plan,
  taskId = '',
  onApprove,
  onCancel,
  isExecuting = false,
}) => {
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    if (loading || isExecuting) return;
    setLoading(true);
    try {
      if (onApprove) {
        await onApprove(taskId);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (loading || isExecuting) return;
    if (onCancel) {
      await onCancel(taskId);
    }
  };

  const steps: PlanStep[] = plan.steps || [];
  const count = plan.estimated_operations || steps.length;

  return (
    <div className="w-full bg-[#0d1424]/90 border-2 border-indigo-500/40 rounded-2xl p-5 shadow-xl shadow-indigo-950/50 backdrop-blur-md transition-all duration-200">
      {/* Card Header matching exact ASCII layout */}
      <div className="flex items-center justify-between pb-3 mb-4 border-b border-indigo-500/20">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-indigo-500/20 border border-indigo-500/40 rounded-lg text-indigo-400">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-mono font-bold text-sm tracking-wider text-indigo-200">PLAN</h3>
            <p className="text-xs text-slate-400">{plan.summary || 'Coordinated multi-step task execution'}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-indigo-500/10 border border-indigo-500/30 rounded-full text-indigo-300 text-xs font-mono">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
          <span>Supervisor Coordinated</span>
        </div>
      </div>

      {/* Plan Steps List */}
      <div className="space-y-2.5 mb-5 font-mono">
        {steps.map((step) => {
          const isDone = step.status === 'COMPLETED';
          const isRunning = step.status === 'RUNNING';
          const isFailed = step.status === 'FAILED';

          return (
            <div
              key={step.id || step.index}
              className={`flex items-start gap-3 p-3 rounded-xl border transition-all ${
                isRunning
                  ? 'bg-indigo-950/40 border-indigo-500/60 shadow-lg shadow-indigo-900/30'
                  : isDone
                  ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                  : isFailed
                  ? 'bg-rose-950/20 border-rose-500/30 text-rose-200'
                  : 'bg-slate-900/60 border-slate-800 text-slate-200'
              }`}
            >
              {/* Number or Status Indicator */}
              <div className="flex items-center justify-center w-6 h-6 rounded-lg bg-slate-800/80 border border-slate-700 text-xs font-bold text-slate-300 shrink-0 mt-0.5">
                {isRunning ? (
                  <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
                ) : isDone ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  step.index
                )}
              </div>

              {/* Action and Specialist */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-sm font-medium text-slate-100">{step.action}</span>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] font-sans ${getSpecialistBadgeClass(
                      step.specialist
                    )}`}
                  >
                    {getSpecialistIcon(step.specialist)}
                    {step.specialist}
                  </span>
                </div>
                <div className="text-xs text-slate-400 flex items-center gap-2">
                  <span className="text-slate-500">Tool:</span>
                  <span className="font-mono text-indigo-300">{step.tool_name}</span>
                  {step.status && step.status !== 'PENDING' && (
                    <span
                      className={`text-[10px] px-1.5 py-0.2 rounded font-sans uppercase font-semibold ${
                        isDone
                          ? 'text-emerald-400 bg-emerald-500/10'
                          : isRunning
                          ? 'text-indigo-400 bg-indigo-500/10'
                          : 'text-rose-400 bg-rose-500/10'
                      }`}
                    >
                      {step.status}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Operations count */}
      <div className="text-xs text-slate-400 font-mono mb-5 flex items-center justify-between px-1">
        <span>Estimated operations: <strong className="text-indigo-300 font-bold text-sm">{count}</strong></span>
        {isExecuting && (
          <span className="flex items-center gap-1.5 text-indigo-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Executing operations...
          </span>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleApprove}
          disabled={loading || isExecuting}
          className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 disabled:opacity-50 text-white text-sm font-semibold rounded-xl shadow-lg shadow-emerald-950/40 border border-emerald-400/40 transition-all cursor-pointer font-sans"
        >
          {loading || isExecuting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Executing Plan...</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              <span>Execute</span>
            </>
          )}
        </button>

        <button
          onClick={handleCancel}
          disabled={loading || isExecuting}
          className="flex items-center justify-center gap-2 px-5 py-2.5 bg-slate-800/80 hover:bg-rose-950/40 hover:text-rose-300 hover:border-rose-500/50 text-slate-300 text-sm font-medium rounded-xl border border-slate-700/80 transition-all cursor-pointer font-sans"
        >
          <X className="w-4 h-4" />
          <span>Cancel</span>
        </button>
      </div>
    </div>
  );
};
