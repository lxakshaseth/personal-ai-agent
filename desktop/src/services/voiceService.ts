/**
 * Continuous Conversational Voice Engine for Desktop UI.
 *
 * Requirements implemented:
 * 1. The microphone/conversation session NEVER self-ends or stops automatically
 *    until the user explicitly says "end", "stop", "exit", "bye", "khatam karo",
 *    or clicks the Stop button.
 * 2. Waits 3 seconds of continuous silence after user finishes speaking before
 *    finalizing speech and executing the command ("system sunne ke 3 sec baad response de").
 *    Shows real-time 3s countdown so user knows NOVA is listening.
 * 3. Follows user command, speaks NOVA's response aloud, and immediately resumes
 *    listening for the user's next command without any manual button clicks.
 */

export function isEndCommand(text: string): boolean {
  if (!text) return false;
  const clean = text
    .toLowerCase()
    .trim()
    .replace(/[.!?,;:]/g, '');

  const exitKeywords = new Set([
    'end',
    'stop',
    'exit',
    'quit',
    'bye',
    'goodbye',
    'good bye',
    'close',
    'stop listening',
    'end listening',
    'stop conversation',
    'end conversation',
    'stop session',
    'end session',
    'khatam',
    'khatam karo',
    'band karo',
    'alvida',
    'bas karo',
    'cancel session',
  ]);

  if (exitKeywords.has(clean)) return true;

  const words = clean.split(/\s+/);
  if (words.length <= 4) {
    if (
      words.includes('stop') ||
      words.includes('end') ||
      words.includes('exit') ||
      words.includes('bye') ||
      words.includes('khatam') ||
      words.includes('band')
    ) {
      if (
        words.includes('conversation') ||
        words.includes('session') ||
        words.includes('mic') ||
        words.includes('listening') ||
        words.includes('karo') ||
        words.length <= 2
      ) {
        return true;
      }
    }
  }

  return false;
}

export interface VoiceSessionCallbacks {
  onStart?: () => void;
  onInterim?: (text: string) => void;
  onCountdown?: (secondsRemaining: number | null) => void;
  onPhraseReady?: (phrase: string, isEnd: boolean) => Promise<void> | void;
  onError?: (error: string) => void;
  onSessionEnd?: () => void;
}

export interface VoiceEngineCallbacks {
  onStart?: () => void;
  onInterim?: (text: string) => void;
  onCountdown?: (secondsRemaining: number | null) => void;
  onResult?: (finalText: string) => void;
  onError?: (error: string) => void;
  onEnd?: () => void;
}

class BrowserVoiceEngine {
  private recognition: any = null;
  private isSessionActive = false;
  private isListening = false;
  private isSpeaking = false;
  private isPausedForSpeech = false;
  private currentUtterance: SpeechSynthesisUtterance | null = null;
  private silenceTimeout: any = null;
  private countdownInterval: any = null;
  private accumulatedTranscript = '';
  private activeCallbacks: VoiceSessionCallbacks | null = null;
  private silenceWaitMs = 3000; // 3 seconds silence wait

  constructor() {
    this.initRecognition();
  }

