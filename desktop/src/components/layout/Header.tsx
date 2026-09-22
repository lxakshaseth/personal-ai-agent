import React from 'react';
import { StatusIndicator } from './StatusIndicator';
import { agentStore, useAgentStore } from '../../stores/agentStore';
import { Bot, Mic, RefreshCw, Minus, X } from 'lucide-react';
import { api } from '../../services/api';

interface HeaderProps {
  activeTab: string;
  onSwitchToRobot?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, onSwitchToRobot }) => {
  const [state] = useAgentStore();

  const getTitle = () => {
    switch (activeTab) {
      case 'dashboard':
        return 'Control Center';
      case 'chat':
        return 'AI Assistant Chat';
      case 'tasks':
        return 'Pipeline & Task Manager';
      case 'voice':
        return 'Voice Interface';
      case 'tools':
        return 'Tool Management';
      case 'memory':
        return 'Short-Term Memory';
      case 'history':
        return 'Command History';
      case 'security':
        return 'Security & Sandboxing';
      case 'system':
        return 'System Telemetry';
      case 'logs':
        return 'Audit & Event Logs';
      case 'settings':
        return 'Configuration';
      default:
        return 'Personal AI Agent';
    }
  };

  const [isReconnecting, setIsReconnecting] = React.useState(false);

  const handleQuickListen = async () => {
    try {
      await api.triggerListen();
    } catch (e) {
      console.error(e);
    }
  };

  const handleReconnect = async () => {
    setIsReconnecting(true);
    try {
      await agentStore.reconnect();
    } finally {
      setIsReconnecting(false);
    }
  };

  const isOffline = !state.isConnected || state.status === 'offline';

  return (
    <header className="h-16 border-b border-slate-800/80 bg-[#07090e]/90 backdrop-blur-md px-6 flex items-center justify-between z-20 flex-shrink-0 drag-region">
      {/* Title & Page info */}
      <div className="flex items-center gap-3 no-drag">
        <h1 className="text-lg font-bold text-white tracking-tight">{getTitle()}</h1>
        <div className="h-4 w-px bg-slate-800" />
        <span className="text-xs font-mono text-cyan-400/90 bg-cyan-950/40 border border-cyan-800/40 px-2 py-0.5 rounded">
          {state.activeModel}
        </span>
      </div>

      {/* Right controls: Robot Mode Toggle + Status + Quick Actions + Window controls */}
      <div className="flex items-center gap-3 no-drag">
        {/* Switch to Desktop Robot Companion */}
        {onSwitchToRobot && (
          <button
            onClick={onSwitchToRobot}
            title="Switch to Desktop Robot Companion on Home Screen (Ctrl+Shift+R)"
            className="px-3 py-1.5 rounded-xl bg-cyan-950/70 hover:bg-cyan-900/90 border border-cyan-500/50 text-cyan-200 hover:text-white transition-all flex items-center gap-1.5 text-xs font-semibold shadow-md shadow-cyan-950/30 group"
          >
            <Bot className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
            <span>Robot Mode</span>
          </button>
        )}

        {/* Quick Voice Trigger */}
        <button
          onClick={handleQuickListen}
          title="Trigger Listen (Ctrl+Space)"
          className="p-2 rounded-xl bg-slate-800/60 hover:bg-cyan-950/50 hover:border-cyan-500/40 border border-slate-700/60 text-slate-300 hover:text-cyan-300 transition-all flex items-center gap-1.5 text-xs font-medium"
        >
          <Mic className="w-3.5 h-3.5" />
          <span>Speak</span>
        </button>

        {/* Offline Reconnect Button */}
        {isOffline && (
          <button
            onClick={handleReconnect}
            disabled={isReconnecting}
            className="px-3 py-1.5 rounded-xl bg-rose-950/80 hover:bg-rose-900/90 border border-rose-700/60 text-rose-200 hover:text-white transition-all flex items-center gap-2 text-xs font-semibold shadow-lg shadow-rose-950/30"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isReconnecting ? 'animate-spin' : ''}`} />
            <span>Reconnect</span>
          </button>
        )}

        {/* Real-Time Visual Status Indicator */}
        <StatusIndicator status={isOffline ? 'offline' : state.status} detail={state.statusDetail} size="md" />

        {/* Window controls (Minimize / Close) for frameless Electron window */}
        <div className="h-4 w-px bg-slate-800 ml-1" />
        <div className="flex items-center gap-1">
          <button
            onClick={() => window.desktopAPI?.minimizeWindow?.()}
            title="Minimize"
            className="p-1.5 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-slate-800/70 transition"
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => window.desktopAPI?.closeWindow?.()}
            title="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800/70 transition"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
};
