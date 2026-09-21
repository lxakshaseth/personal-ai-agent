import React from 'react';
import { AgentStatusType } from '../../types/agent';
import { Mic, Brain, Play, AlertTriangle, AlertCircle, CheckCircle2, WifiOff } from 'lucide-react';

interface StatusIndicatorProps {
  status: AgentStatusType;
  detail?: string;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  detail,
  size = 'md',
  showLabel = true,
}) => {
  const getStatusConfig = (s: AgentStatusType) => {
    switch (s) {
      case 'online':
        return {
          dotColor: 'bg-emerald-400',
          glowColor: 'shadow-[0_0_12px_rgba(52,211,153,0.6)]',
          ringColor: 'border-emerald-500/30',
          textColor: 'text-emerald-300',
          bgColor: 'bg-emerald-950/40 border-emerald-800/40',
          label: 'Agent Online',
          icon: CheckCircle2,
          animate: '',
        };
      case 'listening':
        return {
          dotColor: 'bg-cyan-400',
          glowColor: 'shadow-[0_0_16px_rgba(6,182,212,0.8)]',
          ringColor: 'border-cyan-500/50',
          textColor: 'text-cyan-300',
          bgColor: 'bg-cyan-950/50 border-cyan-800/50',
          label: 'Listening',
          icon: Mic,
          animate: 'animate-pulse',
        };
      case 'thinking':
        return {
          dotColor: 'bg-purple-400',
          glowColor: 'shadow-[0_0_16px_rgba(168,85,247,0.8)]',
          ringColor: 'border-purple-500/50',
          textColor: 'text-purple-300',
          bgColor: 'bg-purple-950/50 border-purple-800/50',
          label: 'Thinking',
          icon: Brain,
          animate: 'animate-pulse',
        };
      case 'executing':
        return {
          dotColor: 'bg-blue-400',
          glowColor: 'shadow-[0_0_16px_rgba(59,130,246,0.8)]',
          ringColor: 'border-blue-500/50',
          textColor: 'text-blue-300',
          bgColor: 'bg-blue-950/50 border-blue-800/50',
          label: 'Executing',
          icon: Play,
          animate: 'animate-spin-slow',
        };
      case 'waiting_confirmation':
        return {
          dotColor: 'bg-amber-400',
          glowColor: 'shadow-[0_0_16px_rgba(245,158,11,0.8)]',
          ringColor: 'border-amber-500/50',
          textColor: 'text-amber-300',
          bgColor: 'bg-amber-950/50 border-amber-800/50',
          label: 'Waiting for Confirmation',
          icon: AlertTriangle,
          animate: 'animate-bounce',
        };
      case 'error':
        return {
          dotColor: 'bg-rose-400',
          glowColor: 'shadow-[0_0_16px_rgba(244,63,94,0.8)]',
          ringColor: 'border-rose-500/50',
          textColor: 'text-rose-300',
          bgColor: 'bg-rose-950/50 border-rose-800/50',
          label: 'Error',
          icon: AlertCircle,
          animate: '',
        };
      case 'offline':
      default:
        return {
          dotColor: 'bg-rose-500',
          glowColor: 'shadow-[0_0_10px_rgba(244,63,94,0.5)]',
          ringColor: 'border-rose-700/40',
          textColor: 'text-rose-400',
          bgColor: 'bg-rose-950/40 border-rose-800/40',
          label: 'Backend Offline',
          icon: WifiOff,
          animate: '',
        };
    }
  };

  const config = getStatusConfig(status);
  const Icon = config.icon;

  if (size === 'sm') {
    return (
      <div className="flex items-center gap-2">
        <span className={`inline-block w-2.5 h-2.5 rounded-full ${config.dotColor} ${config.glowColor}`} />
        {showLabel && <span className={`text-xs font-medium ${config.textColor}`}>{config.label}</span>}
      </div>
    );
  }

  return (
    <div
      className={`inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full border backdrop-blur-md transition-all duration-300 ${config.bgColor}`}
    >
      <div className="relative flex items-center justify-center">
        <span className={`w-2.5 h-2.5 rounded-full ${config.dotColor} ${config.glowColor}`} />
        {status !== 'offline' && (
          <span
            className={`absolute -inset-1 rounded-full border ${config.ringColor} animate-ping opacity-75`}
          />
        )}
      </div>

      <div className="flex flex-col">
        <div className="flex items-center gap-1.5">
          <Icon className={`w-3.5 h-3.5 ${config.textColor} ${config.animate}`} />
          <span className={`text-xs font-semibold uppercase tracking-wider ${config.textColor}`}>
            {config.label}
          </span>
        </div>
        {detail && detail !== config.label && (
          <span className="text-[10px] text-slate-400 max-w-[240px] truncate leading-tight mt-0.5">
            {detail}
          </span>
        )}
      </div>
    </div>
  );
};
