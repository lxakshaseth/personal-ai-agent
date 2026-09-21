export type TimelineEventType =
  | 'agent.started'
  | 'agent.listening'
  | 'agent.transcribing'
  | 'agent.thinking'
  | 'agent.planning'
  | 'tool.selected'
  | 'tool.started'
  | 'tool.progress'
  | 'tool.completed'
  | 'confirmation.required'
  | 'agent.completed'
  | 'agent.error'
  | 'task_cancelled';

export interface TimelineItem {
  id: string;
  event: TimelineEventType | string;
  timestamp: string; // formatted HH:mm:ss, e.g. "12:31:01"
  rawTimestamp: number;
  title: string; // e.g. "🎙 Listening", "📝 Transcribing", "🧠 Understanding command", "🔧 Selected: open_url", "⚙ Executing", "✓ Completed", "🤖 YouTube is open."
  tool?: string;
  duration?: number; // seconds
  progress?: number; // 0.0 to 1.0
  details?: any; // arguments, output, sanitized payload
  error?: string | null;
  status: 'running' | 'completed' | 'error' | 'cancelled' | 'pending';
  requestId?: string;
}

export interface ActiveExecutionState {
  requestId?: string;
  taskId?: string;
  command?: string;
  currentOperation: string;
  progress?: number; // 0.0 to 1.0
  startTime: number;
  elapsedSeconds: number;
  status: 'running' | 'completed' | 'cancelled' | 'error';
}
