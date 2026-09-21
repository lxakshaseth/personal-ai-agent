import React, { useState, useEffect, useRef } from 'react';
import { useAgentStore } from '../../stores/agentStore';
import { TimelineItem } from '../../types/timeline';
import {
  ChevronDown,
  ChevronRight,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  X,
  Copy,
  Check,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

interface ExecutionTimelineProps {
  maxItems?: number;
  className?: string;
  showLongRunningCard?: boolean;
}

export const ExecutionTimeline: React.FC<ExecutionTimelineProps> = ({
  maxItems = 30,
  className = '',
  showLongRunningCard = true,
}) => {
  const [state, store] = useAgentStore();
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number>(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const active = state.activeExecution;
  const isRunning = active?.status === 'running' || state.status === 'executing' || state.status === 'thinking' || state.status === 'listening';

  // Live timer for elapsed execution time
  useEffect(() => {
    let timer: any = null;
    if (isRunning && active?.startTime) {
      const updateElapsed = () => {
        const secs = (Date.now() - active.startTime) / 1000;
        setElapsed(Math.max(0, secs));
      };
      updateElapsed();
      timer = setInterval(updateElapsed, 100);
    } else if (!isRunning) {
      if (active?.startTime) {
        setElapsed(Math.max(0, (Date.now() - active.startTime) / 1000));
      }
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isRunning, active?.startTime]);

  // Auto-scroll to bottom on new timeline items
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [state.timeline.length]);

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCopy = (id: string, content: any) => {
    const text = typeof content === 'object' ? JSON.stringify(content, null, 2) : String(content ?? '');
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // Sample timeline if no execution has happened yet
  const displayItems: TimelineItem[] =
    state.timeline.length > 0
      ? state.timeline.slice(-maxItems)
      : [
          {
            id: 'demo_1',
            event: 'agent.listening',
            timestamp: '12:31:01',
            rawTimestamp: Date.now() - 5000,
            title: '🎙 Listening',
            status: 'completed',
          },
          {
            id: 'demo_2',
            event: 'agent.transcribing',
            timestamp: '12:31:02',
            rawTimestamp: Date.now() - 4000,
            title: '📝 Transcribing',
            status: 'completed',
          },
          {
            id: 'demo_3',
            event: 'agent.thinking',
            timestamp: '12:31:03',
            rawTimestamp: Date.now() - 3000,
            title: '🧠 Understanding command',
            status: 'completed',
          },
          {
            id: 'demo_4',
            event: 'tool.selected',
            timestamp: '12:31:03',
            rawTimestamp: Date.now() - 2500,
            title: '🔧 Selected: open_url',
            tool: 'open_url',
            details: { url: 'https://www.youtube.com' },
            status: 'completed',
          },
          {
            id: 'demo_5',
            event: 'tool.started',
            timestamp: '12:31:04',
            rawTimestamp: Date.now() - 2000,
            title: '⚙ Executing',
            tool: 'open_url',
            details: { url: 'https://www.youtube.com' },
            status: 'completed',
          },
          {
            id: 'demo_6',
            event: 'tool.completed',
            timestamp: '12:31:05',
            rawTimestamp: Date.now() - 1000,
            title: '✓ Completed',
            tool: 'open_url',
            duration: 0.8,
            details: 'Opened Youtube in default browser: https://www.youtube.com',
            status: 'completed',
          },
          {
            id: 'demo_7',
            event: 'agent.completed',
            timestamp: '12:31:05',
            rawTimestamp: Date.now(),
            title: '🤖 YouTube is open.',
            status: 'completed',
          },
        ];

  const progressPercent = active?.progress ? Math.round(active.progress * 100) : (isRunning ? 60 : 100);

  return (
    <div className={`space-y-4 font-sans select-none ${className}`}>
      {/* ────────────────────────────────────────────────────────────── */}
      {/* 1. LONG-RUNNING TASK & EXECUTION CONTROL CARD                  */}
      {/* ────────────────────────────────────────────────────────────── */}
      {showLongRunningCard && (isRunning || active) && (
        <div className="bg-[#0b1019] border border-cyan-500/40 rounded-2xl p-5 space-y-3.5 shadow-xl relative overflow-hidden animate-in fade-in">
          {/* Animated top gradient glow while running */}
          {isRunning && (
            <div className="absolute -top-12 left-1/4 w-1/2 h-20 bg-cyan-500/15 rounded-full blur-xl animate-pulse pointer-events-none" />
          )}

          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 min-w-0">
              <div
                className={`p-2 rounded-xl flex items-center justify-center ${
                  isRunning
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    : active?.status === 'cancelled'
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                    : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                }`}
              >
                {isRunning ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : active?.status === 'cancelled' ? (
                  <X className="w-4 h-4" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
              </div>

              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300">
                    {active?.status === 'cancelled'
                      ? 'TASK CANCELLED'
                      : isRunning
                      ? 'RUNNING TASK'
                      : 'EXECUTION COMPLETE'}
                  </span>
                  {active?.command && (
                    <span className="text-xs text-slate-400 truncate max-w-xs font-serif italic">
                      "{active.command}"
                    </span>
                  )}
                </div>
                {/* Current operation */}
                <p className="text-xs font-medium text-cyan-300 truncate mt-0.5">
                  Current operation: <span className="text-white">{active?.currentOperation || 'Processing'}</span>
                </p>
              </div>
            </div>

            {/* Right: Elapsed time & Cancel Button */}
            <div className="flex items-center gap-3 flex-shrink-0">
              {/* Elapsed Time */}
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>Elapsed: {elapsed.toFixed(1)}s</span>
              </div>

              {/* Cancel Button */}
              {isRunning && (
                <button
                  onClick={() => store.cancelCurrentTask()}
                  className="px-3.5 py-1.5 bg-rose-600/20 hover:bg-rose-600/40 text-rose-300 border border-rose-500/40 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-rose-950/40 hover:scale-105 active:scale-95"
                  title="Cancel current task (Esc)"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>Cancel</span>
                  <span className="text-[10px] font-mono px-1 py-0.2 rounded bg-black/30 text-rose-200">
                    Esc
                  </span>
                </button>
              )}
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>Progress</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-2 w-full bg-slate-950 rounded-full overflow-hidden border border-slate-800/80">
              <div
                className={`h-full transition-all duration-300 rounded-full ${
                  isRunning
                    ? 'bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 animate-pulse'
                    : active?.status === 'cancelled'
                    ? 'bg-rose-500'
                    : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.max(5, Math.min(100, progressPercent))}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────── */}
      {/* 2. LIVE EXECUTION TIMELINE                                     */}
      {/* ────────────────────────────────────────────────────────────── */}
      <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-5 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-slate-200">
              LIVE EXECUTION TIMELINE
            </h3>
          </div>

          <div className="flex items-center gap-2">
            {state.timeline.length > 0 && (
              <button
                onClick={() => store.clearTimeline()}
                className="text-[11px] text-slate-500 hover:text-slate-300 flex items-center gap-1 font-mono transition-colors"
                title="Clear Timeline"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Clear</span>
              </button>
            )}
            <span className="text-[11px] font-mono text-cyan-400 bg-cyan-950/40 border border-cyan-800/40 px-2 py-0.5 rounded-full">
              {displayItems.length} Events
            </span>
          </div>
        </div>

        {/* Chronological List matching:
            12:31:01
            🎙 Listening
            
            12:31:02
            📝 Transcribing
            ...
        */}
        <div
          ref={scrollRef}
          className="space-y-2.5 max-h-96 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-slate-800"
        >
          {displayItems.map((item, index) => {
            const isExpanded = expandedIds.has(item.id);
            const hasDetails = item.details !== undefined || item.error;

            return (
              <div
                key={item.id || index}
                className={`rounded-xl border transition-all ${
                  item.status === 'error'
                    ? 'bg-rose-950/20 border-rose-800/40 hover:border-rose-700/60'
                    : item.status === 'running'
                    ? 'bg-cyan-950/20 border-cyan-500/40 hover:border-cyan-400/60'
                    : item.status === 'cancelled'
                    ? 'bg-amber-950/20 border-amber-800/40 hover:border-amber-700/60'
                    : 'bg-[#080c14] border-slate-800/80 hover:border-slate-700/80'
                }`}
              >
                {/* Event Row */}
                <div
                  onClick={() => hasDetails && toggleExpand(item.id)}
                  className={`p-3 flex items-start justify-between gap-3 ${
                    hasDetails ? 'cursor-pointer' : ''
                  }`}
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    {/* Timestamp */}
                    <div className="text-[11px] font-mono text-slate-500 tracking-wider">
                      {item.timestamp}
                    </div>

                    {/* Title */}
                    <div className="flex items-center gap-2 text-xs font-semibold text-slate-100 break-words">
                      <span>{item.title}</span>

                      {/* Duration badge if present */}
                      {item.duration !== undefined && item.duration !== null && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-900 border border-slate-700/80 text-cyan-300 font-normal">
                          {item.duration}s
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Status Indicator & Expand Icon */}
                  <div className="flex items-center gap-2 flex-shrink-0 pt-1">
                    {item.status === 'running' && (
                      <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                    )}
                    {item.status === 'completed' && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    {item.status === 'error' && (
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                    )}
                    {item.status === 'cancelled' && (
                      <X className="w-3.5 h-3.5 text-amber-400" />
                    )}

                    {hasDetails && (
                      <button
                        type="button"
                        className="text-slate-400 hover:text-white transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4" />
                        ) : (
                          <ChevronRight className="w-4 h-4" />
                        )}
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded Details Panel */}
                {isExpanded && hasDetails && (
                  <div className="px-3.5 pb-3.5 pt-1 border-t border-slate-800/80 space-y-2 text-xs animate-in fade-in">
                    <div className="flex items-center justify-between text-slate-400 pt-1 text-[11px]">
                      <span>Event Details (Sanitized)</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCopy(item.id, item.details || item.error);
                        }}
                        className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 font-mono"
                      >
                        {copiedId === item.id ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3" />
                        )}
                        <span>{copiedId === item.id ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>

                    {/* Error display */}
                    {item.error && (
                      <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 font-mono text-[11px] flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 flex-shrink-0 text-rose-400 mt-0.5" />
                        <span className="break-all">{item.error}</span>
                      </div>
                    )}

                    {/* Payload / Details */}
                    {item.details && (
                      <pre className="p-2.5 rounded-lg bg-[#04060a] border border-slate-800/80 font-mono text-[11px] text-cyan-200 overflow-x-auto max-h-48 whitespace-pre-wrap select-text">
                        {typeof item.details === 'object'
                          ? JSON.stringify(item.details, null, 2)
                          : String(item.details)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
