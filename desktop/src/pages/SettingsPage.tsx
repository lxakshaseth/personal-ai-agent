import React, { useState, useEffect } from 'react';
import { AgentConfig } from '../types/agent';
import { api } from '../services/api';
import {
  Settings,
  Save,
  CheckCircle2,
  Bot,
  Mic,
  Volume2,
  Shield,
  Monitor,
  FileText,
  Sparkles,
  RefreshCw,
  Download,
} from 'lucide-react';

interface UIPreferences {
  theme: 'dark' | 'cyber' | 'midnight' | 'system';
  voiceFeedback: boolean;
  speechRate: number;
  speechVolume: number;
  micDevice: string;
  inputMode: 'push_to_talk' | 'continuous';
  startOnBoot: boolean;
  startMinimized: boolean;
  autoConnectBackend: boolean;
  closeToTray: boolean;
  confirmationTimeout: number;
  logLevel: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  logRetentionDays: number;
}

const DEFAULT_UI_PREFS: UIPreferences = {
  theme: 'dark',
  voiceFeedback: true,
  speechRate: 1.0,
  speechVolume: 1.0,
  micDevice: 'default',
  inputMode: 'push_to_talk',
  startOnBoot: false,
  startMinimized: false,
  autoConnectBackend: true,
  closeToTray: true,
  confirmationTimeout: 60,
  logLevel: 'INFO',
  logRetentionDays: 30,
};

const PREFS_STORAGE_KEY = 'nova_ai_ui_preferences';

