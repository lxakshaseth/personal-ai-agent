import React, { useState, useEffect } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import { Mic, MicOff, Volume2, Sparkles, AlertTriangle, Play, Radio } from 'lucide-react';

export const VoicePage: React.FC = () => {
  const [agentState, store] = useAgentStore();
  const [isCapturing, setIsCapturing] = useState(false);
  const [ttsInput, setTtsInput] = useState('Hello! I am NOVA, your Windows AI assistant.');
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceResult, setVoiceResult] = useState<string | null>(null);
  const [micStatus, setMicStatus] = useState<'unknown' | 'available' | 'unavailable'>('unknown');

  // Check mic/backend availability on mount
  useEffect(() => {
    const detectMic = async () => {
      try {
        await api.checkHealth();
        // If health passes, mic status comes back when we attempt listen
        setMicStatus('available');
      } catch {
        setMicStatus('unavailable');
      }
    };
    detectMic();
  }, []);

  const handleStartListen = async () => {
    setIsCapturing(true);
    setVoiceResult(null);
    store.setStatus('listening', 'Listening for speech...');

    try {
      const res = await api.triggerListen();
      if (res.transcript) {
        setVoiceResult(`Recognized: "${res.transcript}"\n\nAgent Response:\n${res.response}`);
        store.setStatus('online', 'Ready');
        setMicStatus('available');
      } else if (res.error) {
        const isMicError = res.error.toLowerCase().includes('microphone') || res.error.toLowerCase().includes('mic');
        if (isMicError) setMicStatus('unavailable');
        setVoiceResult(`Notice: ${res.error}`);
        store.setStatus('online', 'Ready');
      }
    } catch (err: any) {
      setVoiceResult(`Voice error: ${err.message}`);
      store.setStatus('error', err.message);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleTestTTS = async () => {
    if (!ttsInput.trim() || isSpeaking) return;
    setIsSpeaking(true);
    try {
      await api.speakText(ttsInput);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSpeaking(false);
    }
  };


  return (
    <div className="p-8 space-y-6 max-w-5xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
          <Radio className="w-5 h-5 text-cyan-400" />
          <span>Voice Control Center</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Hands-free voice recognition, wake-word detection, and text-to-speech output.
        </p>
      </div>

      {/* Main Interactive Mic Station */}
      <div className="bg-gradient-to-b from-[#0f1422] to-[#090d16] border border-slate-800 rounded-2xl p-8 flex flex-col items-center justify-center text-center shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />

        {/* Pulsing Visual Waveform */}
        <div className="h-20 flex items-center justify-center gap-1.5 mb-6">
          {[40, 65, 30, 85, 55, 95, 45, 75, 90, 60, 35, 80, 50].map((h, i) => (
            <div
              key={i}
              className={`w-1.5 rounded-full transition-all duration-300 ${
                isCapturing
                  ? 'bg-cyan-400 animate-pulse'
                  : 'bg-slate-700/60'
              }`}
              style={{
                height: isCapturing ? `${h}%` : '20%',
                animationDelay: `${i * 80}ms`,
              }}
            />
          ))}
        </div>

        {/* Big Mic Trigger Button */}
        <button
          onClick={handleStartListen}
          disabled={isCapturing || micStatus === 'unavailable'}
          title={micStatus === 'unavailable' ? 'No microphone detected. Connect a mic or use the text input.' : 'Click to start listening'}
          className={`w-24 h-24 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 active:scale-95 ${
            isCapturing
              ? 'bg-cyan-500 text-white shadow-cyan-500/50 animate-pulse ring-8 ring-cyan-500/20'
              : micStatus === 'unavailable'
              ? 'bg-slate-800 border-2 border-red-500/50 text-red-400 cursor-not-allowed opacity-70'
              : 'bg-gradient-to-tr from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-cyan-950/60 hover:scale-105'
          }`}
        >
          {micStatus === 'unavailable' ? <MicOff className="w-10 h-10" /> : <Mic className="w-10 h-10" />}
        </button>

        <span className="text-sm font-semibold text-white mt-4">
          {isCapturing
            ? '🎙 Listening... Speak now'
            : micStatus === 'unavailable'
            ? '⚠ No Microphone Detected'
            : 'Click to Speak'}
        </span>
        <span className="text-xs text-slate-400 max-w-sm mt-1">
          {micStatus === 'unavailable'
            ? 'Connect an audio input device or use the text command box on the Dashboard.'
            : 'Microphone captures your phrase on demand and executes commands naturally.'}
        </span>

        {/* No-mic warning badge */}
        {micStatus === 'unavailable' && !isCapturing && (
          <div className="mt-4 flex items-center gap-2 bg-red-950/40 border border-red-800/50 rounded-xl px-4 py-2 text-xs text-red-300">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            <span>No microphone detected. Voice input is unavailable.</span>
          </div>
        )}

        {/* Live Result Box */}
        {voiceResult && (
          <div className="mt-6 w-full max-w-lg bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-left text-xs font-mono text-slate-200 whitespace-pre-wrap animate-in fade-in">
            {voiceResult}
          </div>
        )}
      </div>

      {/* TTS Testing & Settings Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* TTS Test */}
        <div className="bg-[#0a0e17] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-white">Text-to-Speech Preview</h3>
          </div>
          <p className="text-xs text-slate-400">
            Test the active Windows speech synthesizer with custom text.
          </p>

          <textarea
            rows={3}
            value={ttsInput}
            onChange={(e) => setTtsInput(e.target.value)}
            className="w-full bg-[#070a10] border border-slate-700/80 rounded-xl p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500 font-sans"
          />

          <button
            onClick={handleTestTTS}
            disabled={isSpeaking || !ttsInput.trim()}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-xl transition-colors flex items-center gap-2"
          >
            <Play className="w-3.5 h-3.5" />
            <span>{isSpeaking ? 'Speaking...' : 'Play Audio'}</span>
          </button>
        </div>

        {/* Configuration Snapshot */}
        <div className="bg-[#0a0e17] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Voice Pipeline Info</h3>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Speech-to-Text (STT)</span>
              <span className="text-cyan-300 font-mono font-semibold">Groq Whisper (whisper-large-v3-turbo)</span>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Text-to-Speech (TTS)</span>
              <span className="text-purple-300 font-mono font-semibold">System SAPI5 (Windows Native)</span>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Wake Word</span>
              <span className="text-emerald-300 font-mono font-semibold">"Jarvis"</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-slate-400">Recording Mode</span>
              <span className="text-slate-200">On-demand safe phrase capture</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
