export type AgentStatusType =
  | 'offline'
  | 'online'
  | 'listening'
  | 'thinking'
  | 'executing'
  | 'waiting_confirmation'
  | 'error';

export interface ToolInfo {
  name: string;
  description: string;
  permission_level: 'LOW' | 'MEDIUM' | 'HIGH';
  requires_confirmation: boolean;
  parameters_schema: Record<string, any>;
  enabled?: boolean;
}

export interface ToolCallItem {
  tool: string;
  args: Record<string, any>;
  success: boolean;
  output: string;
  error?: string | null;
}

export interface CommandHistoryItem {
  id: string;
  timestamp: number;
  command: string;
  success: boolean;
  response: string;
  tool_calls: ToolCallItem[];
  error?: string | null;
  duration_ms: number;
}

export interface ConfirmationTicket {
  ticket_id: string;
  tool_name: string;
  arguments: Record<string, any>;
  command: string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  created_at: number;
  expires_at: number;
}

export interface TaskStep {
  name: string;
  icon: string;
  status: 'pending' | 'active' | 'completed' | 'failed' | 'cancelled';
}

export type TaskStateType =
  | 'CREATED'
  | 'PLANNING'
  | 'WAITING_APPROVAL'
  | 'RUNNING'
  | 'PAUSED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'queued'
  | 'planning'
  | 'executing'
  | 'paused'
  | 'completed'
  | 'cancelled'
  | 'failed';

export interface PlanStep {
  id: string;
  index: number;
  specialist: 'Browser Agent' | 'Computer Agent' | 'File Agent' | 'Communication Agent' | 'System Agent' | string;
  action: string;
  tool_name: string;
  arguments: Record<string, any>;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  duration_seconds?: number | null;
  output?: string | null;
  error?: string | null;
}

export interface ComplexPlan {
  summary: string;
  steps: PlanStep[];
  estimated_operations: number;
}

export interface AgentTask {
  id: string;
  description: string;
  status: TaskStateType;
  is_complex?: boolean;
  plan?: ComplexPlan | null;
  steps: TaskStep[];
  created_at: number;
  updated_at: number;
  duration_seconds: number;
  result?: string | null;
  error?: string | null;
}

export interface SecuritySettings {
  allowed_base_paths: string[];
  allow_shell_commands: boolean;
  require_confirmation: boolean;
  allow_file_deletion: boolean;
  allow_browser_automation: boolean;
  allow_whatsapp_messaging: boolean;
  allow_system_controls: boolean;
  disabled_tools: string[];
  allowed_commands: string[];
  risk_policies: Record<string, string>;
}

export interface AgentConfig {
  groq_model: string;
  stt_provider: string;
  tts_provider: string;
  voice_enabled: boolean;
  wake_word: string;
  wake_word_enabled: boolean;
  allow_shell_commands: boolean;
  require_confirmation: boolean;
}

export interface AuditLogEntry {
  timestamp: string;
  user_command: string;
  tool: string;
  arguments: Record<string, any>;
  permission: string;
  result: 'success' | 'failure' | 'denied' | 'confirmation_required';
  output: string;
  error?: string | null;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  source?: 'voice' | 'text';
  text: string;
  timestamp: number;
  tool_calls?: ToolCallItem[];
  status?: AgentStatusType;
  error?: string | null;
}
