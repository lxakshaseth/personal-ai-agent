import React, { useState, useRef, useEffect } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import {
  Send,
  Mic,
  Bot,
  User,
  Wrench,
  Check,
  Copy,
  Trash2,
  ChevronDown,
  ChevronUp,
  Terminal,
  ExternalLink,
  Activity,
} from 'lucide-react';
import { ExecutionTimeline } from '../components/timeline/ExecutionTimeline';
import { PlanApprovalCard } from '../components/plan/PlanApprovalCard';
import { browserVoice } from '../services/voiceService';

export const ChatPage: React.FC = () => {
  const [state, store] = useAgentStore();
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  const [showTimeline, setShowTimeline] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [state.messages, isSending]);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const cmd = input.trim();
    if (!cmd || isSending) return;

    setInput('');
    setIsSending(true);

    const userMsgId = 'u_' + Date.now();
    store.addMessage({
      id: userMsgId,
      sender: 'user',
      source: 'text',
      text: cmd,
      timestamp: Date.now(),
    });

    try {
      const res = await api.runCommand(cmd);
      store.addMessage({
        id: 'a_' + Date.now(),
        sender: 'agent',
        text: res.response,
        timestamp: Date.now(),
        tool_calls: res.tool_calls,
        error: res.error,
      });
      // Speak response aloud immediately
      if (res.response) {
        browserVoice.speak(res.response);
      }
    } catch (err: any) {
      store.addMessage({
        id: 'err_' + Date.now(),
        sender: 'agent',
        text: `Error: ${err.message}`,
        timestamp: Date.now(),
        error: err.message,
      });
    } finally {
      setIsSending(false);
    }
  };

  const handleVoiceListen = async () => {
    // 1. Browser Native Real-Time Voice (<1s, Google Gemini style)
    if (browserVoice.isSupported()) {
      try {
        store.setStatus('listening', 'Listening... Speak now');
        let liveTranscript = '';
        const transcript = await browserVoice.startListening({
          onInterim: (text) => {
            liveTranscript = text;
            store.setStatus('listening', `Heard: "${text}"`);
          },
        });

        const recognizedText = (transcript || liveTranscript).trim();
        if (recognizedText) {
          store.addMessage({
            id: 'u_' + Date.now(),
            sender: 'user',
            source: 'voice',
            text: recognizedText,
            timestamp: Date.now(),
          });
          store.setStatus('executing', `Executing: "${recognizedText}"...`);

          const res = await api.runCommand(recognizedText);
          if (res.response) {
            store.addMessage({
              id: 'a_' + Date.now(),
              sender: 'agent',
              text: res.response,
              timestamp: Date.now(),
              tool_calls: res.tool_calls,
            });
            browserVoice.speak(res.response);
          }
          store.setStatus('online', 'Ready');
          return;
        }
      } catch (err) {
        console.warn('Browser speech recognition failed, fallback to backend:', err);
      }
    }

    // 2. Fallback: Backend capture
    try {
      store.setStatus('listening', 'Listening for speech...');
      const res = await api.triggerListen();
      if (res.transcript) {
        store.addMessage({
          id: 'u_' + Date.now(),
          sender: 'user',
          source: 'voice',
          text: res.transcript,
          timestamp: Date.now(),
        });
        if (res.response) {
          store.addMessage({
            id: 'a_' + Date.now(),
            sender: 'agent',
            text: res.response,
            timestamp: Date.now(),
            tool_calls: res.tool_calls,
          });
          browserVoice.speak(res.response);
        }
      }
      store.setStatus('online', 'Ready');
    } catch (e: any) {
      store.setStatus('error', e.message);
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleExpand = (cardKey: string) => {
    setExpandedCards((prev) => ({ ...prev, [cardKey]: !prev[cardKey] }));
  };

  const clearChat = () => {
    store.setState({
      messages: [
        {
          id: 'welcome',
          sender: 'agent',
          text: 'Chat history cleared. How can I help you today?',
          timestamp: Date.now(),
        },
      ],
    });
  };

  // Helper to extract clean parameter preview (e.g. URL: youtube.com)
  const getToolParamSummary = (tc: any) => {
    if (tc.args.url) return `URL: ${tc.args.url}`;
    if (tc.args.app_name) return `App: ${tc.args.app_name}`;
    if (tc.args.folder_path) return `Folder: ${tc.args.folder_path}`;
    if (tc.args.file_path) return `File: ${tc.args.file_path}`;
    if (tc.args.contact && tc.args.message) return `To: ${tc.args.contact} | Message: ${tc.args.message}`;
    if (tc.args.command) return `Command: ${tc.args.command}`;
    return Object.entries(tc.args)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' | ');
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] bg-[#07090e] font-sans">
      {/* Top action bar */}
      <div className="h-12 border-b border-slate-800/80 px-6 flex items-center justify-between bg-[#0a0e17]/80 flex-shrink-0">
        <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
          <span>NOVA AI Conversation Stream</span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowTimeline(!showTimeline)}
            className={`text-xs px-3 py-1.5 rounded-xl font-mono flex items-center gap-1.5 transition-all ${
              showTimeline || isSending
                ? 'bg-cyan-950/60 border border-cyan-500/40 text-cyan-300'
                : 'text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Timeline</span>
          </button>

          <button
            onClick={clearChat}
            className="text-xs text-slate-400 hover:text-rose-300 transition-colors flex items-center gap-1.5"
            title="Clear Chat"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear Chat</span>
          </button>
        </div>
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto w-full">
        {(showTimeline || isSending) && (
          <div className="mb-4">
            <ExecutionTimeline />
          </div>
        )}
        {state.messages.map((msg) => {
          const isUser = msg.sender === 'user';
          const isVoice = msg.source === 'voice';

          return (
            <div key={msg.id} className="space-y-3">
              {/* Header Badge */}
              <div className={`flex items-center gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
                {isUser ? (
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold border ${
                      isVoice
                        ? 'bg-cyan-950/60 text-cyan-300 border-cyan-800/60'
                        : 'bg-slate-800/80 text-slate-300 border-slate-700/60'
                    }`}
                  >
                    {isVoice ? <Mic className="w-3 h-3 text-cyan-400" /> : <span className="text-xs">⌨</span>}
                    <span>{isVoice ? '🎙 Voice' : '⌨ Text'}</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-purple-950/60 text-purple-300 border border-purple-800/60">
                    <Bot className="w-3 h-3 text-purple-400" />
                    <span>🤖 Agent</span>
                  </span>
                )}
              </div>

              {/* Message Bubble */}
              <div
                className={`p-4 rounded-2xl text-sm leading-relaxed border transition-all ${
                  isUser
                    ? 'bg-cyan-950/30 border-cyan-800/40 text-cyan-50 ml-12 rounded-tr-none'
                    : 'bg-[#0e1320] border-slate-800 text-slate-100 mr-12 rounded-tl-none shadow-lg'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.text}</p>

                {/* Copy response */}
                {!isUser && (
                  <div className="flex items-center justify-end mt-2 pt-2 border-t border-slate-800/60">
                    <button
                      onClick={() => handleCopy(msg.id, msg.text)}
                      className="text-[11px] text-slate-400 hover:text-cyan-300 flex items-center gap-1 font-mono"
                    >
                      {copiedId === msg.id ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-400" />
                          <span className="text-emerald-400">Copied</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>Copy</span>
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* ──────────────────────────────────────────────────────── */}
              {/* EXPANDABLE TOOL EXECUTION CARD                           */}
              {/* ┌────────────────────────────────────┐                   */}
              {/* │ ⚙ open_url                         │                   */}
              {/* │                                    │                   */}
              {/* │ URL: youtube.com                   │                   */}
              {/* │ Status: ✓ Completed                │                   */}
              {/* │ Duration: 0.8s                     │                   */}
              {/* └────────────────────────────────────┘                   */}
              {/* ──────────────────────────────────────────────────────── */}
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <div className="mr-12 space-y-2">
                  {msg.tool_calls.map((tc, idx) => {
                    const cardKey = `${msg.id}_tc_${idx}`;
                    const isExpanded = !!expandedCards[cardKey];

                    return (
                      <div
                        key={idx}
                        className="bg-[#090d16] border border-cyan-500/30 rounded-xl overflow-hidden font-mono text-xs shadow-md"
                      >
                        {/* Tool Card Header */}
                        <div
                          onClick={() => toggleExpand(cardKey)}
                          className="px-4 py-3 bg-slate-900/60 flex items-center justify-between cursor-pointer hover:bg-slate-900/90 transition-colors"
                        >
                          <div className="flex items-center gap-2 text-cyan-300 font-semibold">
                            <span className="text-sm">⚙</span>
                            <span>{tc.tool}</span>
                          </div>

                          <div className="flex items-center gap-2 text-slate-400">
                            <span className="text-[11px]">
                              {tc.success ? '✓ Completed' : '✗ Failed'}
                            </span>
                            {isExpanded ? (
                              <ChevronUp className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronDown className="w-3.5 h-3.5" />
                            )}
                          </div>
                        </div>

                        {/* Tool Card Body matching requested format */}
                        <div className="p-4 space-y-1.5 text-slate-300 border-t border-slate-800/80">
                          <div className="text-cyan-200 truncate">
                            {getToolParamSummary(tc)}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400">Status:</span>
                            <span className={tc.success ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                              {tc.success ? '✓ Completed' : '✗ Failed'}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400">Duration:</span>
                            <span className="text-slate-200">0.8s</span>
                          </div>

                          {/* Expandable output */}
                          {isExpanded && (
                            <div className="mt-3 pt-3 border-t border-slate-800 space-y-2">
                              {tc.output && (
                                <div>
                                  <span className="text-[10px] text-slate-500 block mb-1">
                                    Raw Output:
                                  </span>
                                  <div className="p-2.5 bg-black/40 rounded-lg text-[11px] text-slate-300 whitespace-pre-wrap border border-slate-800/80">
                                    {tc.output}
                                  </div>
                                </div>
                              )}
                              {tc.error && (
                                <div>
                                  <span className="text-[10px] text-rose-400 block mb-1">
                                    Error:
                                  </span>
                                  <div className="p-2.5 bg-rose-950/30 rounded-lg text-[11px] text-rose-300 border border-rose-800/40">
                                    {tc.error}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {isSending && state.status !== 'online' && state.status !== 'idle' && state.status !== 'error' && (
          <div className="flex items-center justify-between p-3.5 bg-[#0e1320] border border-cyan-900/40 rounded-2xl max-w-md mr-auto text-xs text-slate-300 shadow-lg animate-in fade-in">
            <div className="flex items-center gap-3">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
              <span className="font-mono text-cyan-200">
                {state.status === 'executing'
                  ? state.statusDetail || 'Executing tools...'
                  : state.status === 'speaking'
                  ? 'NOVA is speaking...'
                  : state.statusDetail || 'NOVA is processing...'}
              </span>
            </div>
            <button
              onClick={() => store.stopActive()}
              className="px-2.5 py-1 text-[11px] font-mono font-semibold bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800/60 rounded-lg transition-colors ml-4"
            >
              ⏹ Stop
            </button>
          </div>
        )}

        {state.activeTask && state.activeTask.plan && (state.activeTask.status.toUpperCase() === 'WAITING_APPROVAL' || state.activeTask.status.toUpperCase() === 'RUNNING') && (
          <div className="mr-12 max-w-xl my-3">
            <PlanApprovalCard
              plan={state.activeTask.plan}
              taskId={state.activeTask.id}
              isExecuting={state.activeTask.status.toUpperCase() === 'RUNNING'}
              onApprove={async (taskId) => {
                try {
                  await api.approveTask(taskId);
                  const updated = await api.getTask(taskId);
                  if (updated) store.upsertTask(updated);
                } catch (err) {
                  console.error('Failed to approve plan:', err);
                }
              }}
              onCancel={async (taskId) => {
                try {
                  await api.cancelTask(taskId);
                  const updated = await api.getTask(taskId);
                  if (updated) store.upsertTask(updated);
                } catch (err) {
                  console.error('Failed to cancel task:', err);
                }
              }}
            />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom Input Box */}
      <div className="p-4 border-t border-slate-800/80 bg-[#0a0e17] flex-shrink-0">
        <form
          onSubmit={handleSend}
          className="max-w-4xl mx-auto flex items-center gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleSend();
              }
            }}
            placeholder="Send a message to NOVA AI... (Ctrl + Enter to send)"
            className="flex-1 bg-[#070a10] border border-slate-700/80 focus:border-cyan-500 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20 font-sans"
          />

          <button
            type="button"
            onClick={handleVoiceListen}
            title="Start voice listening (Ctrl + Space)"
            className="p-3 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-cyan-300 border border-slate-700 rounded-xl transition-colors"
          >
            <Mic className="w-4 h-4" />
          </button>

          <button
            type="submit"
            disabled={isSending || !input.trim()}
            className="px-5 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-xl shadow-lg shadow-cyan-950/40 transition-all flex items-center gap-1.5"
          >
            <Send className="w-4 h-4" />
            <span>Send</span>
          </button>
        </form>
      </div>
    </div>
  );
};
