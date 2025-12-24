import axios from 'axios';
import { AgentConfig, AgentEvent, ChatMessage } from '../types';

const DEFAULT_API_BASE_URL = 'http://localhost:8001';

const sanitizeBaseUrl = (url?: string | null): string => {
  if (!url) {
    return '';
  }
  return url.replace(/\/+$/, '');
};

const API_BASE_URL =
  sanitizeBaseUrl(import.meta.env.VITE_API_BASE_URL?.trim()) || DEFAULT_API_BASE_URL;

// Get stored endpoint config
export const getStoredEndpoint = (): string | undefined => {
  const stored = localStorage.getItem('api_endpoint');
  const sanitized = sanitizeBaseUrl(stored?.trim());
  return sanitized || undefined;
};

// Get API base URL, prioritize user-configured endpoint
const getApiBaseUrl = (): string => {
  return getStoredEndpoint() || API_BASE_URL;
};

// Get all agents
export const fetchAgents = async (): Promise<AgentConfig[]> => {
  const baseUrl = getApiBaseUrl();
  const response = await axios.get(`${baseUrl}/agents`);
  return response.data;
};

// WebSocket management class
export class WebSocketService {
  private ws: WebSocket | null = null;
  private messageHandler: ((event: AgentEvent) => void) | null = null;
  private errorHandler: ((error: Event) => void) | null = null;
  private closeHandler: (() => void) | null = null;

  connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (this.messageHandler) {
              this.messageHandler(data);
            }
          } catch (error) {
            console.error('Failed to parse message:', error);
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          if (this.errorHandler) {
            this.errorHandler(error);
          }
          reject(error);
        };

        this.ws.onclose = () => {
          console.log('WebSocket closed');
          if (this.closeHandler) {
            this.closeHandler();
          }
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  send(data: AgentEvent): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.error('WebSocket is not connected');
    }
  }

  onMessage(handler: (event: AgentEvent) => void): void {
    this.messageHandler = handler;
  }

  onError(handler: (error: Event) => void): void {
    this.errorHandler = handler;
  }

  onClose(handler: () => void): void {
    this.closeHandler = handler;
  }

  close(): void {
    if (this.ws) {
      // Remove all event listeners to avoid triggering callbacks
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      
      // Close connection
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

// Generate random context_id
const generateContextId = (): string => {
  return `ctx_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};

const buildWebSocketUrl = (
  agentName: string,
  chatMode: 'multi' | 'single',
  contextId: string,
  endpoint?: string
): string => {
  const base = endpoint && endpoint.length > 0 ? endpoint : window.location.origin;
  const url = new URL(base, window.location.origin);
  const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  const pathname =
    url.pathname && url.pathname !== '/' ? url.pathname.replace(/\/+$/, '') : '';
  return `${protocol}//${url.host}${pathname}/${chatMode}/ws/${encodeURIComponent(agentName)}/${contextId}`;
};

// Create WebSocket instance and initialize connection
export const createWebSocketConnection = async (
  agentName: string,
  chatMode: 'multi' | 'single' = 'multi',
  _initialMessages?: ChatMessage[],
  customEndpoint?: string
): Promise<{ service: WebSocketService; taskId: string }> => {
  const wsService = new WebSocketService();
  
  // Generate random context_id
  const contextId = generateContextId();
  
  // Build WebSocket URL
  const configuredEndpoint = sanitizeBaseUrl(customEndpoint?.trim()) || getApiBaseUrl();
  const wsUrl = buildWebSocketUrl(agentName, chatMode, contextId, configuredEndpoint);
  
  await wsService.connect(wsUrl);
  
  // Generate taskId but don't send immediately, let caller set up callbacks first
  const taskId = generateTaskId();
  
  return { service: wsService, taskId };
};

// Generate task ID
export const generateTaskId = (): string => {
  return `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
};