export const SettingsPage: React.FC = () => {
  const [config, setConfig] = useState<AgentConfig | null>(null);
  const [prefs, setPrefs] = useState<UIPreferences>(DEFAULT_UI_PREFS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  // Load preferences from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(PREFS_STORAGE_KEY);
      if (stored) {
        setPrefs({ ...DEFAULT_UI_PREFS, ...JSON.parse(stored) });
      }
    } catch (e) {
      console.error('Failed to parse stored UI preferences', e);
    }
  }, []);

  // Load backend config
  const loadConfig = async () => {
    setIsLoading(true);
    try {
      const data = await api.getConfig();
      setConfig(data);
    } catch (e) {
      console.error('Failed to load backend config', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSavedSuccess(false);

    try {
      // 1. Persist UI preferences in localStorage
      localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(prefs));

      // 2. Persist backend config
      if (config) {
        await api.updateConfig({
          groq_model: config.groq_model,
          stt_provider: config.stt_provider,
          tts_provider: config.tts_provider,
          voice_enabled: config.voice_enabled,
          wake_word: config.wake_word,
          wake_word_enabled: config.wake_word_enabled,
          allow_shell_commands: config.allow_shell_commands,
          require_confirmation: config.require_confirmation,
        });
      }

      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3500);
    } catch (err: any) {
      console.error('Failed to save settings', err);
      alert(`Error saving configuration: ${err.message || 'Unknown error'}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleExportLogs = async () => {
    try {
      const logs = await api.getAuditLogs(200);
      const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `nova-ai-audit-logs-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('Failed to export audit logs');
    }
  };

  const handleClearCache = () => {
    if (!window.confirm('Reset all local UI preferences and clear cached session data?')) return;
    localStorage.removeItem(PREFS_STORAGE_KEY);
    setPrefs(DEFAULT_UI_PREFS);
    alert('UI preferences have been reset to defaults.');
  };

  if (isLoading || !config) {
    return (
      <div className="p-8 text-center text-slate-500 text-xs">
        Loading agent configuration...
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6 max-w-4xl mx-auto overflow-y-auto h-[calc(100vh-4rem)] select-none">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Settings className="w-5 h-5 text-cyan-400" />
            <span>Agent Configuration & Preferences</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Configure Groq LLM, speech audio devices, wake-word parameters, theme, startup behavior, and logging.
          </p>
        </div>

        <button
          onClick={loadConfig}
          className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition-colors"
          title="Reload Backend Config"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* 1. Groq Model Card */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Groq LLM Configuration</h3>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Selected Model</label>
              <select
                value={config.groq_model}
                onChange={(e) => setConfig({ ...config, groq_model: e.target.value })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
              >
                <option value="openai/gpt-oss-120b">openai/gpt-oss-120b (Recommended - Full Tool Calling Support)</option>
                <option value="llama-3.3-70b-versatile">llama-3.3-70b-versatile (Fast & Versatile)</option>
                <option value="llama-3.1-8b-instant">llama-3.1-8b-instant (Lightweight)</option>
                <option value="mixtral-8x7b-32768">mixtral-8x7b-32768 (32k Context Window)</option>
              </select>
              <span className="text-[11px] text-slate-500 mt-1 block">
                Primary model used for intention analysis, planning pipelines, argument parsing, and conversational responses.
              </span>
            </div>
          </div>
        </div>

        {/* 2. Voice & Audio Settings */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-white">Voice & Speech Synthesis</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Speech-to-Text (STT) Provider</label>
              <select
                value={config.stt_provider}
                onChange={(e) => setConfig({ ...config, stt_provider: e.target.value })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-purple-500 font-mono"
              >
                <option value="groq">groq (Whisper Cloud API)</option>
                <option value="openai">openai (Whisper API)</option>
                <option value="local_whisper">local_whisper (Offline faster-whisper)</option>
                <option value="mock">mock (Deterministic Testing Mock)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-300 block mb-1 font-medium">Text-to-Speech (TTS) Provider</label>
              <select
                value={config.tts_provider}
                onChange={(e) => setConfig({ ...config, tts_provider: e.target.value })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-purple-500 font-mono"
              >
                <option value="system">system (Windows Native SAPI5 / PowerShell)</option>
                <option value="pyttsx3">pyttsx3 (Offline Direct TTS)</option>
                <option value="mock">mock (Silent Mock)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-300 block mb-1 font-medium">
                Speech Rate: <span className="font-mono text-purple-300">{prefs.speechRate}x</span>
              </label>
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.1"
                value={prefs.speechRate}
                onChange={(e) => setPrefs({ ...prefs, speechRate: parseFloat(e.target.value) })}
                className="w-full accent-purple-500"
              />
            </div>

            <div>
              <label className="text-slate-300 block mb-1 font-medium">
                Speech Volume: <span className="font-mono text-purple-300">{Math.round(prefs.speechVolume * 100)}%</span>
              </label>
              <input
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={prefs.speechVolume}
                onChange={(e) => setPrefs({ ...prefs, speechVolume: parseFloat(e.target.value) })}
                className="w-full accent-purple-500"
              />
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800/80 flex flex-wrap gap-4 text-xs">
            <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={config.voice_enabled}
                onChange={(e) => setConfig({ ...config, voice_enabled: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-purple-500"
              />
              <span>Voice Interface Enabled</span>
            </label>

            <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.voiceFeedback}
                onChange={(e) => setPrefs({ ...prefs, voiceFeedback: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-purple-500"
              />
              <span>Auto-Speak Agent Responses aloud</span>
            </label>
          </div>
        </div>

        {/* 3. Microphone & Audio Input */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Mic className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-semibold text-white">Microphone & Audio Capture</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Microphone Device</label>
              <select
                value={prefs.micDevice}
                onChange={(e) => setPrefs({ ...prefs, micDevice: e.target.value })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="default">Default Windows Recording Device</option>
                <option value="realtek">Realtek High Definition Audio (Built-in)</option>
                <option value="usb_headset">USB Audio / Headset Microphone</option>
              </select>
            </div>

            <div>
              <label className="text-slate-300 block mb-1 font-medium">Input Trigger Mode</label>
              <select
                value={prefs.inputMode}
                onChange={(e) => setPrefs({ ...prefs, inputMode: e.target.value as any })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-blue-500"
              >
                <option value="push_to_talk">Push-to-Talk (Ctrl + Space)</option>
                <option value="continuous">Continuous Listening with VAD</option>
              </select>
            </div>
          </div>
        </div>

        {/* 4. Wake Word Settings */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Wake Word Activation</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Wake Word Phrase</label>
              <input
                type="text"
                value={config.wake_word}
                onChange={(e) => setConfig({ ...config, wake_word: e.target.value })}
                placeholder="e.g. Jarvis or Nova"
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
              />
            </div>

            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.wake_word_enabled}
                  onChange={(e) => setConfig({ ...config, wake_word_enabled: e.target.checked })}
                  className="rounded bg-slate-800 border-slate-700 text-cyan-500"
                />
                <span>Enable Wake Word Detection</span>
              </label>
            </div>
          </div>
        </div>

        {/* 5. Theme & Appearance (persisted in localStorage) */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Theme & UI Appearance</h3>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            {[
              { id: 'dark', label: 'Dark Slate (Default)', bg: 'bg-[#07090e]' },
              { id: 'cyber', label: 'Cyber Neon', bg: 'bg-[#040d1a]' },
              { id: 'midnight', label: 'Midnight Black', bg: 'bg-[#000000]' },
              { id: 'system', label: 'Windows System', bg: 'bg-[#0f172a]' },
            ].map((themeItem) => (
              <button
                key={themeItem.id}
                type="button"
                onClick={() => setPrefs({ ...prefs, theme: themeItem.id as any })}
                className={`p-3 rounded-xl border text-left transition-all ${
                  prefs.theme === themeItem.id
                    ? 'border-cyan-500 bg-cyan-950/30 text-white font-medium shadow-md shadow-cyan-950/40'
                    : 'border-slate-800 bg-slate-900/50 text-slate-400 hover:text-slate-200'
                }`}
              >
                <div className={`w-full h-8 rounded-lg mb-2 border border-slate-800 ${themeItem.bg}`} />
                <span>{themeItem.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 6. Startup Behavior (persisted in localStorage) */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-teal-400" />
            <h3 className="text-sm font-semibold text-white">Windows Startup & Tray Behavior</h3>
          </div>

          <div className="space-y-2 text-xs">
            <label className="flex items-center gap-2.5 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.startOnBoot}
                onChange={(e) => setPrefs({ ...prefs, startOnBoot: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-teal-500"
              />
              <span>Launch NOVA AI on Windows boot</span>
            </label>

            <label className="flex items-center gap-2.5 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.startMinimized}
                onChange={(e) => setPrefs({ ...prefs, startMinimized: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-teal-500"
              />
              <span>Start minimized to system notification area (tray)</span>
            </label>

            <label className="flex items-center gap-2.5 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.closeToTray}
                onChange={(e) => setPrefs({ ...prefs, closeToTray: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-teal-500"
              />
              <span>Minimize to tray instead of quitting when window is closed</span>
            </label>

            <label className="flex items-center gap-2.5 text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={prefs.autoConnectBackend}
                onChange={(e) => setPrefs({ ...prefs, autoConnectBackend: e.target.checked })}
                className="rounded bg-slate-800 border-slate-700 text-teal-500"
              />
              <span>Automatically connect to localhost:8000 on application start</span>
            </label>
          </div>
        </div>

        {/* 7. Confirmation Settings */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-white">Confirmation & Approval Settings</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Confirmation Timeout (Seconds)</label>
              <input
                type="number"
                min="10"
                max="300"
                value={prefs.confirmationTimeout}
                onChange={(e) => setPrefs({ ...prefs, confirmationTimeout: parseInt(e.target.value, 10) || 60 })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-emerald-500"
              />
              <span className="text-[11px] text-slate-500 mt-1 block">
                Time before pending HIGH-risk tool approvals expire automatically.
              </span>
            </div>

            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.require_confirmation}
                  onChange={(e) => setConfig({ ...config, require_confirmation: e.target.checked })}
                  className="rounded bg-slate-800 border-slate-700 text-emerald-500"
                />
                <span>Enforce interactive confirmation on HIGH-risk actions</span>
              </label>
            </div>
          </div>
        </div>

        {/* 8. Logging & Diagnostics */}
        <div className="bg-[#0b1019] border border-slate-800 rounded-2xl p-5 space-y-4">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">Logging & Diagnostic Storage</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <label className="text-slate-300 block mb-1 font-medium">Log Level</label>
              <select
                value={prefs.logLevel}
                onChange={(e) => setPrefs({ ...prefs, logLevel: e.target.value as any })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-amber-500 font-mono"
              >
                <option value="DEBUG">DEBUG (Verbose diagnostic trace)</option>
                <option value="INFO">INFO (Standard production logs)</option>
                <option value="WARNING">WARNING (Only warnings and failures)</option>
                <option value="ERROR">ERROR (Only critical exceptions)</option>
              </select>
            </div>

            <div>
              <label className="text-slate-300 block mb-1 font-medium">Log Retention (Days)</label>
              <input
                type="number"
                min="1"
                max="365"
                value={prefs.logRetentionDays}
                onChange={(e) => setPrefs({ ...prefs, logRetentionDays: parseInt(e.target.value, 10) || 30 })}
                className="w-full bg-[#07090e] border border-slate-700/80 rounded-xl p-2.5 text-slate-200 focus:outline-none focus:border-amber-500"
              />
            </div>
          </div>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={handleExportLogs}
              className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export Audit Logs (JSON)</span>
            </button>

            <button
              type="button"
              onClick={handleClearCache}
              className="px-3.5 py-2 bg-rose-950/30 hover:bg-rose-950/50 text-rose-300 border border-rose-800/40 rounded-xl text-xs font-medium transition-colors"
            >
              Reset Local Preferences
            </button>
          </div>
        </div>

        {/* Form Actions Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
          {savedSuccess && (
            <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold animate-in fade-in">
              <CheckCircle2 className="w-4 h-4" />
              <span>All preferences and settings successfully saved to localStorage & backend!</span>
            </div>
          )}
          <div className="ml-auto">
            <button
              type="submit"
              disabled={isSaving}
              className="px-6 py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-cyan-950/40 transition-all flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              <span>{isSaving ? 'Saving Changes...' : 'Save All Settings'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
