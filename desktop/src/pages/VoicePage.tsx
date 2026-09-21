import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { api } from '../services/api';
import {
  Mic,
  MicOff,
  Volume2,
  Sparkles,
  AlertTriangle,
  Play,
  Radio,
  Square,
  Zap,
  Clock,
  CheckCircle2,
  Sliders,
  SendHorizontal,
  Activity,
  VolumeX,
} from 'lucide-react';
import {
  browserVoice,
  streamingVoiceClient,
  StreamingVoiceEvents,
} from '../services/voiceService';

interface ConversationItem {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  timestamp: string;
}

export const VoicePage: React.FC = () => {
  const [agentState, store] = useAgentStore();
  const [isInSession, setIsInSession] = useState(false);
  const [liveSpeech, setLiveSpeech] = useState('');
  const [countdown, setCountdown] = useState<number | null>(null);
  const [activeStatus, setActiveStatus] = useState<
    'idle' | 'listening' | 'waiting_silence' | 'executing' | 'speaking'
  >('idle');
  const [conversation, setConversation] = useState<ConversationItem[]>([]);
  const [ttsInput, setTtsInput] = useState('Hello! I am NOVA, your Windows AI assistant.');
  const [isSpeakingTest, setIsSpeakingTest] = useState(false);
  const [micStatus, setMicStatus] = useState<'unknown' | 'available' | 'unavailable'>('unknown');
  const [silenceDelay, setSilenceDelay] = useState<number>(1200); // 1.2s fast default
  const [streamingText, setStreamingText] = useState('');
  const [latencyMetrics, setLatencyMetrics] = useState<{ [key: string]: number } | null>(null);

  const conversationEndRef = useRef<HTMLDivElement>(null);
  const streamingTextRef = useRef<string>('');
  const playbackTimeoutRef = useRef<any>(null);

  useEffect(() => {
    if (browserVoice.isSupported()) {
      setMicStatus('available');
    } else {
      const detectMic = async () => {
        try {
          await api.checkHealth();
          setMicStatus('available');
        } catch {
          setMicStatus('unavailable');
        }
      };
      detectMic();
    }
  }, []);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversation, liveSpeech, streamingText]);

  // Barge-in: immediately cancel audio playback and LLM stream
  const handleBargeIn = useCallback(() => {
    streamingVoiceClient.interrupt();
    browserVoice.stopSpeaking();
    if (playbackTimeoutRef.current) {
      clearTimeout(playbackTimeoutRef.current);
      playbackTimeoutRef.current = null;
    }
    const currentPending = streamingTextRef.current.trim();
    if (currentPending) {
      const now = new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
      setConversation((prev) => [
        ...prev,
        { id: 'a_' + Date.now(), sender: 'agent', text: currentPending + ' [Interrupted]', timestamp: now },
      ]);
    }
    setStreamingText('');
    streamingTextRef.current = '';
    setActiveStatus('listening');
    store.setStatus('listening', 'Continuous Listening Active');
  }, [store]);

  const commitStreamingReply = useCallback(() => {
    if (playbackTimeoutRef.current) {
      clearTimeout(playbackTimeoutRef.current);
      playbackTimeoutRef.current = null;
    }
    const finalReply = streamingTextRef.current.trim();
    if (finalReply) {
      const now = new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
      setConversation((prev) => [
        ...prev,
        { id: 'a_' + Date.now(), sender: 'agent', text: finalReply, timestamp: now },
      ]);
      setStreamingText('');
      streamingTextRef.current = '';
    }
    setActiveStatus('listening');
    store.setStatus('listening', 'Continuous Listening Active');
  }, [store]);

  const handleStopSession = useCallback(() => {
    streamingVoiceClient.interrupt();
    streamingVoiceClient.disconnect();
    browserVoice.stopAll();
    if (playbackTimeoutRef.current) {
      clearTimeout(playbackTimeoutRef.current);
      playbackTimeoutRef.current = null;
    }
    setIsInSession(false);
    setActiveStatus('idle');
    setLiveSpeech('');
    setStreamingText('');
    streamingTextRef.current = '';
    setCountdown(null);
    store.setStatus('online', 'Ready');
    api.cancelActiveTask().catch(() => {});
  }, [store]);

  const handleExecuteNow = () => {
    browserVoice.forceFlushNow();
  };

  // Keyboard shortcuts: Enter = execute immediately; Escape = barge-in interruption
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && isInSession && (activeStatus === 'listening' || activeStatus === 'waiting_silence')) {
        e.preventDefault();
        handleExecuteNow();
      } else if (e.key === 'Escape' && isInSession && activeStatus === 'speaking') {
        e.preventDefault();
        handleBargeIn();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isInSession, activeStatus, handleBargeIn]);

  const handleSetSilenceDelay = (delayMs: number) => {
    setSilenceDelay(delayMs);
    browserVoice.setSilenceWaitMs(delayMs);
  };

  const setupStreamingClient = useCallback(() => {
    const callbacks: StreamingVoiceEvents = {
      onConnectionReady: () => {
        console.log('[StreamingVoiceClient] Connected to /ws/voice');
      },
      onLlmStart: () => {
        setActiveStatus('executing');
        store.setStatus('executing', 'NOVA thinking (streaming)...');
        setStreamingText('');
        streamingTextRef.current = '';
      },
      onLlmChunk: (token: string) => {
        streamingTextRef.current += token;
        setStreamingText(streamingTextRef.current);
      },
      onTtsStart: (_idx: number, _text: string) => {
        setActiveStatus('speaking');
        store.setStatus('speaking', 'NOVA speaking...');
      },
      onAssistantDone: (metrics: { [key: string]: number }) => {
        setLatencyMetrics(metrics);
        // Safety timeout fallback if browser audio finishes without triggering onPlaybackComplete
        if (playbackTimeoutRef.current) clearTimeout(playbackTimeoutRef.current);
        playbackTimeoutRef.current = setTimeout(() => {
          commitStreamingReply();
        }, 3000);
      },
      onPlaybackComplete: () => {
        commitStreamingReply();
      },
      onInterrupted: () => {
        handleBargeIn();
      },
      onError: (errMsg: string) => {
        console.warn('[StreamingVoiceClient] Error:', errMsg);
      },
    };

    streamingVoiceClient.connect(callbacks);
  }, [store, commitStreamingReply, handleBargeIn]);

  const handleToggleSession = () => {
    if (isInSession) {
      handleStopSession();
      return;
    }

    if (browserVoice.isSupported()) {
      setIsInSession(true);
      setActiveStatus('listening');
      store.setStatus('listening', 'Continuous Listening Active');

      // Connect to the high-speed Streaming WebSocket pipeline
      setupStreamingClient();

      browserVoice.startContinuousSession(
        {
          onStart: () => {
            setIsInSession(true);
            setActiveStatus('listening');
            setCountdown(null);
          },
          onInterim: (text) => {
            setLiveSpeech(text);

            // Instant Barge-In: If user begins speaking while assistant is speaking/executing,
            // immediately interrupt ongoing audio!
            if (activeStatus === 'speaking' || activeStatus === 'executing') {
              handleBargeIn();
            }
          },
          onCountdown: (sec) => {
            setCountdown(sec);
            if (sec !== null && sec > 0) {
              setActiveStatus('waiting_silence');
              store.setStatus('listening', `Answering in ${sec}s...`);
            } else {
              setActiveStatus('listening');
            }
          },
          onPhraseReady: async (phrase, isEnd) => {
            setLiveSpeech('');
            setCountdown(null);

            const now = new Date().toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
            });
            setConversation((prev) => [
              ...prev,
              { id: 'u_' + Date.now(), sender: 'user', text: phrase, timestamp: now },
            ]);

            if (isEnd) {
              setConversation((prev) => [
                ...prev,
                {
                  id: 'a_' + Date.now(),
                  sender: 'agent',
                  text: 'Goodbye! Voice session ended.',
                  timestamp: new Date().toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  }),
                },
              ]);
              handleStopSession();
              return;
            }

            // Follow user command with real-time streaming pipeline
            setActiveStatus('executing');
            store.setStatus('executing', `Processing: "${phrase}"...`);
            setStreamingText('');
            streamingTextRef.current = '';

            if (streamingVoiceClient.isReady) {
              streamingVoiceClient.sendPrompt(phrase);
            } else {
              // Ensure connection and send
              setupStreamingClient();
              // Short delay to let socket open if needed
              setTimeout(() => {
                streamingVoiceClient.sendPrompt(phrase);
              }, 100);
            }
          },
          onError: (errMsg) => {
            console.warn('Voice session notice:', errMsg);
          },
          onSessionEnd: () => {
            setIsInSession(false);
            setActiveStatus('idle');
            setCountdown(null);
            setLiveSpeech('');
            store.setStatus('online', 'Ready');
          },
        },
        silenceDelay
      );
    } else {
      runBackendFallback();
    }
  };

  const runBackendFallback = async () => {
    setIsInSession(true);
    setActiveStatus('listening');
    store.setStatus('listening', 'Listening for speech...');

    try {
      const res = await api.triggerListen();
      if (res.transcript) {
        const now = new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        });
        setConversation((prev) => [
          ...prev,
          { id: 'u_' + Date.now(), sender: 'user', text: res.transcript!, timestamp: now },
        ]);

        if (res.response) {
          setConversation((prev) => [
            ...prev,
            {
              id: 'a_' + Date.now(),
              sender: 'agent',
              text: res.response!,
              timestamp: new Date().toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
              }),
            },
          ]);
          setActiveStatus('speaking');
          await browserVoice.speak(res.response);
        }
      }
    } catch (err: any) {
      console.warn('Backend listen error:', err);
    } finally {
      setIsInSession(false);
      setActiveStatus('idle');
      store.setStatus('online', 'Ready');
    }
  };

  const handleTestTTS = async () => {
    if (!ttsInput.trim() || isSpeakingTest) return;
    setIsSpeakingTest(true);
    try {
      if (browserVoice.isSupported()) {
        await browserVoice.speak(ttsInput);
      } else {
        await api.speakText(ttsInput);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSpeakingTest(false);
    }
  };

  const QUICK_PROMPTS = [
    'What time is it right now?',
    'Open YouTube in Chrome',
    'Take a screenshot',
    'Open Notepad',
    'Check CPU usage',
    'Say "End" to exit',
  ];

  return (
    <div className="p-8 space-y-6 max-w-5xl mx-auto overflow-y-auto h-[calc(100vh-4rem)]">
      {/* Header & Speed Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Radio className="w-5 h-5 text-cyan-400" />
            <span>Continuous Voice Control</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Ultra-low-latency conversational voice engine. Speaks back in &lt;1s and keeps listening continuously.
          </p>
        </div>

        {/* Speed Cadence Selector */}
        <div className="flex items-center gap-1.5 p-1 bg-slate-900/90 border border-slate-800 rounded-xl shadow-inner">
          <span className="text-[10px] text-slate-400 px-2 font-medium flex items-center gap-1">
            <Sliders className="w-3 h-3 text-cyan-400" />
            <span>Cadence:</span>
          </span>
          <button
            onClick={() => handleSetSilenceDelay(800)}
            className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-all ${
              silenceDelay === 800
                ? 'bg-cyan-500 text-white font-bold shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            ⚡ Turbo (0.8s)
          </button>
          <button
            onClick={() => handleSetSilenceDelay(1200)}
            className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-all ${
              silenceDelay === 1200
                ? 'bg-cyan-500 text-white font-bold shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            🚀 Fast (1.2s)
          </button>
          <button
            onClick={() => handleSetSilenceDelay(3000)}
            className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-all ${
              silenceDelay === 3000
                ? 'bg-cyan-500 text-white font-bold shadow-md'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            ⏱️ Relaxed (3s)
          </button>
        </div>
      </div>

      {/* Main Interactive Mic Station */}
      <div className="bg-gradient-to-b from-[#0f1422] to-[#090d16] border border-slate-800 rounded-2xl p-8 flex flex-col items-center justify-center text-center shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 inset-x-0 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />

        {/* Dynamic Waveform Visualizer */}
        <div className="h-20 flex items-center justify-center gap-1.5 mb-6">
          {[40, 65, 30, 85, 55, 95, 45, 75, 90, 60, 35, 80, 50].map((h, i) => (
            <div
              key={i}
              className={`w-1.5 rounded-full transition-all duration-300 ${
                activeStatus === 'listening'
                  ? 'bg-cyan-400 animate-pulse'
                  : activeStatus === 'waiting_silence'
                  ? 'bg-amber-400 animate-bounce'
                  : activeStatus === 'executing'
                  ? 'bg-purple-400 animate-pulse'
                  : activeStatus === 'speaking'
                  ? 'bg-emerald-400 animate-pulse'
                  : 'bg-slate-700/60'
              }`}
              style={{
                height: isInSession ? `${h}%` : '20%',
                animationDelay: `${i * 80}ms`,
              }}
            />
          ))}
        </div>

        {/* Big Mic Trigger / Stop Button */}
        <div className="flex items-center gap-4">
          <button
            onClick={handleToggleSession}
            disabled={micStatus === 'unavailable'}
            title={
              micStatus === 'unavailable'
                ? 'No microphone detected.'
                : isInSession
                ? 'Click to end session'
                : 'Click to start continuous conversation'
            }
            className={`w-24 h-24 rounded-full flex items-center justify-center shadow-2xl transition-all duration-300 active:scale-95 ${
              isInSession
                ? 'bg-red-500 hover:bg-red-600 text-white shadow-red-500/50 ring-8 ring-red-500/20'
                : micStatus === 'unavailable'
                ? 'bg-slate-800 border-2 border-red-500/50 text-red-400 cursor-not-allowed opacity-70'
                : 'bg-gradient-to-tr from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white shadow-cyan-950/60 hover:scale-105'
            }`}
          >
            {micStatus === 'unavailable' ? (
              <MicOff className="w-10 h-10" />
            ) : isInSession ? (
              <Square className="w-10 h-10 fill-current" />
            ) : (
              <Mic className="w-10 h-10" />
            )}
          </button>
        </div>

        {/* Status Line */}
        <span className="text-sm font-semibold text-white mt-4 flex items-center gap-2">
          {activeStatus === 'waiting_silence' && countdown !== null ? (
            <span className="text-amber-300 flex items-center gap-1.5">
              <Clock className="w-4 h-4 animate-spin" />
              <span>Answering in {countdown}s... (Keep talking to add more)</span>
            </span>
          ) : activeStatus === 'listening' ? (
            <span className="text-cyan-300">🎙 Listening... Speak your command</span>
          ) : activeStatus === 'executing' ? (
            <span className="text-purple-300 flex items-center gap-1.5">
              <Activity className="w-4 h-4 animate-spin" />
              <span>Generating response (streaming tokens)...</span>
            </span>
          ) : activeStatus === 'speaking' ? (
            <span className="text-emerald-300 flex items-center gap-1.5">
              <Volume2 className="w-4 h-4 animate-pulse" />
              <span>NOVA is speaking response...</span>
            </span>
          ) : micStatus === 'unavailable' ? (
            <span className="text-red-400">⚠ No Microphone Detected</span>
          ) : (
            <span>Click to Start Continuous Conversation</span>
          )}
        </span>

        {/* Live Speaking Preview & Execute Now Button */}
        {liveSpeech && (
          <div className="mt-5 w-full max-w-lg flex flex-col items-center gap-2 animate-in fade-in">
            <div className="w-full bg-slate-900/95 border border-cyan-500/40 rounded-xl p-3.5 text-left text-xs font-mono text-cyan-200 whitespace-pre-wrap shadow-xl">
              <span className="text-cyan-400 font-bold block mb-1">Hearing you:</span>
              "{liveSpeech}"
            </div>

            {/* Instant Action Button */}
            <button
              onClick={handleExecuteNow}
              className="px-4 py-1.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs rounded-xl shadow-lg flex items-center gap-1.5 transition-transform hover:scale-105"
            >
              <Zap className="w-3.5 h-3.5 fill-current" />
              <span>Done Speaking — Execute Now (Enter ↵)</span>
            </button>
          </div>
        )}

        {/* Real-time Streaming Response Card */}
        {streamingText && (
          <div className="mt-4 w-full max-w-lg bg-slate-900/95 border border-emerald-500/50 rounded-xl p-4 text-left shadow-2xl animate-in fade-in">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-emerald-400 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span>NOVA Speaking (Real-time Stream)</span>
              </span>
              <button
                onClick={handleBargeIn}
                className="text-[10px] bg-red-950/80 hover:bg-red-900 border border-red-700 text-red-300 px-2.5 py-1 rounded-lg flex items-center gap-1 transition-all shadow hover:scale-105"
                title="Interrupt assistant speech (or press Escape)"
              >
                <Square className="w-2.5 h-2.5 fill-current" />
                <span>Barge-in / Stop (Esc)</span>
              </button>
            </div>
            <p className="text-xs text-slate-100 font-sans leading-relaxed whitespace-pre-wrap">
              {streamingText}
            </p>
          </div>
        )}

        {/* Live TTFA Latency Badge */}
        {latencyMetrics && latencyMetrics.time_to_first_audio_ms !== undefined && (
          <div className="mt-3 flex flex-wrap items-center justify-center gap-2 text-[11px] font-mono px-3.5 py-1.5 bg-cyan-950/60 border border-cyan-800/60 rounded-full text-cyan-300 shadow-inner">
            <span className="flex items-center gap-1 text-amber-300 font-bold">
              <Zap className="w-3.5 h-3.5 fill-current" />
              <span>TTFA: {latencyMetrics.time_to_first_audio_ms.toFixed(0)}ms</span>
            </span>
            <span className="text-slate-600">•</span>
            {latencyMetrics.llm_first_token_ms !== undefined && (
              <span>LLM First Token: {latencyMetrics.llm_first_token_ms.toFixed(0)}ms</span>
            )}
            <span className="text-slate-600">•</span>
            {latencyMetrics.tts_first_audio_ms !== undefined && (
              <span>TTS Audio: {latencyMetrics.tts_first_audio_ms.toFixed(0)}ms</span>
            )}
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400 font-medium">⚡ Real-time Overlapped</span>
          </div>
        )}

        <span className="text-xs text-slate-400 max-w-md mt-3">
          {isInSession
            ? 'Real-time conversation active. Speak freely — assistant responds in <1s. Say "End" to stop, or speak anytime to interrupt.'
            : 'Start session to converse hands-free without clicking again. Responses stream back in <1s.'}
        </span>

        {/* Quick Voice Prompt Chips */}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2 max-w-xl">
          <span className="text-[10px] uppercase font-semibold text-slate-500 tracking-wider w-full mb-1">
            Try saying:
          </span>
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => {
                if (!isInSession) handleToggleSession();
              }}
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-white transition-all flex items-center gap-1.5"
            >
              <Zap className="w-3 h-3 text-cyan-400" />
              <span>{prompt}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Real-Time Continuous Conversation Log */}
      {conversation.length > 0 && (
        <div className="bg-[#0a0e17] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Live Conversation Log</span>
            </h3>
            <span className="text-[10px] text-slate-500">{conversation.length} exchanges</span>
          </div>

          <div className="space-y-3 max-h-60 overflow-y-auto pr-2">
            {conversation.map((item) => (
              <div
                key={item.id}
                className={`p-3 rounded-xl text-xs ${
                  item.sender === 'user'
                    ? 'bg-cyan-950/40 border border-cyan-800/40 text-cyan-100 ml-8'
                    : 'bg-slate-900 border border-slate-800 text-slate-200 mr-8'
                }`}
              >
                <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                  <span className="font-semibold uppercase text-cyan-400">
                    {item.sender === 'user' ? 'You' : 'NOVA'}
                  </span>
                  <span>{item.timestamp}</span>
                </div>
                <p className="whitespace-pre-wrap font-sans leading-relaxed">{item.text}</p>
              </div>
            ))}
            <div ref={conversationEndRef} />
          </div>
        </div>
      )}

      {/* TTS Testing & Voice Pipeline Snapshot Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* TTS Preview */}
        <div className="bg-[#0a0e17] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-purple-400" />
            <h3 className="text-sm font-semibold text-white">Speech Synthesis Test</h3>
          </div>
          <p className="text-xs text-slate-400">
            Test the instant speech synthesizer with custom text.
          </p>

          <textarea
            rows={3}
            value={ttsInput}
            onChange={(e) => setTtsInput(e.target.value)}
            className="w-full bg-[#070a10] border border-slate-700/80 rounded-xl p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-purple-500 font-sans"
          />

          <button
            onClick={handleTestTTS}
            disabled={isSpeakingTest || !ttsInput.trim()}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-xl transition-colors flex items-center gap-2"
          >
            <Play className="w-3.5 h-3.5" />
            <span>{isSpeakingTest ? 'Speaking...' : 'Play Audio'}</span>
          </button>
        </div>

        {/* Pipeline Info */}
        <div className="bg-[#0a0e17] border border-slate-800 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white">Speed & Pipeline Metrics</h3>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Active LLM Model</span>
              <span className="text-cyan-300 font-mono font-semibold">Qwen 27B (160ms on Groq LPU)</span>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Silence Wait Window</span>
              <span className="text-amber-300 font-mono font-semibold">{silenceDelay / 1000}s (Instant with Enter)</span>
            </div>
            <div className="flex justify-between py-2 border-b border-slate-800">
              <span className="text-slate-400">Fast Path Router</span>
              <span className="text-emerald-300 font-mono font-semibold">&lt; 20ms Deterministic</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-slate-400">Speech Synthesis</span>
              <span className="text-purple-300 font-mono font-semibold">&lt; 50ms Native Audio</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