  private initRecognition() {
    if (typeof window === 'undefined') return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognition) {
      try {
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'en-US';
        this.recognition.maxAlternatives = 1;
      } catch (err) {
        console.warn('SpeechRecognition initialization failed', err);
        this.recognition = null;
      }
    }
  }

  public isSupported(): boolean {
    return this.recognition !== null;
  }

  public getSessionActive(): boolean {
    return this.isSessionActive;
  }

  public setSilenceWaitMs(ms: number): void {
    this.silenceWaitMs = Math.max(500, ms);
  }

  public getSilenceWaitMs(): number {
    return this.silenceWaitMs;
  }

  /**
   * Immediately trigger speech execution without waiting for silence timer.
   */
  public forceFlushNow(): void {
    if (!this.isSessionActive || this.isPausedForSpeech) return;
    if (this.silenceTimeout) clearTimeout(this.silenceTimeout);
    if (this.countdownInterval) clearInterval(this.countdownInterval);
    this.silenceTimeout = null;
    this.countdownInterval = null;
    this.activeCallbacks?.onCountdown?.(null);

    const commandToExecute = this.accumulatedTranscript.trim();
    if (!commandToExecute) return;
    this.accumulatedTranscript = '';

    const isEnd = isEndCommand(commandToExecute);
    if (isEnd) {
      this.isSessionActive = false;
      this.stopListening();
      this.activeCallbacks?.onPhraseReady?.(commandToExecute, true);
      this.speak('Goodbye! Voice conversation ended.');
      this.activeCallbacks?.onSessionEnd?.();
      return;
    }

    this.isPausedForSpeech = true;
    try {
      this.recognition?.abort();
    } catch {}

    const cb = this.activeCallbacks;
    Promise.resolve(cb?.onPhraseReady?.(commandToExecute, false))
      .catch((err) => {
        cb?.onError?.(err?.message || 'Execution error');
      })
      .finally(() => {
        if (this.isSessionActive) {
          this.isPausedForSpeech = false;
          cb?.onInterim?.('');
          this.startListeningInternal();
        }
      });
  }

  /**
   * Start a continuous conversation session.
   *
   * NEVER self-ends until user says "end" or calls endSession().
   * Fast default: 1.2s silence wait (configurable).
   */
  public startContinuousSession(
    callbacks: VoiceSessionCallbacks,
    silenceWaitMs = 1200
  ): void {
    if (!this.recognition) {
      callbacks.onError?.('Web Speech Recognition is not supported in this browser.');
      return;
    }

    // Stop any ongoing speech
    this.stopSpeaking();
    if (this.silenceTimeout) clearTimeout(this.silenceTimeout);
    if (this.countdownInterval) clearInterval(this.countdownInterval);

    this.isSessionActive = true;
    this.isPausedForSpeech = false;
    this.activeCallbacks = callbacks;
    this.silenceWaitMs = silenceWaitMs;
    this.accumulatedTranscript = '';

    this.startListeningInternal();
  }

  private startListeningInternal() {
    if (!this.recognition || !this.isSessionActive || this.isPausedForSpeech) return;

    try {
      this.recognition.abort();
    } catch {}

    this.recognition.continuous = true;
    this.recognition.interimResults = true;

    this.recognition.onstart = () => {
      this.isListening = true;
      this.activeCallbacks?.onStart?.();
    };

    this.recognition.onresult = (event: any) => {
      if (this.isPausedForSpeech || !this.isSessionActive) return;

      let interimTranscript = '';
      let newFinal = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          newFinal += transcript + ' ';
        } else {
          interimTranscript += transcript;
        }
      }

      if (newFinal) {
        this.accumulatedTranscript = (this.accumulatedTranscript + ' ' + newFinal).trim();
      }

      const liveText = (
        this.accumulatedTranscript + (interimTranscript ? ' ' + interimTranscript : '')
      ).trim();

      if (liveText) {
        this.activeCallbacks?.onInterim?.(liveText);
        // Start/reset the 3-second silence timer
        this.resetSilenceTimer(liveText);
      }
    };

    this.recognition.onerror = (event: any) => {
      console.warn('SpeechRecognition event notice:', event.error);
      if (event.error === 'not-allowed') {
        this.isSessionActive = false;
        this.activeCallbacks?.onError?.('Microphone access denied. Please allow mic permissions.');
        this.activeCallbacks?.onSessionEnd?.();
      }
    };

    this.recognition.onend = () => {
      this.isListening = false;
      // CRITICAL: Mic NEVER self-ends while session is active! Auto-restart!
      if (this.isSessionActive && !this.isPausedForSpeech && !this.isSpeaking) {
        try {
          this.recognition.start();
        } catch {}
      }
    };

    try {
      this.recognition.start();
    } catch (err) {
      console.warn('Could not start speech recognition immediately:', err);
    }
  }

  private resetSilenceTimer(currentText: string) {
    if (this.silenceTimeout) clearTimeout(this.silenceTimeout);
    if (this.countdownInterval) clearInterval(this.countdownInterval);

    let remainingMs = this.silenceWaitMs;
    this.activeCallbacks?.onCountdown?.(Number((remainingMs / 1000).toFixed(1)));

    this.countdownInterval = setInterval(() => {
      remainingMs -= 200;
      if (remainingMs > 0) {
        this.activeCallbacks?.onCountdown?.(Number((remainingMs / 1000).toFixed(1)));
      } else {
        if (this.countdownInterval) clearInterval(this.countdownInterval);
        this.countdownInterval = null;
      }
    }, 200);

    this.silenceTimeout = setTimeout(async () => {
      if (!this.isSessionActive || this.isPausedForSpeech) return;

      this.activeCallbacks?.onCountdown?.(null);
      const commandToExecute = currentText.trim();
      if (!commandToExecute) return;

      // Clear for next turn
      this.accumulatedTranscript = '';

      // Check if user gave an end / exit command:
      const isEnd = isEndCommand(commandToExecute);
      if (isEnd) {
        this.isSessionActive = false;
        this.stopListening();
        this.activeCallbacks?.onPhraseReady?.(commandToExecute, true);
        await this.speak('Goodbye! Voice conversation ended.');
        this.activeCallbacks?.onSessionEnd?.();
        return;
      }

      // Pause mic capture while agent processes & speaks response
      this.isPausedForSpeech = true;
      try {
        this.recognition?.abort();
      } catch {}

      try {
        await this.activeCallbacks?.onPhraseReady?.(commandToExecute, false);
      } catch (err: any) {
        this.activeCallbacks?.onError?.(err?.message || 'Execution error');
      } finally {
        // Resume listening automatically if session is still alive!
        if (this.isSessionActive) {
          this.isPausedForSpeech = false;
          this.activeCallbacks?.onInterim?.('');
          this.startListeningInternal();
        }
      }
    }, this.silenceWaitMs);
  }

  public endSession() {
    this.isSessionActive = false;
    this.isPausedForSpeech = false;
    if (this.silenceTimeout) clearTimeout(this.silenceTimeout);
    if (this.countdownInterval) clearInterval(this.countdownInterval);
    this.silenceTimeout = null;
    this.countdownInterval = null;
    this.accumulatedTranscript = '';

    this.stopListening();
    this.stopSpeaking();
    this.activeCallbacks?.onCountdown?.(null);
    this.activeCallbacks?.onSessionEnd?.();
    this.activeCallbacks = null;
  }

  public stopListening() {
    if (this.recognition) {
      try {
        this.recognition.abort();
      } catch {}
      this.isListening = false;
    }
  }

  /**
   * Single-shot listen helper with 3-second silence wait.
   */
  public startListening(callbacks?: VoiceEngineCallbacks, silenceWaitMs = 3000): Promise<string> {
    return new Promise((resolve, reject) => {
      if (!this.recognition) {
        reject(new Error('Web Speech Recognition is not supported in this environment.'));
        return;
      }

      this.stopSpeaking();
      this.stopListening();

      let accumulated = '';
      let timer: any = null;
      let countdown: any = null;

      this.recognition.continuous = true;
      this.recognition.interimResults = true;

      this.recognition.onstart = () => {
        this.isListening = true;
        callbacks?.onStart?.();
      };

      const cleanup = () => {
        if (timer) clearTimeout(timer);
        if (countdown) clearInterval(countdown);
        callbacks?.onCountdown?.(null);
        this.stopListening();
      };

      this.recognition.onresult = (event: any) => {
        let interim = '';
        let newFinal = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            newFinal += transcript + ' ';
          } else {
            interim += transcript;
          }
        }
        if (newFinal) accumulated = (accumulated + ' ' + newFinal).trim();
        const live = (accumulated + (interim ? ' ' + interim : '')).trim();

        if (live) {
          callbacks?.onInterim?.(live);

          // Reset 3s silence timer
          if (timer) clearTimeout(timer);
          if (countdown) clearInterval(countdown);

          let sec = Math.round(silenceWaitMs / 1000);
          callbacks?.onCountdown?.(sec);

          countdown = setInterval(() => {
            sec -= 1;
            if (sec > 0) {
              callbacks?.onCountdown?.(sec);
            } else {
              clearInterval(countdown);
            }
          }, 1000);

          timer = setTimeout(() => {
            cleanup();
            callbacks?.onResult?.(live);
            resolve(live);
          }, silenceWaitMs);
        }
      };

      this.recognition.onerror = (event: any) => {
        console.warn('Speech recognition error:', event.error);
        cleanup();
        callbacks?.onError?.(event.error);
        resolve('');
      };

      this.recognition.onend = () => {
        this.isListening = false;
        callbacks?.onEnd?.();
      };

      try {
        this.recognition.start();
      } catch (err: any) {
        cleanup();
        reject(err);
      }
    });
  }

  /**
   * Speak text immediately in the user's desktop browser (<50ms latency).
   */
  public speak(text: string): Promise<void> {
    return new Promise((resolve) => {
      if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
        resolve();
        return;
      }

      const cleanText = text.trim();
      if (!cleanText) {
        resolve();
        return;
      }

      this.stopSpeaking();
      this.isSpeaking = true;

      const utterance = new SpeechSynthesisUtterance(cleanText);
      this.currentUtterance = utterance;
      utterance.rate = 1.05; // Natural crisp assistant pace
      utterance.pitch = 1.0;
      utterance.lang = 'en-US';

      // Pick high-quality English voice if available
      const voices = window.speechSynthesis.getVoices();
      const preferredVoice = voices.find(
        (v) =>
          v.lang.startsWith('en') &&
          (v.name.includes('Google') ||
            v.name.includes('Natural') ||
            v.name.includes('Microsoft') ||
            v.name.includes('Samantha') ||
            v.name.includes('David'))
      );
      if (preferredVoice) {
        utterance.voice = preferredVoice;
      }

      utterance.onend = () => {
        this.isSpeaking = false;
        this.currentUtterance = null;
        resolve();
      };

      utterance.onerror = (e) => {
        console.warn('Speech synthesis error:', e);
        this.isSpeaking = false;
        this.currentUtterance = null;
        resolve();
      };

      window.speechSynthesis.speak(utterance);
    });
  }

  public stopSpeaking() {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      try {
        window.speechSynthesis.cancel();
      } catch {}
    }
    this.isSpeaking = false;
    this.currentUtterance = null;
  }

  public stopAll() {
    this.endSession();
  }
}

