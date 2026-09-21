import { useState, useEffect } from 'react';
import { SystemMetrics } from '../types/system';

interface SystemState {
  metrics: SystemMetrics | null;
  cpuHistory: number[];
  memoryHistory: number[];
  isLoading: boolean;
  error: string | null;
}

const defaultSystemState: SystemState = {
  metrics: null,
  cpuHistory: [],
  memoryHistory: [],
  isLoading: true,
  error: null,
};

type Listener = (state: SystemState) => void;
let state: SystemState = { ...defaultSystemState };
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((l) => l(state));
}

export const systemStore = {
  getState: () => state,
  setMetrics: (metrics: SystemMetrics) => {
    const nextCpu = [...state.cpuHistory, metrics.cpu_percent].slice(-30);
    const nextMem = [...state.memoryHistory, metrics.memory_percent].slice(-30);
    state = {
      ...state,
      metrics,
      cpuHistory: nextCpu,
      memoryHistory: nextMem,
      isLoading: false,
      error: null,
    };
    notify();
  },
  setError: (err: string) => {
    state = { ...state, error: err, isLoading: false };
    notify();
  },
};

export function useSystemStore(): [SystemState, typeof systemStore] {
  const [localState, setLocalState] = useState<SystemState>(systemStore.getState());

  useEffect(() => {
    return (listeners.add(setLocalState), () => {
      listeners.delete(setLocalState);
    });
  }, []);

  return [localState, systemStore];
}
