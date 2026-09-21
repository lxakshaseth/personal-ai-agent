import React, { useState, useEffect } from 'react';
import { AuditLogEntry } from '../types/agent';
import { api } from '../services/api';
import { FileText, Search, RefreshCw, CheckCircle2, XCircle, AlertTriangle, ShieldX, ChevronDown, ChevronUp } from 'lucide-react';

export const LogsPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [search, setSearch] = useState('');
  const [filterResult, setFilterResult] = useState<string>('all');
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadLogs = async () => {
    setIsLoading(true);
    try {
      const data = await api.getAuditLogs(100);
      setLogs(data);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const filteredLogs = logs.filter((entry) => {
    const matchesSearch =
      entry.tool.toLowerCase().includes(search.toLowerCase()) ||
      entry.user_command.toLowerCase().includes(search.toLowerCase()) ||
      (entry.output && entry.output.toLowerCase().includes(search.toLowerCase()));

    const matchesResult = filterResult === 'all' || entry.result === filterResult;
    return matchesSearch && matchesResult;
  });

  const getResultBadge = (result: string) => {
    switch (result) {
      case 'success':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950/50 text-emerald-400 border border-emerald-800/50 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> SUCCESS
          </span>
        );
      case 'confirmation_required':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/50 text-amber-400 border border-amber-800/50 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> CONFIRM_REQ
          </span>
        );
      case 'denied':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950/50 text-purple-400 border border-purple-800/50 flex items-center gap-1">
            <ShieldX className="w-3 h-3" /> DENIED
          </span>
        );
      case 'failure':
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/50 text-rose-400 border border-rose-800/50 flex items-center gap-1">
            <XCircle className="w-3 h-3" /> FAILURE
          </span>
        );
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <FileText className="w-5 h-5 text-cyan-400" />
            <span>Audit & Event Logs</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Append-only structured audit trail from <code className="text-cyan-300">logs/audit.jsonl</code>.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search audit trail..."
              className="w-full bg-[#0a0e17] border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <button
            onClick={loadLogs}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
        {['all', 'success', 'confirmation_required', 'denied', 'failure'].map((res) => (
          <button
            key={res}
            onClick={() => setFilterResult(res)}
            className={`px-3 py-1.5 rounded-xl text-xs font-medium uppercase tracking-wider transition-all ${
              filterResult === res
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {res.replace('_', ' ')}
          </button>
        ))}
      </div>

      {/* Log list */}
      {filteredLogs.length === 0 ? (
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-12 text-center text-slate-500 text-xs">
          No audit records matching criteria.
        </div>
      ) : (
        <div className="space-y-2">
          {filteredLogs.map((entry, idx) => {
            const isExpanded = expandedIndex === idx;
            return (
              <div
                key={idx}
                className="bg-[#0b1019] border border-slate-800/80 rounded-xl overflow-hidden text-xs"
              >
                <div
                  onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                  className="p-3.5 flex items-center justify-between gap-4 cursor-pointer hover:bg-slate-900/50"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {getResultBadge(entry.result)}
                    <span className="font-mono text-cyan-300 font-semibold">{entry.tool}</span>
                    <span className="text-slate-300 truncate">"{entry.user_command}"</span>
                  </div>

                  <div className="flex items-center gap-4 flex-shrink-0 text-[11px] font-mono text-slate-500">
                    <span>{entry.timestamp.replace('T', ' ').slice(0, 19)}</span>
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </div>

                {isExpanded && (
                  <div className="p-4 bg-[#080b11] border-t border-slate-800 space-y-2 font-mono text-[11px]">
                    <div>
                      <span className="text-slate-400">Arguments:</span>
                      <pre className="mt-1 p-2 bg-slate-900 rounded border border-slate-800 text-slate-300 overflow-x-auto">
                        {JSON.stringify(entry.arguments, null, 2)}
                      </pre>
                    </div>

                    {entry.output && (
                      <div>
                        <span className="text-slate-400">Output:</span>
                        <div className="mt-1 p-2 bg-slate-900 rounded border border-slate-800 text-slate-200 whitespace-pre-wrap">
                          {entry.output}
                        </div>
                      </div>
                    )}

                    {entry.error && (
                      <div>
                        <span className="text-rose-400">Error:</span>
                        <div className="mt-1 p-2 bg-rose-950/30 rounded border border-rose-800/40 text-rose-300">
                          {entry.error}
                        </div>
                      </div>
                    )}
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
