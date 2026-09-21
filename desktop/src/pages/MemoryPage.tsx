import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Database, Plus, Trash2, RefreshCw, Search, Key, X, Eye, Pencil, Copy, Check } from 'lucide-react';

export const MemoryPage: React.FC = () => {
  const [memory, setMemory] = useState<Record<string, any>>({});
  const [search, setSearch] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  // Add Modal State
  const [isAdding, setIsAdding] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newTtl, setNewTtl] = useState<string>('');

  // View Modal State
  const [viewingItem, setViewingItem] = useState<{ key: string; value: any } | null>(null);
  const [copied, setCopied] = useState(false);

  // Edit Modal State
  const [editingItem, setEditingItem] = useState<{ key: string; value: string; ttl: string } | null>(null);

  const loadMemory = async () => {
    setIsLoading(true);
    try {
      const data = await api.getMemory();
      setMemory(data);
    } catch (e) {
      console.error('Failed to load memory', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMemory();
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim()) return;

    let parsedVal: any = newValue;
    try {
      parsedVal = JSON.parse(newValue);
    } catch {
      // Treat as plain string
    }

    const ttl = newTtl ? parseInt(newTtl, 10) : undefined;
    try {
      await api.setMemory(newKey.trim(), parsedVal, ttl);
      setNewKey('');
      setNewValue('');
      setNewTtl('');
      setIsAdding(false);
      loadMemory();
    } catch (err) {
      console.error('Failed to set memory', err);
    }
  };

  const handleOpenEdit = (key: string) => {
    const rawVal = memory[key];
    const stringVal = typeof rawVal === 'object' ? JSON.stringify(rawVal, null, 2) : String(rawVal ?? '');
    setEditingItem({
      key,
      value: stringVal,
      ttl: '',
    });
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;

    let parsedVal: any = editingItem.value;
    try {
      parsedVal = JSON.parse(editingItem.value);
    } catch {
      // Treat as plain string
    }

    const ttl = editingItem.ttl ? parseInt(editingItem.ttl, 10) : undefined;
    try {
      await api.setMemory(editingItem.key, parsedVal, ttl);
      setEditingItem(null);
      loadMemory();
    } catch (err) {
      console.error('Failed to update memory', err);
    }
  };

  const handleDelete = async (key: string) => {
    if (!window.confirm(`Are you sure you want to delete memory entry '${key}'?`)) return;
    try {
      await api.deleteMemory(key);
      if (viewingItem?.key === key) setViewingItem(null);
      if (editingItem?.key === key) setEditingItem(null);
      loadMemory();
    } catch (err) {
      console.error('Failed to delete memory', err);
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm('Are you sure you want to clear all agent memory entries? This action cannot be undone.')) return;
    try {
      await api.clearMemory();
      setViewingItem(null);
      setEditingItem(null);
      loadMemory();
    } catch (err) {
      console.error('Failed to clear memory', err);
    }
  };

  const handleCopyValue = (val: any) => {
    const text = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val ?? '');
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const filteredKeys = Object.keys(memory).filter((k) =>
    k.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-8 space-y-6 max-w-6xl mx-auto overflow-y-auto h-[calc(100vh-4rem)] select-none">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Database className="w-5 h-5 text-cyan-400" />
            <span>Short-Term Memory Store</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Inspect, edit, and delete short-term memory key-value entries maintained across agent turns.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadMemory}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors"
            title="Refresh Memory Store"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
          <button
            onClick={() => setIsAdding(true)}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded-xl flex items-center gap-1.5 shadow-md shadow-cyan-950/40 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Key</span>
          </button>
          <button
            onClick={handleClearAll}
            disabled={filteredKeys.length === 0}
            className="px-4 py-2 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 text-xs font-semibold rounded-xl flex items-center gap-1.5 transition-colors disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear All</span>
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative max-w-md">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter memory keys..."
          className="w-full bg-[#0a0e17] border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
        />
      </div>

      {/* Memory Entries List */}
      {filteredKeys.length === 0 ? (
        <div className="bg-[#0b1019] border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500 text-xs">
          {search ? 'No matching memory keys found.' : 'No memory entries found. Add a key or let the agent store context.'}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredKeys.map((key) => {
            const rawVal = memory[key];
            const isObj = typeof rawVal === 'object' && rawVal !== null;
            const displayPreview = isObj
              ? JSON.stringify(rawVal)
              : String(rawVal ?? '');

            return (
              <div
                key={key}
                className="bg-[#0b1019] border border-slate-800/80 rounded-xl p-4 flex items-start justify-between gap-4 hover:border-slate-700/80 transition-colors"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Key className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="font-mono text-cyan-300 font-semibold text-xs">{key}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                      {isObj ? (Array.isArray(rawVal) ? 'array' : 'object') : typeof rawVal}
                    </span>
                  </div>
                  <pre className="bg-[#07090e] border border-slate-800/80 rounded-lg p-2.5 text-xs font-mono text-slate-300 truncate overflow-x-auto max-h-24">
                    {typeof rawVal === 'object'
                      ? JSON.stringify(rawVal, null, 2)
                      : String(rawVal ?? '')}
                  </pre>
                </div>

                {/* Actions: View, Edit, Delete */}
                <div className="flex items-center gap-1.5 flex-shrink-0 pt-1">
                  <button
                    onClick={() => setViewingItem({ key, value: rawVal })}
                    className="p-2 text-slate-400 hover:text-cyan-300 hover:bg-slate-800/80 rounded-lg transition-colors"
                    title="View Details"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleOpenEdit(key)}
                    className="p-2 text-slate-400 hover:text-amber-300 hover:bg-slate-800/80 rounded-lg transition-colors"
                    title="Edit Entry"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDelete(key)}
                    className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 rounded-lg transition-colors"
                    title="Delete Entry"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────── */}
      {/* VIEW MODAL                                                     */}
      {/* ────────────────────────────────────────────────────────────── */}
      {viewingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-[#0e131f] border border-slate-700 rounded-2xl shadow-2xl p-6 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white font-mono">{viewingItem.key}</h3>
              </div>
              <button
                onClick={() => setViewingItem(null)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between text-slate-400">
                <span>Value Content</span>
                <button
                  onClick={() => handleCopyValue(viewingItem.value)}
                  className="flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>

              <pre className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-3 text-xs font-mono text-cyan-200 overflow-y-auto max-h-72 whitespace-pre-wrap select-text">
                {typeof viewingItem.value === 'object'
                  ? JSON.stringify(viewingItem.value, null, 2)
                  : String(viewingItem.value ?? '')}
              </pre>
            </div>

            <div className="pt-2 flex justify-end gap-2">
              <button
                onClick={() => {
                  handleOpenEdit(viewingItem.key);
                  setViewingItem(null);
                }}
                className="px-4 py-2 bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/30 rounded-xl text-xs font-medium"
              >
                Edit
              </button>
              <button
                onClick={() => setViewingItem(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────── */}
      {/* EDIT MODAL                                                     */}
      {/* ────────────────────────────────────────────────────────────── */}
      {editingItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-[#0e131f] border border-slate-700 rounded-2xl shadow-2xl p-6 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Pencil className="w-4 h-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-white">Edit Memory Key</h3>
              </div>
              <button
                onClick={() => setEditingItem(null)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Key (Read Only)</label>
                <input
                  type="text"
                  disabled
                  value={editingItem.key}
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-400 font-mono opacity-80 cursor-not-allowed"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Value (String or JSON)</label>
                <textarea
                  rows={5}
                  required
                  value={editingItem.value}
                  onChange={(e) => setEditingItem({ ...editingItem, value: e.target.value })}
                  placeholder='e.g. "newValue" or {"setting": true}'
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Time to Live (Seconds, Optional)</label>
                <input
                  type="number"
                  value={editingItem.ttl}
                  onChange={(e) => setEditingItem({ ...editingItem, ttl: e.target.value })}
                  placeholder="Leave empty to retain without TTL"
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditingItem(null)}
                  className="px-4 py-2 text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl font-semibold"
                >
                  Update Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────────── */}
      {/* ADD MODAL                                                      */}
      {/* ────────────────────────────────────────────────────────────── */}
      {isAdding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-[#0e131f] border border-slate-700 rounded-2xl shadow-2xl p-6 space-y-4 animate-in fade-in">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white">Store Memory Item</h3>
              <button
                onClick={() => setIsAdding(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAdd} className="space-y-3 text-xs">
              <div>
                <label className="text-slate-300 block mb-1">Key Name</label>
                <input
                  type="text"
                  required
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="e.g. user_preferred_app"
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Value (String or JSON)</label>
                <textarea
                  rows={4}
                  required
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder='e.g. "WhatsApp" or {"theme": "dark"}'
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Time to Live (Seconds, Optional)</label>
                <input
                  type="number"
                  value={newTtl}
                  onChange={(e) => setNewTtl(e.target.value)}
                  placeholder="Leave empty for persistent"
                  className="w-full bg-[#07090e] border border-slate-800 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAdding(false)}
                  className="px-4 py-2 text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl font-semibold"
                >
                  Save Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
