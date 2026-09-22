/**
 * Web Audio API Sci-Fi Sound Synthesizer for Desktop Robot Companion
 * Self-contained audio feedback without external audio files.
 */

let audioCtx: AudioContext | null = null;
let isMuted = false;

// Load mute state from localStorage if available
try {
  const saved = localStorage.getItem('nova_robot_muted');
  if (saved !== null) {
    isMuted = saved === 'true';
  }
} catch {
  // ignore
}

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

export const robotSounds = {
  isMuted: () => isMuted,
  setMuted: (muted: boolean) => {
    isMuted = muted;
    try {
      localStorage.setItem('nova_robot_muted', String(muted));
    } catch {}
  },
  toggleMute: () => {
    robotSounds.setMuted(!isMuted);
    return isMuted;
  },

  // Gentle sci-fi UI blip on click
  playBlip: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.06);

      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.08);
    } catch {}
  },

  // Wake / listening chime (harmonic ascending chime)
  playWake: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      [587.33, 880, 1174.66].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const startTime = ctx.currentTime + idx * 0.06;

        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, startTime);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(0.09, startTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.22);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startTime);
        osc.stop(startTime + 0.24);
      });
    } catch {}
  },

  // Happy playful chirp when petting or clicking the robot
  playHappyChirp: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      const notes = [659.25, 830.61, 987.77, 1318.51];
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const startTime = ctx.currentTime + idx * 0.05;

        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, startTime);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(0.1, startTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.25);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startTime);
        osc.stop(startTime + 0.26);
      });
    } catch {}
  },

  // Success chime on task completion
  playSuccess: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      [523.25, 659.25, 783.99, 1046.5].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const startTime = ctx.currentTime + idx * 0.08;

        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, startTime);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(0.08, startTime + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.35);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startTime);
        osc.stop(startTime + 0.38);
      });
    } catch {}
  },

  // Alert / confirmation warning tone
  playAlert: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      [440, 554.37].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const startTime = ctx.currentTime + idx * 0.12;

        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(freq, startTime);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(0.06, startTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.16);

        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startTime);
        osc.stop(startTime + 0.18);
      });
    } catch {}
  },

  // Halt / stop tone
  playStop: () => {
    if (isMuted) return;
    const ctx = getAudioContext();
    if (!ctx) return;
    try {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(400, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(180, ctx.currentTime + 0.15);

      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);

      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.18);
    } catch {}
  },
};
