import React, { useState, useEffect } from 'react';
import { ToolInfo } from '../types/agent';
import { api } from '../services/api';
import {
  Wrench,
  Search,
  Folder,
  Globe,
  Monitor,
  Terminal,
  MessageSquare,
  Activity,
  Play,
  CheckCircle2,
  XCircle,
  X,
  ToggleLeft,
  ToggleRight,
} from 'lucide-react';

export const ToolsPage: React.FC = () => {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [disabledTools, setDisabledTools] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  // Test Drawer state
  const [testingTool, setTestingTool] = useState<ToolInfo | null>(null);
  const [testArgs, setTestArgs] = useState<string>('{}');
  const [testConfirmed, setTestConfirmed] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [toolsRes, secRes] = await Promise.all([
          api.getTools(),
          api.getSecuritySettings(),
        ]);
        setTools(toolsRes.tools);
        setDisabledTools(secRes.disabled_tools || []);
      } catch (e) {
        console.error('Failed to load tools and security settings', e);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const getToolCategory = (name: string): string => {
    if (name.includes('whatsapp')) return 'whatsapp';
    if (name.includes('url') || name.includes('browser')) return 'browser';
    if (
      name.includes('folder') ||
      name.includes('file') ||
      name.includes('directory')
    )
      return 'filesystem';
    if (name.includes('screenshot') || name.includes('computer')) return 'windows';
    if (
      name.includes('cpu') ||
      name.includes('memory') ||
      name.includes('disk') ||
      name.includes('process') ||
      name.includes('system') ||
      name.includes('time')
    )
      return 'system';
    if (name.includes('command')) return 'terminal';
    return 'system';
  };

  const handleToggleTool = async (toolName: string) => {
    const isCurrentlyDisabled = disabledTools.includes(toolName);
    const updated = isCurrentlyDisabled
      ? disabledTools.filter((t) => t !== toolName)
      : [...disabledTools, toolName];

    setDisabledTools(updated);
    try {
      await api.updateSecuritySettings({ disabled_tools: updated });
    } catch (err) {
      console.error('Failed to update tool state in backend', err);
    }
  };

  const categories = [
    { id: 'all', label: 'All Tools', count: tools.length },
    { id: 'filesystem', label: 'Filesystem', icon: Folder, count: tools.filter((t) => getToolCategory(t.name) === 'filesystem').length },
    { id: 'browser', label: 'Browser', icon: Globe, count: tools.filter((t) => getToolCategory(t.name) === 'browser').length },
    { id: 'windows', label: 'Windows', icon: Monitor, count: tools.filter((t) => getToolCategory(t.name) === 'windows').length },
    { id: 'terminal', label: 'Terminal', icon: Terminal, count: tools.filter((t) => getToolCategory(t.name) === 'terminal').length },
    { id: 'whatsapp', label: 'WhatsApp', icon: MessageSquare, count: tools.filter((t) => getToolCategory(t.name) === 'whatsapp').length },
    { id: 'system', label: 'System', icon: Activity, count: tools.filter((t) => getToolCategory(t.name) === 'system').length },
  ];

  const filteredTools = tools.filter((tool) => {
    const matchesSearch =
      tool.name.toLowerCase().includes(search.toLowerCase()) ||
      tool.description.toLowerCase().includes(search.toLowerCase());
    const matchesCat = selectedCategory === 'all' || getToolCategory(tool.name) === selectedCategory;
    return matchesSearch && matchesCat;
  });

  const openTestDrawer = (tool: ToolInfo) => {
    setTestingTool(tool);
    const defaultArgs: Record<string, any> = {};
    if (tool.parameters_schema?.properties) {
      for (const [key, prop] of Object.entries<any>(tool.parameters_schema.properties)) {
        defaultArgs[key] = prop.default !== undefined ? prop.default : '';
      }
    }
    setTestArgs(JSON.stringify(defaultArgs, null, 2));
    setTestConfirmed(false);
    setTestResult(null);
  };

  const executeTest = async () => {
    if (!testingTool) return;
    setIsExecuting(true);
    setTestResult(null);
    try {
      let parsed = {};
      try {
        parsed = JSON.parse(testArgs);
      } catch {
        setTestResult({ success: false, error: 'Invalid JSON argument syntax.' });
        setIsExecuting(false);
        return;
      }
      const res = await api.executeTool(testingTool.name, parsed, testConfirmed);
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="p-8 space-y-6 max-w-7xl mx-auto overflow-y-auto h-[calc(100vh-4rem)] font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Wrench className="w-5 h-5 text-cyan-400" />
            <span>Registered Computer-Control Tools</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Browse active tool modules, inspect permission tiers, and toggle availability.
          </p>
        </div>

        <div className="relative w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tools..."
            className="w-full bg-[#0a0e17] border border-slate-700/80 rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Categories Tabs matching requested categories */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-3 overflow-x-auto">
        {categories.map((c) => {
          const Icon = c.icon;
          return (
            <button
              key={c.id}
              onClick={() => setSelectedCategory(c.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all whitespace-nowrap flex items-center gap-2 ${
                selectedCategory === c.id
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 border border-transparent'
              }`}
            >
              {Icon && <Icon className="w-3.5 h-3.5" />}
              <span>{c.label}</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-400">
                {c.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tools Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredTools.map((tool) => {
          const isEnabled = !disabledTools.includes(tool.name);
          return (
            <div
              key={tool.name}
              className={`bg-[#0b1019] border rounded-2xl p-5 flex flex-col justify-between transition-all ${
                isEnabled
                  ? 'border-slate-800/80 hover:border-slate-700 shadow-sm'
                  : 'border-slate-800/40 opacity-60'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono text-cyan-300 text-sm font-semibold">
                    {tool.name}
                  </span>

                  {/* Permission Level */}
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold border ${
                      tool.permission_level === 'HIGH'
                        ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                        : tool.permission_level === 'MEDIUM'
                        ? 'bg-blue-500/10 text-blue-300 border-blue-500/30'
                        : 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                    }`}
                  >
                    {tool.permission_level}
                  </span>
                </div>

                <p className="text-xs text-slate-400 leading-relaxed mb-3 line-clamp-2">
                  {tool.description}
                </p>
              </div>

              {/* Bottom Row: Enabled/Disabled Toggle & Test Button */}
              <div className="pt-3 border-t border-slate-800/60 flex items-center justify-between">
                {/* Enabled/Disabled Toggle */}
                <button
                  onClick={() => handleToggleTool(tool.name)}
                  className={`flex items-center gap-1.5 text-xs font-medium transition-colors ${
                    isEnabled ? 'text-emerald-400' : 'text-slate-500'
                  }`}
                  title={isEnabled ? 'Click to Disable' : 'Click to Enable'}
                >
                  {isEnabled ? (
                    <ToggleRight className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <ToggleLeft className="w-5 h-5 text-slate-600" />
                  )}
                  <span>{isEnabled ? 'Enabled' : 'Disabled'}</span>
                </button>

                <button
                  onClick={() => openTestDrawer(tool)}
                  disabled={!isEnabled}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-cyan-950/60 hover:text-cyan-300 border border-slate-700 hover:border-cyan-700/50 rounded-lg text-xs font-medium text-slate-300 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Play className="w-3 h-3" />
                  <span>Test</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Tool Test Modal */}
      {testingTool && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-xl bg-[#0e131f] border border-slate-700 rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-6 py-4 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
              <span className="font-semibold text-white text-sm">
                Test Tool: <code className="text-cyan-300">{testingTool.name}</code>
              </span>
              <button
                onClick={() => setTestingTool(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-xs text-slate-400">{testingTool.description}</p>
              <div>
                <label className="text-xs text-slate-300 font-medium mb-1 block">
                  Arguments (JSON):
                </label>
                <textarea
                  rows={4}
                  value={testArgs}
                  onChange={(e) => setTestArgs(e.target.value)}
                  className="w-full bg-[#080b11] border border-slate-800 rounded-xl p-3 font-mono text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>

              {testingTool.requires_confirmation && (
                <label className="flex items-center gap-2 text-xs text-amber-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={testConfirmed}
                    onChange={(e) => setTestConfirmed(e.target.checked)}
                    className="rounded bg-slate-800 border-slate-700 text-amber-500"
                  />
                  <span>Confirm HIGH-risk execution</span>
                </label>
              )}

              {testResult && (
                <div
                  className={`p-3 rounded-xl border text-xs font-mono whitespace-pre-wrap ${
                    testResult.success
                      ? 'bg-emerald-950/30 border-emerald-800/40 text-emerald-200'
                      : 'bg-rose-950/30 border-rose-800/40 text-rose-200'
                  }`}
                >
                  <div className="font-semibold mb-1">
                    {testResult.success ? '✓ Output:' : '✗ Error:'}
                  </div>
                  {testResult.output || testResult.error}
                </div>
              )}
            </div>

            <div className="px-6 py-4 bg-slate-900/60 border-t border-slate-800 flex justify-end gap-3">
              <button
                onClick={() => setTestingTool(null)}
                className="px-4 py-2 text-xs text-slate-400 hover:text-white"
              >
                Close
              </button>
              <button
                onClick={executeTest}
                disabled={isExecuting}
                className="px-5 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded-xl flex items-center gap-2"
              >
                <Play className="w-3.5 h-3.5" />
                <span>{isExecuting ? 'Running...' : 'Execute Tool'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
