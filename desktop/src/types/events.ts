import { AgentStatusType, ConfirmationTicket, ToolCallItem } from './agent';

export type EventType =
  | 'status_changed'
  | 'tool_started'
  | 'tool_finished'
  | 'tool_failed'
  | 'confirmation_requested'
  | 'confirmation_resolved'
  | 'voice_event'
  | 'command_started'
  | 'command_completed'
  | 'system_metrics'
  | 'log_emitted'
  | 'init_snapshot';

export interface WSEvent {
  type: EventType;
  payload: any;
  timestamp: number;
}