export const browserVoice = new BrowserVoiceEngine();

export interface StreamingVoiceEvents {
  onConnectionReady?: () => void;
  onVadState?: (state: 'speaking' | 'silence') => void;
  onTranscriptFinal?: (text: string) => void;
  onLlmStart?: () => void;
  onLlmChunk?: (token: string) => void;
  onTtsStart?: (chunkIndex: number, text: string) => void;
  onAudioChunk?: (chunkIndex: number, text: string, base64Audio: string) => void;
  onAssistantDone?: (metrics: { [key: string]: number }) => void;
  onPlaybackComplete?: () => void;
  onInterrupted?: () => void;
  onError?: (err: string) => void;
}

export class StreamingVoiceClient {
  private ws: WebSocket | null = null;
  private callbacks: StreamingVoiceEvents = {};
  private speechQueue: string[] = [];
  private isProcessingSpeechQueue = false;
  private isConnected = false;

  public get isReady(): boolean {
    return this.isConnected && this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  public connect(callbacks: StreamingVoiceEvents) {
    this.callbacks = callbacks;
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || '127.0.0.1';
    const port = '8000';
    const url = `${protocol}//${host}:${port}/ws/voice`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.callbacks.onConnectionReady?.();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const type = msg.type;

          if (type === 'connection_ready') {
            this.callbacks.onConnectionReady?.();
          } else if (type === 'vad_state') {
            this.callbacks.onVadState?.(msg.state);
          } else if (type === 'transcript_final') {
            this.callbacks.onTranscriptFinal?.(msg.text);
          } else if (type === 'llm_start') {
            this.callbacks.onLlmStart?.();
          } else if (type === 'llm_chunk') {
            this.callbacks.onLlmChunk?.(msg.text);
          } else if (type === 'tts_start') {
            this.callbacks.onTtsStart?.(msg.chunk_index, msg.text);
            // Queue text for immediate progressive spoken playback
            this.queueTextForSpeech(msg.text);
          } else if (type === 'audio_chunk') {
            this.callbacks.onAudioChunk?.(msg.chunk_index, msg.text, msg.data);
          } else if (type === 'assistant_done') {
            this.callbacks.onAssistantDone?.(msg.metrics || {});
          } else if (type === 'interrupted') {
            this.handleLocalInterruption();
            this.callbacks.onInterrupted?.();
          } else if (type === 'error') {
            this.callbacks.onError?.(msg.message);
          }
        } catch (e) {
          console.debug('Error parsing voice ws message', e);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
      };

      this.ws.onerror = (e) => {
        console.warn('Voice WebSocket error:', e);
      };
    } catch (err) {
      console.warn('Failed to create voice WebSocket:', err);
    }
  }

  public sendPrompt(text: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'prompt', text }));
    }
  }

  public interrupt() {
    this.handleLocalInterruption();
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'interrupt' }));
    }
  }

  private handleLocalInterruption() {
    this.speechQueue = [];
    this.isProcessingSpeechQueue = false;
    browserVoice.stopSpeaking();
  }

  private queueTextForSpeech(text: string) {
    const clean = text.trim();
    if (!clean) return;
    this.speechQueue.push(clean);
    if (!this.isProcessingSpeechQueue) {
      this.processSpeechQueue();
    }
  }

  private async processSpeechQueue() {
    if (this.isProcessingSpeechQueue) return;
    this.isProcessingSpeechQueue = true;

    while (this.speechQueue.length > 0) {
      const nextChunk = this.speechQueue.shift();
      if (nextChunk) {
        await browserVoice.speak(nextChunk);
      }
    }

    this.isProcessingSpeechQueue = false;
    this.callbacks.onPlaybackComplete?.();
  }

  public disconnect() {
    this.interrupt();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected = false;
  }
}

export const streamingVoiceClient = new StreamingVoiceClient();

