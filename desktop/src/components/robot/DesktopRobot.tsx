import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  Send,
  Square,
  Maximize2,
  Volume2,
  VolumeX,
  Minus,
  X,
  Sparkles,
  ShieldAlert,
  Check,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import { useAgentStore } from '../../stores/agentStore';
import { api } from '../../services/api';
import { robotSounds } from './robotSounds';

interface DesktopRobotProps {
  onExpandDashboard: () => void;
}

export const DesktopRobot: React.FC<DesktopRobotProps> = ({ onExpandDashboard }) => {
  const [state, store] = useAgentStore();
  const [inputText, setInputText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isMuted, setIsMuted] = useState(robotSounds.isMuted());
  const [isHappy, setIsHappy] = useState(false);
  const [showInput, setShowInput] = useState(true);
  const [customQuote, setCustomQuote] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const isOffline = !state.isConnected || state.status === 'offline';
  const isListening = state.status === 'listening';
  const isThinking = ['thinking', 'planning'].includes(state.status);
  const isExecuting = ['executing', 'running'].includes(state.status) || Boolean(state.activeTask);
  const isWaitingConfirmation = state.status === 'waiting_confirmation' || state.pendingConfirmations.length > 0;
  const isSpeaking = state.status === 'speaking';

  // Play sound when status changes
  useEffect(() => {
    if (isListening) {
      robotSounds.playWake();
    } else if (isWaitingConfirmation) {
      robotSounds.playAlert();
    }
  }, [state.status, isListening, isWaitingConfirmation]);

  // Petting / clicking the robot avatar
  const handlePetRobot = () => {
    robotSounds.playHappyChirp();
    setIsHappy(true);
    const quotes = [
      'Ready for action, Commander!',
      'All systems optimal and online!',
      'How can Nova assist you today?',
      'Always at your service!',
      'Press Ctrl+Space anytime to speak!',
    ];
    setCustomQuote(quotes[Math.floor(Math.random() * quotes.length)]);
    setTimeout(() => {
      setIsHappy(false);
      setCustomQuote(null);
    }, 4000);
  };

  // Toggle voice listening
  const handleToggleListen = async () => {
    robotSounds.playBlip();
    try {
      store.setStatus('listening', 'Listening for speech command...');
      await api.triggerListen();
    } catch (err: any) {
      console.error('Failed to trigger voice listening:', err);
      store.setStatus('error', err.message || 'Voice trigger failed');
    }
  };

  // Stop active operation
  const handleStop = async () => {
    robotSounds.playStop();
    try {
      await store.stopActive();
    } catch (err) {
      console.error('Failed to stop:', err);
    }
  };

  // Submit text command
  const handleSubmitCommand = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const prompt = inputText.trim();
    if (!prompt || isSubmitting) return;

    robotSounds.playBlip();
    setIsSubmitting(true);
    setInputText('');

    // Add user message to store
    store.addMessage({
      id: 'msg_' + Date.now(),
      sender: 'user',
      text: prompt,
      timestamp: Date.now(),
    });

    try {
      store.setStatus('thinking', `Processing: "${prompt.slice(0, 30)}..."`);
      const res = await api.runCommand(prompt);
      if (res && res.response) {
        store.addMessage({
          id: 'resp_' + Date.now(),
          sender: 'agent',
          text: res.response,
          timestamp: Date.now(),
        });
        robotSounds.playSuccess();
        store.setStatus('online', 'Ready');
      }
    } catch (err: any) {
      console.error('Command execution failed:', err);
      store.addMessage({
        id: 'err_' + Date.now(),
        sender: 'system',
        text: `Error: ${err.message || 'Execution failed'}`,
        timestamp: Date.now(),
      });
      store.setStatus('error', 'Execution error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Approval handlers for pending confirmation
  const handleConfirm = async (ticketId: string, approved: boolean) => {
    robotSounds.playBlip();
    try {
      await api.respondConfirmation(ticketId, approved);
      store.resolveConfirmation(ticketId);
    } catch (err) {
      console.error('Confirmation response failed:', err);
    }
  };

  // Sound mute toggle
  const toggleMute = () => {
    const next = robotSounds.toggleMute();
    setIsMuted(next);
  };

  // Window control helpers
  const handleMinimize = () => {
    robotSounds.playBlip();
    window.desktopAPI?.minimizeWindow?.();
  };

  const handleClose = () => {
    robotSounds.playBlip();
    window.desktopAPI?.closeWindow?.();
  };

  // Determine speech bubble text
  const latestMessage = state.messages[state.messages.length - 1]?.text;
  const bubbleText =
    customQuote ||
    (isWaitingConfirmation
      ? `Action requires approval: ${state.pendingConfirmations[0]?.tool_name || 'System Command'}`
      : isListening
      ? 'Listening for voice command...'
      : isThinking
      ? 'Analyzing your request...'
      : isExecuting
      ? state.statusDetail || 'Executing task...'
      : isOffline
      ? 'Backend offline (localhost:8000)'
      : latestMessage || 'Nova AI ready. Click mic or type below!');

  return (
    <div className="w-full h-full flex flex-col items-center justify-between p-2 select-none">
      {/* ── Top Window Bar (Draggable) ─────────────────────────── */}
      <div className="w-full drag-region flex items-center justify-between px-3 py-1.5 rounded-full bg-slate-900/80 backdrop-blur-md border border-slate-800/80 shadow-lg mb-2">
        {/* Status Pill */}
        <div className="flex items-center gap-1.5 no-drag">
          <span
            className={`w-2 h-2 rounded-full ${
              isOffline
                ? 'bg-rose-500'
                : isListening
                ? 'bg-cyan-400 animate-ping'
                : isThinking || isExecuting
                ? 'bg-amber-400 animate-pulse'
                : 'bg-emerald-400'
            }`}
          />
          <span className="text-[10px] font-mono font-semibold tracking-wider text-slate-300 uppercase">
            {isOffline ? 'OFFLINE' : isListening ? 'LISTENING' : isThinking ? 'THINKING' : isExecuting ? 'WORKING' : 'NOVA BOT'}
          </span>
        </div>

        {/* Quick controls */}
        <div className="flex items-center gap-1 no-drag">
          <button
            onClick={toggleMute}
            title={isMuted ? 'Unmute SFX' : 'Mute SFX'}
            className="p-1 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/70 transition"
          >
            {isMuted ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5 text-cyan-400" />}
          </button>
          <button
            onClick={onExpandDashboard}
            title="Expand to Full Control Center (Ctrl+Shift+R)"
            className="p-1 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/70 transition"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleMinimize}
            title="Minimize"
            className="p-1 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-slate-800/70 transition"
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleClose}
            title="Close"
            className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800/70 transition"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── Dynamic Speech Bubble ────────────────────────────── */}
      <div className="w-full max-w-[340px] mb-2 px-1 transition-all duration-300">
        <div className="relative group bg-slate-900/90 backdrop-blur-xl border border-cyan-500/30 rounded-2xl p-3 shadow-xl shadow-cyan-950/20 text-xs text-slate-200">
          {/* Top highlight indicator */}
          <div className="flex items-center justify-between mb-1 text-[10px] text-cyan-400 font-mono">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-cyan-400" />
              <span>NOVA CORE</span>
            </span>
            {isOffline && (
              <button
                onClick={() => store.reconnect()}
                className="flex items-center gap-1 text-rose-400 hover:underline"
              >
                <RefreshCw className="w-2.5 h-2.5" /> Reconnect
              </button>
            )}
          </div>

          {/* Bubble content */}
          <p className="line-clamp-3 leading-relaxed text-slate-200 font-sans">
            {bubbleText}
          </p>

          {/* Pending Confirmation Controls right inside the speech bubble */}
          {isWaitingConfirmation && state.pendingConfirmations[0] && (
            <div className="mt-2 pt-2 border-t border-amber-500/30 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-amber-400 text-[10px] font-semibold truncate max-w-[140px]">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="truncate">{state.pendingConfirmations[0].reason || 'High Risk Action'}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleConfirm(state.pendingConfirmations[0].ticket_id, false)}
                  className="px-2 py-1 rounded-lg bg-rose-950/80 hover:bg-rose-900 border border-rose-700/60 text-rose-200 text-[10px] font-bold flex items-center gap-1"
                >
                  <X className="w-3 h-3" /> Deny
                </button>
                <button
                  onClick={() => handleConfirm(state.pendingConfirmations[0].ticket_id, true)}
                  className="px-2 py-1 rounded-lg bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700/60 text-emerald-200 text-[10px] font-bold flex items-center gap-1"
                >
                  <Check className="w-3 h-3" /> Approve
                </button>
              </div>
            </div>
          )}

          {/* Speech bubble bottom pointer / arrow */}
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[8px] border-t-slate-900/90" />
        </div>
      </div>

      {/* ── Living Robot Avatar ──────────────────────────────── */}
      <div className="relative flex flex-col items-center justify-center my-auto cursor-pointer no-drag select-none group" onClick={handlePetRobot}>
        {/* Floating Robot Body */}
        <div className="relative animate-robot-hover">
          {/* Pulsing Acoustic Glow Ring when Listening / Speaking */}
          {(isListening || isSpeaking) && (
            <div className="absolute -inset-4 rounded-full bg-cyan-500/20 blur-xl animate-ping" />
          )}

          {/* Robot Head Outer Shell */}
          <div
            className={`w-36 h-32 rounded-[2.5rem] bg-gradient-to-b from-slate-800 via-slate-900 to-[#0b101b] p-2 border-2 transition-all duration-300 shadow-2xl ${
              isOffline
                ? 'border-rose-700/40 shadow-rose-950/30'
                : isListening
                ? 'border-cyan-400 shadow-cyan-500/40 animate-cyber-pulse'
                : isThinking || isExecuting
                ? 'border-amber-400/80 shadow-amber-500/30'
                : 'border-cyan-500/40 shadow-cyan-950/50 hover:border-cyan-400'
            }`}
          >
            {/* Robot Antenna */}
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 flex flex-col items-center">
              <div
                className={`w-3.5 h-3.5 rounded-full shadow-lg transition-all ${
                  isOffline
                    ? 'bg-rose-500 shadow-rose-500/50'
                    : isListening
                    ? 'bg-cyan-300 shadow-cyan-400/80 animate-ping'
                    : isThinking || isExecuting
                    ? 'bg-amber-400 shadow-amber-400/80 animate-pulse'
                    : 'bg-cyan-400 shadow-cyan-400/50'
                }`}
              />
              <div className="w-1 h-3 bg-slate-700 rounded-b" />
            </div>

            {/* Cyber Visor / LED Screen */}
            <div className="w-full h-full rounded-[2rem] bg-black/90 p-2.5 flex flex-col items-center justify-center relative overflow-hidden border border-slate-800/80">
              {/* Scanline Grid Background */}
              <div
                className="absolute inset-0 opacity-15 pointer-events-none"
                style={{
                  backgroundImage:
                    'linear-gradient(rgba(6, 182, 212, 0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(6, 182, 212, 0.2) 1px, transparent 1px)',
                  backgroundSize: '8px 8px',
                }}
              />

              {/* Visor Scanning Beam (Active when executing) */}
              {isExecuting && (
                <div className="absolute inset-0 bg-gradient-to-b from-transparent via-cyan-400/20 to-transparent animate-radar-sweep pointer-events-none" />
              )}

              {/* Digital LED Eyes */}
              <div className="flex items-center justify-center gap-4 mb-2 z-10">
                {/* Left Eye */}
                <div className="relative flex items-center justify-center">
                  {isHappy ? (
                    // Happy Eye ^
                    <span className="text-cyan-300 text-2xl font-bold">^</span>
                  ) : isThinking ? (
                    // Spinning Matrix Eye
                    <div className="w-6 h-6 rounded-full border-2 border-dashed border-amber-400 animate-cyber-ring flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-amber-400 shadow-lg shadow-amber-400" />
                    </div>
                  ) : isOffline ? (
                    // Offline Eye x
                    <span className="text-rose-500 text-xl font-bold">✕</span>
                  ) : (
                    // Standard / Listening Cyber Eye
                    <div
                      className={`rounded-full transition-all duration-300 animate-eye-blink shadow-lg ${
                        isListening
                          ? 'w-7 h-7 bg-cyan-300 shadow-cyan-400/90'
                          : 'w-6 h-4 bg-cyan-400 shadow-cyan-400/70'
                      }`}
                    />
                  )}
                </div>

                {/* Right Eye */}
                <div className="relative flex items-center justify-center">
                  {isHappy ? (
                    // Happy Eye ^
                    <span className="text-cyan-300 text-2xl font-bold">^</span>
                  ) : isThinking ? (
                    // Spinning Matrix Eye
                    <div className="w-6 h-6 rounded-full border-2 border-dashed border-amber-400 animate-cyber-ring flex items-center justify-center">
                      <div className="w-2 h-2 rounded-full bg-amber-400 shadow-lg shadow-amber-400" />
                    </div>
                  ) : isOffline ? (
                    // Offline Eye x
                    <span className="text-rose-500 text-xl font-bold">✕</span>
                  ) : (
                    // Standard / Listening Cyber Eye
                    <div
                      className={`rounded-full transition-all duration-300 animate-eye-blink shadow-lg ${
                        isListening
                          ? 'w-7 h-7 bg-cyan-300 shadow-cyan-400/90'
                          : 'w-6 h-4 bg-cyan-400 shadow-cyan-400/70'
                      }`}
                    />
                  )}
                </div>
              </div>

              {/* Digital Equalizer Mouth (Speaks / reacts) */}
              <div className="flex items-center gap-1 z-10 h-3">
                {isSpeaking ? (
                  // Animated audio wave bars
                  [1, 2, 3, 4, 5].map((i) => (
                    <div
                      key={i}
                      className="w-1 bg-cyan-400 rounded-full animate-pulse"
                      style={{
                        height: `${8 + (i % 3) * 5}px`,
                        animationDuration: `${0.2 + i * 0.1}s`,
                      }}
                    />
                  ))
                ) : isHappy ? (
                  // Smiling mouth
                  <div className="w-6 h-2 border-b-2 border-cyan-400 rounded-full" />
                ) : isOffline ? (
                  <div className="w-4 h-0.5 bg-rose-500 rounded" />
                ) : (
                  // Idle subtle dot
                  <div className="w-3 h-1 bg-cyan-500/50 rounded-full" />
                )}
              </div>
            </div>
          </div>

          {/* Robot Cyber Ears / Headphone Accents */}
          <div className="absolute -left-2 top-10 w-2.5 h-8 bg-cyan-600/80 rounded-l-full shadow-md" />
          <div className="absolute -right-2 top-10 w-2.5 h-8 bg-cyan-600/80 rounded-r-full shadow-md" />
        </div>

        {/* Ambient Hover Shadow */}
        <div className="w-24 h-2.5 rounded-full bg-cyan-500/20 blur-sm mt-3 animate-robot-shadow" />
      </div>

      {/* ── Slide-Out Quick Command Bar & Controls ───────────── */}
      <div className="w-full max-w-[350px] no-drag">
        {showInput && (
          <form onSubmit={handleSubmitCommand} className="relative mb-2">
            <input
              ref={inputRef}
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={isListening ? 'Listening...' : 'Type a command or chat...'}
              disabled={isSubmitting || isListening}
              className="w-full bg-slate-900/90 backdrop-blur-md border border-slate-800 focus:border-cyan-500/70 rounded-xl py-2 pl-3 pr-9 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 shadow-lg"
            />
            <button
              type="submit"
              disabled={!inputText.trim() || isSubmitting}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 rounded-lg bg-cyan-600/80 hover:bg-cyan-500 text-white disabled:opacity-30 disabled:hover:bg-cyan-600/80 transition shadow"
            >
              <Send className="w-3 h-3" />
            </button>
          </form>
        )}

        {/* Action Button Dock */}
        <div className="flex items-center justify-between gap-1.5 px-2 py-1.5 rounded-2xl bg-slate-900/80 backdrop-blur-md border border-slate-800/80 shadow-lg">
          {/* 1. Voice Listen Button */}
          <button
            onClick={handleToggleListen}
            title="Listen Voice Command (Ctrl+Space)"
            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-xl text-xs font-semibold transition-all ${
              isListening
                ? 'bg-cyan-500 text-slate-950 shadow-lg shadow-cyan-500/30 animate-pulse'
                : 'bg-slate-800/80 hover:bg-cyan-950/50 text-cyan-300 hover:border-cyan-500/40 border border-slate-700/50'
            }`}
          >
            <Mic className="w-3.5 h-3.5" />
            <span>{isListening ? 'Listening' : 'Speak'}</span>
          </button>

          {/* 2. Emergency Stop / Halt Button (active when executing or task active) */}
          {isExecuting && (
            <button
              onClick={handleStop}
              title="Stop Execution (Esc)"
              className="flex items-center justify-center gap-1 py-1.5 px-2.5 rounded-xl bg-rose-950/80 hover:bg-rose-900 border border-rose-700/60 text-rose-200 text-xs font-semibold shadow-lg shadow-rose-950/30"
            >
              <Square className="w-3.5 h-3.5 fill-rose-300" />
              <span>Stop</span>
            </button>
          )}

          {/* 3. Expand to Full Control Center */}
          <button
            onClick={onExpandDashboard}
            title="Open Full Control Center"
            className="flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold shadow-md shadow-blue-900/30"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            <span>Dashboard</span>
          </button>
        </div>
      </div>
    </div>
  );
};
