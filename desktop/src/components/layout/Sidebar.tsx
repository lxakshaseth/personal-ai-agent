import React from 'react';
import {
  LayoutDashboard,
  MessageSquare,
  ListTodo,
  Wrench,
  Database,
  History,
  ShieldCheck,
  Settings,
  Bot,
  Sparkles,
} from 'lucide-react';
import { useAgentStore } from '../../stores/agentStore';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const [state] = useAgentStore();

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    {
      id: 'chat',
      label: 'Chat',
      icon: MessageSquare,
      badge: state.messages.length > 1 ? state.messages.length - 1 : null,
    },
    {
      id: 'tasks',
      label: 'Tasks',
      icon: ListTodo,
      badge: state.activeTask ? '1 active' : null,
      badgeColor: state.activeTask ? 'bg-cyan-500/20 text-cyan-300' : undefined,
    },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'memory', label: 'Memory', icon: Database },
    {
      id: 'history',
      label: 'History',
      icon: History,
      badge: state.history.length > 0 ? state.history.length : null,
    },
    { id: 'security', label: 'Security', icon: ShieldCheck },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-64 border-r border-slate-800/80 bg-[#0a0e17] flex flex-col justify-between flex-shrink-0 select-none">
      {/* Brand Header */}
      <div>
        <div className="h-16 flex items-center gap-3 px-5 border-b border-slate-800/80">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 via-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 text-white">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
              <span>NOVA AI</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30">
                PRO
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Windows Control Center</p>
          </div>
        </div>

        {/* Navigation items */}
        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-cyan-600/20 to-blue-600/10 text-cyan-300 border border-cyan-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-cyan-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== null && item.badge !== undefined && (
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                      item.badgeColor
                        ? item.badgeColor
                        : isActive
                        ? 'bg-cyan-500/30 text-cyan-200'
                        : 'bg-slate-800 text-slate-400'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-4 border-t border-slate-800/80">
        <div className="bg-slate-900/60 border border-slate-800/60 rounded-xl p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`w-2 h-2 rounded-full ${
                state.isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-rose-400'
              }`}
            />
            <span className="text-[11px] font-medium text-slate-300">
              {state.isConnected ? 'Agent Core Active' : 'Connecting...'}
            </span>
          </div>
          <span className="text-[10px] font-mono text-slate-500">127.0.0.1:8000</span>
        </div>
      </div>
    </aside>
  );
};
