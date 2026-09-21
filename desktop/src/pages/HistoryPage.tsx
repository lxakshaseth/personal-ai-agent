import React, { useState } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import {
  History,
  Search,
  Trash2,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
} from 'lucide-react';

export const HistoryPage: React.FC = () => {
  const [agentState, store] = useAgentStore();
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredHistory = agentState.history.filter(
    (item) =>
      item.command.toLowerCase().includes(search.toLowerCase()) ||
      item.tool_calls?.some((tc) => tc.tool.toLowerCase().includes(search.toLowerCase()))
  );

  const handleClearHistory = async () => {
    if (!window.confirm('Clear all command history records?')) return;
    try {
      await api.clearHistory();
      store.setState({ history: [] });
    } catch (e) {
      console.error(e);
    }
  };

  const copyCommand = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="p-8 space-y-6 max-w-6xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <History className="w-5 h-5 text-cyan-400" />
            <span>Command History Trail</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Complete audit trail of all natural-language prompts, tool invocations, and responses.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search history..."
              className="w-full bg-[#0a0e17] border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <button
            onClick={handleClearHistory}
            disabled={agentState.history.length === 0}
            className="px-3.5 py-2 bg-slate-800 hover:bg-rose-950/40 hover:text-rose-300 text-slate-300 border border-slate-700 rounded-xl text-xs font-medium transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* History Items */}
      {filteredHistory.length === 0 ? (
        <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500 text-xs">
          No command history records found.
        </div>
      ) : (
        <div className="space-y-3">
          {filteredHistory.map((item) => {
            const isExpanded = expandedId === item.id;
            const dateStr = new Date(item.timestamp * 1000).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            });

            return (
              <div
                key={item.id}
                className="bg-[#0b1019] border border-slate-800/80 rounded-xl overflow-hidden transition-all"
              >
                <div
                  onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  className="p-4 flex items-center justify-between gap-4 cursor-pointer hover:bg-slate-900/40"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <span
                      className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                        item.success ? 'bg-emerald-400' : 'bg-rose-400'
                      }`}
                    />
                    <span className="font-semibold text-xs text-white truncate">
                      "{item.command}"
                    </span>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0 text-xs">
                    {item.tool_calls?.length > 0 && (
                      <span className="px-2 py-0.5 rounded bg-cyan-950/50 text-cyan-300 border border-cyan-800/50 font-mono text-[11px]">
                        {item.tool_calls.map((t) => t.tool).join(', ')}
                      </span>
                    )}

                    <span className="text-slate-400 font-mono text-[11px] flex items-center gap-1">
                      <Clock className="w-3 h-3 text-slate-500" />
                      {item.duration_ms}ms
                    </span>

                    <span className="text-slate-500 font-mono text-[11px]">{dateStr}</span>

                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div className="p-4 bg-[#080b11] border-t border-slate-800/80 space-y-3 text-xs">
                    <div>
                      <span className="text-slate-400 font-medium block mb-1">Synthesized Response:</span>
                      <div className="bg-slate-900/90 p-3 rounded-lg border border-slate-800 text-slate-200">
                        {item.response}
                      </div>
                    </div>

                    {item.tool_calls && item.tool_calls.length > 0 && (
                      <div>
                        <span className="text-slate-400 font-medium block mb-1">Tool Executions:</span>
                        <div className="space-y-2">
                          {item.tool_calls.map((tc, idx) => (
                            <div key={idx} className="bg-slate-900/60 p-3 rounded-lg border border-slate-800/60 font-mono">
                              <div className="flex items-center justify-between text-cyan-300 mb-1">
                                <span>{tc.tool}()</span>
                                <span className={tc.success ? 'text-emerald-400' : 'text-rose-400'}>
                                  {tc.success ? 'SUCCESS' : 'FAILED'}
                                </span>
                              </div>
                              <div className="text-[11px] text-slate-400">Args: {JSON.stringify(tc.args)}</div>
                              {tc.output && (
                                <div className="mt-1 text-slate-300 text-[11px] whitespace-pre-wrap">
                                  {tc.output}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="flex justify-end pt-2">
                      <button
                        onClick={() => copyCommand(item.id, item.command)}
                        className="text-[11px] text-slate-400 hover:text-cyan-300 flex items-center gap-1"
                      >
                        {copiedId === item.id ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Copy Command</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
