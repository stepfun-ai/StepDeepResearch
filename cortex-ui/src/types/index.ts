// Type definitions corresponding to backend

export interface ModelParams {
  model_name: string;
  api_key?: string;
  base_url?: string;
  [key: string]: any;
}

export interface ComponentConfig {
  type: string;
  [key: string]: any;
}

export interface AgentConfig {
  model: ModelParams;
  name: string;
  agent_type?: string;
  system_prompt?: string;
  log_root_dir?: string;
  description?: string;
  components?: ComponentConfig[];
  sub_agents?: AgentConfig[];
  max_steps?: number;
  support_vision?: boolean;
  support_audio?: boolean;
  extra_config?: Record<string, any>;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant' | 'system' | 'tool' | null;
  content: string | any[] | null;
  name?: string;
  tool_calls?: any[];
  tool_call_id?: string;
}

export enum AgentEventType {
  RESPONSE = 'response',
  ERROR = 'error',
  REQUEST = 'request',
  SIGNAL = 'signal',
  CLIENT_TOOL_CALL = 'client_tool_call',
  CLIENT_TOOL_RESULT = 'client_tool_result',
}

export enum AgentMessageType {
  STREAM = 'stream',
  ACCUMULATED = 'accumulated',
  NON_STREAM = 'non-stream',
}

export enum AgentRunningStatus {
  FINISHED = 'finished',
  STOPPED = 'stopped',
  ERROR = 'error',
  RUNNING = 'running',
}

export interface AgentResponse {
  message?: ChatMessage;
  message_type?: string;
  status?: string;
  error_msg?: string;
  metadata?: Record<string, any>;
}

export interface AgentRequest {
  agent_name: string;
  config?: AgentConfig;
  messages?: ChatMessage[];
}

export interface ClientToolCall {
  tool_call_id: string;
  function: {
    name: string;
    arguments: string;
  };
}

export interface AgentEvent {
  event_id?: string;
  task_id: string;
  type: AgentEventType;
  agent_name?: string;
  request?: AgentRequest;
  response?: AgentResponse;
  error?: string;
  client_tool_call?: ClientToolCall;
  client_tool_result?: AgentResponse;
}

