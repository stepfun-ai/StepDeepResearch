import React, { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Card,
  Input,
  Button,
  message,
  Spin,
  Tag,
  Space,
  Typography,
  Layout,
  Modal,
  Badge,
  Collapse,
} from 'antd';
import {
  SendOutlined,
  ArrowLeftOutlined,
  UserOutlined,
  RobotOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  InfoCircleOutlined,
  ToolOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { createWebSocketConnection, WebSocketService, getStoredEndpoint } from '../services/api';
import {
  AgentEvent,
  AgentEventType,
  AgentMessageType,
  ChatMessage,
} from '../types';
import { EndpointConfig } from '../components/EndpointConfig';
import { CitationStore } from '../types/citation';
import { extractCitationsFromToolResult, parseQueryResults, isBatchSearchResult } from '../utils/citationParser';
import FinalAnswer from '../components/FinalAnswer';
import SearchResultsPanel from '../components/SearchResultsPanel';
import TodoPanel, { parseTodoResult, isTodoResult } from '../components/TodoPanel';
import ShellPanel, { parseShellResult, isShellResult } from '../components/ShellPanel';
import WebPagePanel, { parseBatchOpenResult, isBatchOpenResult } from '../components/WebPagePanel';
import FilePanel, { parseFileResult, isFileResult } from '../components/FilePanel';

const { TextArea } = Input;
const { Title, Text } = Typography;
const { Header, Content, Footer } = Layout;

interface ToolCall {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string;
  };
}

interface ToolCallStatus {
  id: string;
  completed: boolean;
  result?: string;
}

interface MessageItem {
  id: string; // For React key, keep unique
  messageId?: string; // message.id, for merging multiple events of the same message
  type: AgentEventType;
  content: string | any[];
  contentItems?: ContentItem[]; // Structured content items
  isUser: boolean;
  messageType?: string;
  status?: string;
  timestamp: Date;
  agentName?: string; // Agent name
  raw?: AgentEvent; // Last event (backward compatibility)
  rawEvents: AgentEvent[]; // All related events
  toolCalls?: ToolCall[];
  toolCallId?: string;
  toolCallResult?: string;
  clientToolCall?: {
    tool_call_id: string;
    function: {
      name: string;
      arguments: string;
    };
  };
  clientToolSubmitted?: boolean; // Flag for whether client_tool has been submitted
  clientToolResult?: string; // Store the submitted result
}

// Content item types
interface ContentItem {
  type: 'text' | 'thinking';
  content: string;
}

// Helper function: Parse content items from content array
const parseContentItems = (content: any): ContentItem[] => {
  if (typeof content === 'string') {
    return content ? [{ type: 'text', content }] : [];
  }
  if (Array.isArray(content)) {
    return content
      .map(item => {
        if (typeof item === 'string') {
          return item ? { type: 'text' as const, content: item } : null;
        }
        if (item && typeof item === 'object') {
          // Handle {type: 'text', text: '...'} format
          if (item.type === 'text' && typeof item.text === 'string') {
            return item.text ? { type: 'text' as const, content: item.text } : null;
          }
          // Handle {type: 'thinking', thinking: '...'} format
          if (item.type === 'thinking' && typeof item.thinking === 'string') {
            return item.thinking ? { type: 'thinking' as const, content: item.thinking } : null;
          }
          // Handle other objects containing text field
          if ('text' in item && typeof item.text === 'string') {
            return item.text ? { type: 'text' as const, content: item.text } : null;
          }
        }
        return null;
      })
      .filter((item): item is ContentItem => item !== null);
  }
  if (content === null || content === undefined) {
    return [];
  }
  return [{ type: 'text', content: JSON.stringify(content) }];
};

// Helper function: Extract plain text from content (for streaming accumulation)
const extractTextFromContent = (content: any): string => {
  const items = parseContentItems(content);
  return items.map(item => item.content).join('');
};

// Helper function: Merge adjacent content items of the same type
const mergeContentItems = (items: ContentItem[]): ContentItem[] => {
  if (items.length === 0) return [];
  const merged: ContentItem[] = [];
  let current = { ...items[0] };
  
  for (let i = 1; i < items.length; i++) {
    if (items[i].type === current.type) {
      current.content += items[i].content;
    } else {
      merged.push(current);
      current = { ...items[i] };
    }
  }
  merged.push(current);
  return merged;
};

const ChatPage: React.FC = () => {
  const { agentName } = useParams<{ agentName: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const chatMode = (searchParams.get('mode') as 'multi' | 'single') || 'multi';

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [connecting, setConnecting] = useState(true);
  const [wsService, setWsService] = useState<WebSocketService | null>(null);
  const [taskId, setTaskId] = useState<string>('');
  const [toolCallStatuses, setToolCallStatuses] = useState<Map<string, ToolCallStatus>>(new Map());
  const [selectedMessage, setSelectedMessage] = useState<MessageItem | null>(null);
  const [isEventModalVisible, setIsEventModalVisible] = useState(false);
  const [connectionError, setConnectionError] = useState<string>('');
  const [clientToolInputs, setClientToolInputs] = useState<Map<string, string>>(new Map());
  // Citation store - for storing cite_index info from search results
  const [citationStore, setCitationStore] = useState<CitationStore>(new Map());
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const streamingMessageIdRef = useRef<string | null>(null);
  const wsServiceRef = useRef<WebSocketService | null>(null);
  const isConnectingRef = useRef<boolean>(false);
  const isMountedRef = useRef<boolean>(true);
  const userScrolledRef = useRef<boolean>(false);

  useEffect(() => {
    isMountedRef.current = true;
    
    if (!agentName) {
      message.error('Agent name not specified');
      navigate('/');
      return;
    }

    console.log('Component mounted, initializing WebSocket');
    initWebSocket();

    return () => {
      // Only close connection when component truly unmounts
      console.log('Component unmounting, closing WebSocket connection');
      isMountedRef.current = false;
      if (wsServiceRef.current) {
        wsServiceRef.current.close();
        wsServiceRef.current = null;
      }
      isConnectingRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty dependency array, only execute on mount/unmount

  useEffect(() => {
    // Only auto-scroll if user hasn't manually scrolled up
    if (!userScrolledRef.current) {
      scrollToBottom();
    }
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Check if user is near the bottom of the scroll container
  const isNearBottom = () => {
    const container = contentRef.current;
    if (!container) return true;
    const threshold = 100; // pixels from bottom
    return container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
  };

  // Handle scroll event to detect user manual scroll
  const handleScroll = () => {
    if (isNearBottom()) {
      userScrolledRef.current = false;
    } else {
      userScrolledRef.current = true;
    }
  };

  const handleEndpointChange = () => {
    // Reconnect
    if (wsServiceRef.current) {
      wsServiceRef.current.close();
      wsServiceRef.current = null;
    }
    setWsService(null);
    setConnecting(true);
    setConnectionError('');
    initWebSocket();
  };

  const initWebSocket = async () => {
    // Prevent duplicate connections
    if (isConnectingRef.current) {
      console.log('Already connecting, skip');
      return;
    }

    try {
      isConnectingRef.current = true;
      
      // If there's an existing connection, close it first
      if (wsServiceRef.current) {
        console.log('Closing existing WebSocket connection');
        wsServiceRef.current.close();
        wsServiceRef.current = null;
      }

      setConnecting(true);

      console.log('Creating WebSocket connection...');
      const endpoint = getStoredEndpoint();
      const { service: ws, taskId: newTaskId } = await createWebSocketConnection(
        agentName!,
        chatMode,
        [],
        endpoint
      );

      setTaskId(newTaskId);

      // Set up all event handlers first
      ws.onMessage(handleWebSocketMessage);
      ws.onError((error) => {
        console.error('WebSocket error:', error);
        isConnectingRef.current = false;
        setConnecting(false);
        setConnectionError('WebSocket connection error');
      });
      ws.onClose(() => {
        console.log('WebSocket closed');
        isConnectingRef.current = false;
        // Only update state on non-intentional close
        if (wsServiceRef.current === ws) {
          wsServiceRef.current = null;
          setWsService(null);
          setConnecting(false);
        }
      });

      // Update both state and ref
      wsServiceRef.current = ws;
      setWsService(ws);
      console.log('WebSocket connected successfully');
      
      setConnecting(false);
      setConnectionError('');
      isConnectingRef.current = false;
    } catch (error) {
      console.error('Failed to connect:', error);
      setConnecting(false);
      isConnectingRef.current = false;
      const errorMsg = error instanceof Error ? error.message : 'Failed to connect to Agent';
      setConnectionError(errorMsg);
      message.error(errorMsg);
    }
  };

  const handleWebSocketMessage = (event: AgentEvent) => {
    console.log('Received message:', event);

    if (event.type === AgentEventType.ERROR) {
      console.error('Received error from server:', event.error);
      message.error(`Server error: ${event.error}`);
      handleErrorMessage(event);
    } else if (event.type === AgentEventType.CLIENT_TOOL_CALL && event.client_tool_call) {
      handleClientToolCall(event);
    } else if (event.type === AgentEventType.RESPONSE && event.response) {
      const response = event.response;
      const messageType = response.message_type;
      const responseMessage = response.message;

      // Ignore events with role: null
      if (responseMessage && responseMessage.role === null && response.message?.content === null) {
        console.log('Ignored message with role: null');
        return;
      }

      // Check if this is a tool_call completion event (role is tool)
      if (responseMessage?.role === 'tool' && responseMessage?.tool_call_id) {
        handleToolCallResult(event);
        return;
      }

      // Check if contains tool_calls and is accumulated (stream end)
      if (responseMessage?.tool_calls && 
          responseMessage.tool_calls.length > 0 && 
          messageType === AgentMessageType.ACCUMULATED) {
        handleToolCallStart(event);
        return;
      }

      // Handle regular streaming messages
      if (messageType === AgentMessageType.STREAM) {
        handleStreamMessage(event);
      } else if (messageType === AgentMessageType.ACCUMULATED) {
        // accumulated without tool_calls means regular message stream end
        // No special handling needed, already accumulated in STREAM
        streamingMessageIdRef.current = null;
      } else {
        // Non-streaming message, create separate card
        handleNonStreamMessage(event);
      }
    }
  };

  const handleToolCallStart = (event: AgentEvent) => {
    const responseMessage = event.response!.message!;
    const toolCalls = responseMessage.tool_calls as ToolCall[];
    const messageId = responseMessage.id || undefined;

    // Initialize tool_call status
    setToolCallStatuses((prev) => {
      const newMap = new Map(prev);
      toolCalls.forEach((tc) => {
        newMap.set(tc.id, { id: tc.id, completed: false });
      });
      return newMap;
    });

    // Close streaming message
    streamingMessageIdRef.current = null;

    setMessages((prev) => {
      // Find if there's already a message with same messageId (streaming message)
      const existingIndex = prev.findIndex(msg => msg.messageId === messageId && messageId);
      
      if (existingIndex !== -1) {
        // Existing streaming message, keep it separate, create new tool_call message
        // Create new tool_call message (no content, only toolCalls)
        const toolMessage: MessageItem = {
          id: `tool_${Date.now()}`,
          messageId: `${messageId}_tool`, // Use different messageId
          type: AgentEventType.RESPONSE,
          content: '',
          contentItems: [],
          isUser: false,
          timestamp: new Date(),
          agentName: event.agent_name,
          raw: event,
          rawEvents: [event],
          toolCalls: toolCalls,
        };
        
        // Insert new tool_call message after existing message
        const newMessages = [...prev];
        newMessages.splice(existingIndex + 1, 0, toolMessage);
        return newMessages;
      } else {
        // No existing message, create new tool_call message
        const newMessage: MessageItem = {
          id: `tool_${Date.now()}`,
          messageId: messageId,
          type: AgentEventType.RESPONSE,
          content: '',
          contentItems: [],
          isUser: false,
          timestamp: new Date(),
          agentName: event.agent_name,
          raw: event,
          rawEvents: [event],
          toolCalls: toolCalls,
        };
        return [...prev, newMessage];
      }
    });
  };

  const handleToolCallResult = (event: AgentEvent) => {
    const responseMessage = event.response!.message!;
    const toolCallId = responseMessage.tool_call_id!;
    const content = responseMessage.content;
    
    // Convert content to string or keep as is
    let result: string | any;
    if (typeof content === 'string') {
      result = content;
    } else if (Array.isArray(content)) {
      // If it's an array, try to extract text content
      const textContent = content
        .map(item => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object' && 'text' in item) return item.text;
          return JSON.stringify(item);
        })
        .join('\n');
      result = textContent || JSON.stringify(content, null, 2);
    } else {
      result = content;
    }

    // Extract citation info from search results
    if (typeof result === 'string' && isBatchSearchResult(result)) {
      const newCitations = extractCitationsFromToolResult(result);
      if (newCitations.size > 0) {
        setCitationStore((prev) => {
          const merged = new Map(prev);
          newCitations.forEach((value, key) => {
            merged.set(key, value);
          });
          return merged;
        });
        console.log(`Extracted ${newCitations.size} citations from tool result`);
      }
    }

    // Update tool_call status
    setToolCallStatuses((prev) => {
      const newMap = new Map(prev);
      const status = newMap.get(toolCallId);
      if (status) {
        newMap.set(toolCallId, { ...status, completed: true, result });
      }
      return newMap;
    });
  };

  const handleStreamMessage = (event: AgentEvent) => {
    const response = event.response!;
    const messageContent = response.message?.content;
    const newContentItems = parseContentItems(messageContent);
    const messageId = response.message?.id;
    
    // If parsed content items are empty, skip this message
    if (newContentItems.length === 0) {
      return;
    }
    
    setMessages((prev) => {
      // Find if there's already a message with same messageId
      const existingIndex = prev.findIndex(msg => msg.messageId === messageId && messageId);
      
      if (existingIndex !== -1) {
        // Update existing message
        return prev.map((msg, idx) => {
          if (idx === existingIndex) {
            const existingItems = msg.contentItems || [];
            const mergedItems = mergeContentItems([...existingItems, ...newContentItems]);
            return { 
              ...msg, 
              content: mergedItems.map(item => item.content).join(''),
              contentItems: mergedItems,
              agentName: event.agent_name || msg.agentName,
              raw: event,
              rawEvents: [...msg.rawEvents, event]
            };
          }
          return msg;
        });
      } else if (streamingMessageIdRef.current) {
        // If there's streaming message reference (legacy compatibility)
        return prev.map((msg) => {
          if (msg.id === streamingMessageIdRef.current) {
            const existingItems = msg.contentItems || [];
            const mergedItems = mergeContentItems([...existingItems, ...newContentItems]);
            return { 
              ...msg, 
              content: mergedItems.map(item => item.content).join(''),
              contentItems: mergedItems,
              agentName: event.agent_name || msg.agentName,
              raw: event,
              messageId: messageId,
              rawEvents: [...msg.rawEvents, event]
            };
          }
          return msg;
        });
      } else {
        // Create new streaming message card
        const newMessageId = `stream_${Date.now()}`;
        streamingMessageIdRef.current = newMessageId;
        return [
          ...prev,
          {
            id: newMessageId,
            messageId: messageId,
            type: AgentEventType.RESPONSE,
            content: newContentItems.map(item => item.content).join(''),
            contentItems: newContentItems,
            isUser: false,
            messageType: response.message_type,
            status: response.status,
            timestamp: new Date(),
            agentName: event.agent_name,
            raw: event,
            rawEvents: [event],
          },
        ];
      }
    });
  };

  const handleNonStreamMessage = (event: AgentEvent) => {
    const response = event.response!;
    const messageId = response.message?.id;
    
    // If there was a streaming message in progress, close it
    streamingMessageIdRef.current = null;
    
    // Parse content items
    const contentItems = response.message?.content 
      ? parseContentItems(response.message.content)
      : [];
    
    // If parsed content items are empty, skip this message
    if (contentItems.length === 0) {
      return;
    }

    setMessages((prev) => {
      // Find if there's already a message with same messageId
      const existingIndex = prev.findIndex(msg => msg.messageId === messageId && messageId);
      
      if (existingIndex !== -1) {
        // Update existing message
        return prev.map((msg, idx) => {
          if (idx === existingIndex) {
            return { 
              ...msg, 
              content: contentItems.map(item => item.content).join(''),
              contentItems: contentItems,
              messageType: response.message_type,
              status: response.status,
              agentName: event.agent_name || msg.agentName,
              raw: event,
              rawEvents: [...msg.rawEvents, event]
            };
          }
          return msg;
        });
      } else {
        // Create new message
        const newMessage: MessageItem = {
          id: `msg_${Date.now()}_${Math.random()}`,
          messageId: messageId,
          type: event.type,
          content: contentItems.map(item => item.content).join(''),
          contentItems: contentItems,
          isUser: false,
          messageType: response.message_type,
          status: response.status,
          timestamp: new Date(),
          agentName: event.agent_name,
          raw: event,
          rawEvents: [event],
        };
        return [...prev, newMessage];
      }
    });
  };

  const handleClientToolCall = (event: AgentEvent) => {
    const clientToolCall = event.client_tool_call!;
    const toolCallId = clientToolCall.tool_call_id;
    
    // Create client_tool_call message, no toolCalls, only show client tool call
    const newMessage: MessageItem = {
      id: `client_tool_${Date.now()}_${toolCallId}`,
      type: AgentEventType.CLIENT_TOOL_CALL,
      content: '',
      isUser: false,
      timestamp: new Date(),
      agentName: event.agent_name,
      raw: event,
      rawEvents: [event],
      clientToolCall: clientToolCall,
      // Explicitly don't set toolCalls, ensure only client tool call card is shown
    };

    setMessages((prev) => {
      // Check if there's already a tool_call card with the same tool_call_id
      // If exists, remove it, only keep client_tool_call card
      const filteredMessages = prev.filter((msg) => {
        // If it's a regular tool_call card, check if it contains the same tool_call_id
        if (msg.toolCalls && msg.toolCalls.length > 0) {
          const hasSameToolCallId = msg.toolCalls.some(tc => tc.id === toolCallId);
          if (hasSameToolCallId) {
            console.log(`Removing duplicate tool_call card for tool_call_id: ${toolCallId}`);
            return false; // Remove this message
          }
        }
        return true;
      });
      
      return [...filteredMessages, newMessage];
    });
    
    streamingMessageIdRef.current = null;
  };

  const handleErrorMessage = (event: AgentEvent) => {
    const newMessage: MessageItem = {
      id: `error_${Date.now()}`,
      type: AgentEventType.ERROR,
      content: event.error || 'Unknown error',
      isUser: false,
      timestamp: new Date(),
      agentName: event.agent_name,
      raw: event,
      rawEvents: [event],
    };

    setMessages((prev) => [...prev, newMessage]);
    streamingMessageIdRef.current = null;
  };

  const handleSendClientToolResult = async (toolCallId: string, result: string) => {
    if (!wsService || !wsService.isConnected()) {
      message.error('Connection lost');
      return;
    }

    const resultEvent: AgentEvent = {
      task_id: taskId,
      type: AgentEventType.CLIENT_TOOL_RESULT,
      client_tool_result: {
        message: {
          role: 'tool',
          content: result,
          tool_call_id: toolCallId,
        },
      },
    };

    try {
      wsService.send(resultEvent);
      
      // Update message state, mark as submitted and save result
      setMessages((prev) => prev.map((msg) => {
        if (msg.clientToolCall?.tool_call_id === toolCallId) {
          return {
            ...msg,
            clientToolSubmitted: true,
            clientToolResult: result,
          };
        }
        return msg;
      }));
      
      message.success('Tool result sent');
    } catch (error) {
      message.error('Failed to send tool result');
      console.error('Failed to send client tool result:', error);
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !wsService || !wsService.isConnected()) {
      return;
    }

    // Reset scroll state when user sends a new message
    userScrolledRef.current = false;

    // Close previous streaming message
    streamingMessageIdRef.current = null;

    // Generate unique message_id
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Add user message to interface
    const userMessage: MessageItem = {
      id: `user_${Date.now()}`,
      messageId: messageId,
      type: AgentEventType.REQUEST,
      content: inputValue,
      isUser: true,
      timestamp: new Date(),
      rawEvents: [],
    };
    setMessages((prev) => [...prev, userMessage]);
    // Construct message to send
    const chatMessage: ChatMessage = {
      id: messageId,
      role: 'user',
      content: inputValue,
    };

    const requestEvent: AgentEvent = {
      task_id: taskId,
      type: AgentEventType.REQUEST,
      request: {
        agent_name: agentName!,
        messages: [chatMessage],
      },
    };

    try {
      wsService.send(requestEvent);
      setInputValue('');
    } catch (error) {
      message.error('Failed to send message');
      console.error('Failed to send message:', error);
    }
  };

  const getStatusIcon = (status?: string) => {
    switch (status) {
      case 'finished':
        return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
      case 'error':
        return <WarningOutlined style={{ color: '#ff4d4f' }} />;
      default:
        return null;
    }
  };

  const showEventDetails = (msg: MessageItem) => {
    setSelectedMessage(msg);
    setIsEventModalVisible(true);
  };

  // Render content items (distinguish thinking, text and answer)
  const renderContentItems = (msg: MessageItem) => {
    const items = msg.contentItems || [];
    
    // If no structured content, fallback to original content
    if (items.length === 0) {
      const textContent = typeof msg.content === 'string' 
        ? msg.content 
        : extractTextFromContent(msg.content);
      return textContent ? <span>{textContent}</span> : null;
    }

    return (
      <>
        {items.map((item, index) => {
          if (item.type === 'thinking') {
            return (
              <div
                key={index}
                style={{
                  backgroundColor: '#f0f5ff',
                  borderLeft: '3px solid #597ef7',
                  padding: '8px 12px',
                  marginBottom: '8px',
                  borderRadius: '0 4px 4px 0',
                  fontSize: '13px',
                  color: '#5c6b8a',
                }}
              >
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  marginBottom: '4px',
                  color: '#597ef7',
                  fontWeight: 500,
                  fontSize: '12px',
                }}>
                  <span style={{ marginRight: '4px' }}>💭</span>
                  Thinking...
                </div>
                <div style={{ 
                  whiteSpace: 'pre-wrap', 
                  wordBreak: 'break-word',
                  fontStyle: 'italic',
                }}>
                  {item.content}
                </div>
              </div>
            );
          }
          // text type - check if contains <answer> tag
          if (item.content.includes('<answer>') && item.content.includes('</answer>')) {
            return (
              <FinalAnswer
                key={index}
                content={item.content}
                citations={citationStore}
              />
            );
          }
          return (
            <div
              key={index}
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {item.content}
            </div>
          );
        })}
      </>
    );
  };

  const renderClientToolCallCard = (msg: MessageItem) => {
    const clientToolCall = msg.clientToolCall!;
    const toolCallId = clientToolCall.tool_call_id;
    const isSubmitted = msg.clientToolSubmitted || false;
    
    // Safely parse arguments
    let parsedArgs = {};
    try {
      if (clientToolCall.function.arguments) {
        parsedArgs = JSON.parse(clientToolCall.function.arguments);
      }
    } catch (e) {
      console.error('Failed to parse client tool call arguments:', e);
      parsedArgs = { raw: clientToolCall.function.arguments };
    }

    // If submitted, use saved result, otherwise use current input
    const displayValue = isSubmitted ? (msg.clientToolResult || '') : (clientToolInputs.get(toolCallId) || '');

    return (
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '16px' }}>
        <Badge
          count={
            <InfoCircleOutlined
              style={{ color: 'white', cursor: 'pointer', backgroundColor: 'rgba(34, 197, 94, 0.8)', borderRadius: '50%', padding: '3px' }}
              onClick={() => showEventDetails(msg)}
            />
          }
          offset={[-10, 10]}
        >
          <Card
            size="small"
            style={{ 
              minWidth: '420px', 
              maxWidth: '75%',
              borderRadius: '16px',
              border: 'none',
              boxShadow: '0 4px 20px rgba(34, 197, 94, 0.12)',
              overflow: 'hidden',
            }}
            styles={{
              header: {
                background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
                borderBottom: '1px solid rgba(34, 197, 94, 0.1)',
                padding: '14px 20px',
              },
              body: {
                padding: '16px 20px',
                background: '#fefffe',
              }
            }}
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 12px rgba(34, 197, 94, 0.3)',
                }}>
                  <ToolOutlined style={{ color: 'white', fontSize: '16px' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#166534' }}>
                    {msg.agentName || 'Client Tool Call'}
                  </div>
                  <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                    {clientToolCall.function.name}
                  </div>
                </div>
                {isSubmitted ? (
                  <Tag 
                    icon={<CheckCircleOutlined />}
                    style={{ 
                      borderRadius: '12px',
                      background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                      border: 'none',
                      color: 'white',
                      fontSize: '11px',
                    }}
                  >
                    Submitted
                  </Tag>
                ) : (
                  <Tag 
                    style={{ 
                      borderRadius: '12px',
                      background: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                      border: 'none',
                      color: 'white',
                      fontSize: '11px',
                    }}
                  >
                    Input Required
                  </Tag>
                )}
              </div>
            }
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text type="secondary" style={{ fontSize: '12px', color: '#64748b' }}>Parameters:</Text>
                <pre style={{ 
                  backgroundColor: '#f1f5f9', 
                  padding: '12px', 
                  borderRadius: '10px',
                  overflow: 'auto',
                  maxHeight: '200px',
                  marginTop: '6px',
                  fontSize: '12px',
                  border: '1px solid #e2e8f0',
                }}>
                  {JSON.stringify(parsedArgs, null, 2)}
                </pre>
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: '12px', color: '#64748b' }}>
                  {isSubmitted ? 'Submitted Result:' : 'Enter Result:'}
                </Text>
                <TextArea
                  value={displayValue}
                  onChange={(e) => {
                    if (!isSubmitted) {
                      setClientToolInputs((prev) => {
                        const newMap = new Map(prev);
                        newMap.set(toolCallId, e.target.value);
                        return newMap;
                      });
                    }
                  }}
                  onPressEnter={(e) => {
                    if (!e.shiftKey && !isSubmitted) {
                      e.preventDefault();
                      if (displayValue.trim()) {
                        handleSendClientToolResult(toolCallId, displayValue);
                      }
                    }
                  }}
                  placeholder={isSubmitted ? '' : 'Enter tool execution result... (Shift+Enter for new line, Enter to send)'}
                  autoSize={{ minRows: 2, maxRows: 6 }}
                  style={{ 
                    marginTop: '6px',
                    backgroundColor: isSubmitted ? '#f1f5f9' : '#fff',
                    borderRadius: '10px',
                    border: '1px solid #e2e8f0',
                  }}
                  disabled={isSubmitted}
                />
              </div>
              <Text style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'right' as const, display: 'block' }}>
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </Text>
            </Space>
          </Card>
        </Badge>
      </div>
    );
  };

  const renderToolCallCard = (msg: MessageItem) => {
    const toolCalls = msg.toolCalls || [];
    
    // Collect all batch search results for display in dedicated SearchResultsPanel
    const batchSearchResults: { toolCallId: string; queryResults: any[] }[] = [];
    // Collect all todo results for display in dedicated TodoPanel
    const todoResults: { toolCallId: string; items: any[] }[] = [];
    // Collect all shell results for display in dedicated ShellPanel
    const shellResults: { toolCallId: string; result: any }[] = [];
    // Collect all batch_open results for display in dedicated WebPagePanel
    const batchOpenResults: { toolCallId: string; pages: any[] }[] = [];
    // Collect all file results for display in dedicated FilePanel
    const fileResults: { toolCallId: string; result: any }[] = [];
    // Record tool call IDs that need to be filtered
    const specialToolCallIds = new Set<string>();

    // First collect results from all special tools
    toolCalls.forEach((toolCall) => {
      const status = toolCallStatuses.get(toolCall.id);
      const isCompleted = status?.completed || false;
      
      // Parse arguments
      let parsedArgs: any = {};
      try {
        if (toolCall.function.arguments) {
          parsedArgs = JSON.parse(toolCall.function.arguments);
        }
      } catch (e) {
        // ignore
      }

      // Check if this is a todo tool
      if (toolCall.function.name === 'todo') {
        if (isCompleted && status?.result) {
          const resultStr = typeof status.result === 'string' 
            ? status.result 
            : JSON.stringify(status.result, null, 2);
          if (isTodoResult(resultStr)) {
            const items = parseTodoResult(resultStr);
            if (items.length > 0) {
              todoResults.push({ toolCallId: toolCall.id, items });
              specialToolCallIds.add(toolCall.id);
            }
          }
        }
        // Even without results, filter out todo tool
        specialToolCallIds.add(toolCall.id);
      }
      
      // Check if this is a batch_search tool
      const isBatchSearch = toolCall.function.name === 'batch_web_surfer' && 
        parsedArgs && parsedArgs.action === 'batch_search';
      
      if (isBatchSearch) {
        if (isCompleted && status?.result) {
          const resultStr = typeof status.result === 'string' 
            ? status.result 
            : JSON.stringify(status.result, null, 2);
          if (isBatchSearchResult(resultStr)) {
            const queryResults = parseQueryResults(resultStr);
            if (queryResults.length > 0) {
              batchSearchResults.push({ toolCallId: toolCall.id, queryResults });
              specialToolCallIds.add(toolCall.id);
            }
          }
        }
        // Even without results, filter out batch_search tool
        specialToolCallIds.add(toolCall.id);
      }

      // Check if this is a shell tool
      if (toolCall.function.name === 'shell') {
        if (isCompleted && status?.result) {
          const resultStr = typeof status.result === 'string' 
            ? status.result 
            : JSON.stringify(status.result, null, 2);
          if (isShellResult(resultStr)) {
            const shellResult = parseShellResult(resultStr);
            if (shellResult) {
              shellResults.push({ toolCallId: toolCall.id, result: shellResult });
              specialToolCallIds.add(toolCall.id);
            }
          }
        }
        // Even without results, filter out shell tool
        specialToolCallIds.add(toolCall.id);
      }

      // Check if this is a batch_open tool
      const isBatchOpen = toolCall.function.name === 'batch_web_surfer' && 
        parsedArgs && parsedArgs.action === 'batch_open';
      
      if (isBatchOpen) {
        if (isCompleted && status?.result) {
          const resultStr = typeof status.result === 'string' 
            ? status.result 
            : JSON.stringify(status.result, null, 2);
          if (isBatchOpenResult(resultStr)) {
            const pages = parseBatchOpenResult(resultStr);
            if (pages.length > 0) {
              batchOpenResults.push({ toolCallId: toolCall.id, pages });
              specialToolCallIds.add(toolCall.id);
            }
          }
        }
        // Even without results, filter out batch_open tool
        specialToolCallIds.add(toolCall.id);
      }

      // Check if this is a file tool
      if (toolCall.function.name === 'file') {
        if (isCompleted && status?.result) {
          const resultStr = typeof status.result === 'string' 
            ? status.result 
            : JSON.stringify(status.result, null, 2);
          if (isFileResult(resultStr)) {
            const fileResult = parseFileResult(resultStr);
            if (fileResult) {
              fileResults.push({ toolCallId: toolCall.id, result: fileResult });
              specialToolCallIds.add(toolCall.id);
            }
          }
        }
        // Even without results, filter out file tool
        specialToolCallIds.add(toolCall.id);
      }
    });

    // Filter out special tools (todo and batch_search), they display in separate panels
    const otherToolCalls = toolCalls.filter(tc => !specialToolCallIds.has(tc.id));

    // Prepare Collapse items (only include other tools)
    const collapseItems = otherToolCalls.map((toolCall) => {
      const status = toolCallStatuses.get(toolCall.id);
      const isCompleted = status?.completed || false;
      
      // Safely parse arguments
      let parsedArgs = {};
      try {
        if (toolCall.function.arguments) {
          parsedArgs = JSON.parse(toolCall.function.arguments);
        }
      } catch (e) {
        console.error('Failed to parse tool call arguments:', e);
        parsedArgs = { raw: toolCall.function.arguments };
      }

      // Render execution result
      const renderResult = () => {
        if (!isCompleted || !status?.result) return null;
        
        const resultStr = typeof status.result === 'string' 
          ? status.result 
          : JSON.stringify(status.result, null, 2);

        // Default display method
        return (
          <div>
            <Text type="secondary" style={{ fontSize: '12px', color: '#64748b' }}>Result:</Text>
            <pre style={{ 
              backgroundColor: '#f0fdf4', 
              padding: '12px', 
              borderRadius: '10px',
              overflow: 'auto',
              maxHeight: '200px',
              border: '1px solid #bbf7d0',
              marginTop: '6px',
              fontSize: '12px',
            }}>
              {resultStr}
            </pre>
          </div>
        );
      };

      return {
        key: toolCall.id,
        label: (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {isCompleted ? (
              <div style={{
                width: '20px',
                height: '20px',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <CheckCircleOutlined style={{ color: 'white', fontSize: '11px' }} />
              </div>
            ) : (
              <div style={{
                width: '20px',
                height: '20px',
                borderRadius: '6px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <LoadingOutlined style={{ color: 'white', fontSize: '11px' }} spin />
              </div>
            )}
            <Text strong style={{ fontSize: '13px', color: '#334155' }}>{toolCall.function.name}</Text>
          </div>
        ),
        children: (
          <Space direction="vertical" style={{ width: '100%' }}>
            <div>
              <Text type="secondary" style={{ fontSize: '12px', color: '#64748b' }}>Parameters:</Text>
              <pre style={{ 
                backgroundColor: '#f1f5f9', 
                padding: '12px', 
                borderRadius: '10px',
                overflow: 'auto',
                maxHeight: '200px',
                marginTop: '6px',
                fontSize: '12px',
                border: '1px solid #e2e8f0',
              }}>
                {JSON.stringify(parsedArgs, null, 2)}
              </pre>
            </div>
            {renderResult()}
          </Space>
        ),
      };
    });

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
        {/* Batch search tool call cards */}
        {batchSearchResults.map(({ toolCallId, queryResults }) => (
          <SearchResultsPanel 
            key={toolCallId}
            queryResults={queryResults}
            title="Search Tool"
            agentName={msg.agentName}
            timestamp={msg.timestamp}
          />
        ))}

        {/* Batch open (web page) tool call cards */}
        {batchOpenResults.map(({ toolCallId, pages }) => (
          <WebPagePanel 
            key={toolCallId}
            pages={pages}
            title="Web Reader"
            agentName={msg.agentName}
            timestamp={msg.timestamp}
          />
        ))}
        
        {/* Todo tool call cards */}
        {todoResults.map(({ toolCallId, items }) => (
          <TodoPanel 
            key={toolCallId}
            items={items}
            title="Task Manager"
            agentName={msg.agentName}
            timestamp={msg.timestamp}
          />
        ))}

        {/* Shell tool call cards */}
        {shellResults.map(({ toolCallId, result }) => (
          <ShellPanel 
            key={toolCallId}
            result={result}
            title="Terminal"
            agentName={msg.agentName}
            timestamp={msg.timestamp}
          />
        ))}

        {/* File tool call cards */}
        {fileResults.map(({ toolCallId, result }) => (
          <FilePanel 
            key={toolCallId}
            result={result}
            title="File Tool"
            agentName={msg.agentName}
            timestamp={msg.timestamp}
          />
        ))}
        
        {/* Other tool call cards */}
        {collapseItems.length > 0 && (
          <Badge
            count={
              <InfoCircleOutlined
                style={{ color: 'white', cursor: 'pointer', backgroundColor: 'rgba(249, 115, 22, 0.8)', borderRadius: '50%', padding: '3px' }}
                onClick={() => showEventDetails(msg)}
              />
            }
            offset={[-10, 10]}
          >
            <Card
              size="small"
              style={{ 
                minWidth: '420px', 
                maxWidth: '75%',
                borderRadius: '16px',
                border: 'none',
                boxShadow: '0 4px 20px rgba(249, 115, 22, 0.12)',
                overflow: 'hidden',
              }}
              styles={{
                header: {
                  background: 'linear-gradient(135deg, #fff7ed 0%, #fed7aa 100%)',
                  borderBottom: '1px solid rgba(249, 115, 22, 0.1)',
                  padding: '14px 20px',
                },
                body: {
                  padding: '12px 20px',
                  background: '#fffbf7',
                }
              }}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{
                    width: '32px',
                    height: '32px',
                    borderRadius: '10px',
                    background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 4px 12px rgba(249, 115, 22, 0.3)',
                  }}>
                    <ToolOutlined style={{ color: 'white', fontSize: '16px' }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: '#9a3412' }}>
                      {msg.agentName || 'Tool Call'}
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                      {collapseItems.length} tool{collapseItems.length > 1 ? 's' : ''} executed
                    </div>
                  </div>
                </div>
              }
            >
              <Collapse 
                ghost 
                items={collapseItems}
                style={{ marginTop: '-8px' }}
              />
              <Text style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'right' as const, display: 'block', marginTop: '8px' }}>
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </Text>
            </Card>
          </Badge>
        )}
      </div>
    );
  };

  // Check if there are pending client_tools
  const hasPendingClientTools = () => {
    return messages.some(
      (msg) => 
        msg.type === AgentEventType.CLIENT_TOOL_CALL && 
        msg.clientToolCall && 
        !msg.clientToolSubmitted
    );
  };

  const renderMessageCard = (msg: MessageItem) => {
    // If client_tool_call, only show client tool call card, not tool_call card
    if (msg.type === AgentEventType.CLIENT_TOOL_CALL && msg.clientToolCall) {
      return renderClientToolCallCard(msg);
    }

    // If message contains tool_calls, use special tool_call card
    // Explicitly exclude CLIENT_TOOL_CALL type messages
    if (msg.toolCalls && msg.toolCalls.length > 0 && msg.type !== AgentEventType.CLIENT_TOOL_CALL) {
      return renderToolCallCard(msg);
    }

    if (msg.isUser) {
      return (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '16px' }}>
          <div
            style={{
              maxWidth: '70%',
              position: 'relative',
            }}
          >
            {msg.rawEvents.length > 0 && (
              <InfoCircleOutlined
                style={{ 
                  position: 'absolute',
                  top: '-8px',
                  right: '-8px',
                  color: 'white',
                  backgroundColor: 'rgba(102, 126, 234, 0.8)',
                  borderRadius: '50%',
                  padding: '4px',
                  fontSize: '10px',
                  cursor: 'pointer',
                  zIndex: 1,
                }}
                onClick={() => showEventDetails(msg)}
              />
            )}
            <div
              style={{
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                borderRadius: '20px 20px 4px 20px',
                padding: '12px 18px',
                boxShadow: '0 4px 12px rgba(102, 126, 234, 0.25)',
              }}
            >
              <div style={{ 
                whiteSpace: 'pre-wrap', 
                wordBreak: 'break-word',
                color: 'white',
                fontSize: '14px',
                lineHeight: '1.6',
              }}>
                {typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content, null, 2)}
              </div>
              <div style={{ 
                marginTop: '8px', 
                fontSize: '11px', 
                color: 'rgba(255,255,255,0.7)',
                textAlign: 'right',
              }}>
                {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '16px' }}>
        <div style={{ display: 'flex', gap: '12px', maxWidth: '75%' }}>
          {/* Avatar */}
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              background: msg.type === AgentEventType.ERROR 
                ? 'linear-gradient(135deg, #ff6b6b 0%, #ee5a5a 100%)'
                : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
            }}
          >
            {msg.type === AgentEventType.ERROR ? (
              <WarningOutlined style={{ color: 'white', fontSize: '16px' }} />
            ) : (
              <RobotOutlined style={{ color: 'white', fontSize: '16px' }} />
            )}
          </div>
          
          {/* Message content */}
          <div style={{ flex: 1, position: 'relative' }}>
            {msg.rawEvents.length > 0 && (
              <InfoCircleOutlined
                style={{ 
                  position: 'absolute',
                  top: '-8px',
                  right: '-8px',
                  color: '#667eea',
                  backgroundColor: 'white',
                  borderRadius: '50%',
                  padding: '4px',
                  fontSize: '10px',
                  cursor: 'pointer',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.1)',
                  zIndex: 1,
                }}
                onClick={() => showEventDetails(msg)}
              />
            )}
            
            {/* Agent name */}
            <div style={{ 
              marginBottom: '6px', 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px' 
            }}>
              <Text strong style={{ fontSize: '13px', color: '#374151' }}>
                {msg.type === AgentEventType.ERROR ? 'Error' : (msg.agentName || 'Agent')}
              </Text>
              {msg.status && getStatusIcon(msg.status)}
            </div>
            
            {/* Message bubble */}
            <div
              style={{
                backgroundColor: 'white',
                borderRadius: '4px 20px 20px 20px',
                padding: '14px 18px',
                boxShadow: '0 2px 12px rgba(0, 0, 0, 0.08)',
                border: msg.type === AgentEventType.ERROR ? '1px solid #ffccc7' : '1px solid rgba(0, 0, 0, 0.04)',
              }}
            >
              <div
                style={{
                  maxHeight: '500px',
                  overflow: 'auto',
                  fontSize: '14px',
                  lineHeight: '1.7',
                  color: '#1f2937',
                }}
              >
                {renderContentItems(msg)}
              </div>
            </div>
            
            {/* Timestamp */}
            <div style={{ 
              marginTop: '6px', 
              fontSize: '11px', 
              color: '#9ca3af',
            }}>
              {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (connecting && !connectionError) {
    return (
      <Layout style={{ height: '100vh' }}>
        <Header style={{ backgroundColor: 'white', padding: '0 16px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              height: '100%',
            }}
          >
            <Space>
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate('/')}
              >
                Back
              </Button>
              <Title level={4} style={{ margin: 0 }}>
                <RobotOutlined /> {agentName}
                <span style={{ marginLeft: '8px', fontSize: '14px', color: '#666' }}>
                  {chatMode === 'multi' ? <><TeamOutlined /> Multi-Agent</> : <><UserOutlined /> Single-Agent</>}
                </span>
              </Title>
            </Space>
            <Space>
              <EndpointConfig onSave={handleEndpointChange} />
              <Tag color="processing">Connecting...</Tag>
            </Space>
          </div>
        </Header>
        <Content
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            backgroundColor: '#f0f2f5',
          }}
        >
          <Spin size="large" tip="Connecting to Agent..." />
        </Content>
      </Layout>
    );
  }

  if (connectionError) {
    return (
      <Layout style={{ height: '100vh' }}>
        <Header style={{ backgroundColor: 'white', padding: '0 16px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              height: '100%',
            }}
          >
            <Space>
              <Button
                type="text"
                icon={<ArrowLeftOutlined />}
                onClick={() => navigate('/')}
              >
                Back
              </Button>
              <Title level={4} style={{ margin: 0 }}>
                <RobotOutlined /> {agentName}
                <span style={{ marginLeft: '8px', fontSize: '14px', color: '#666' }}>
                  {chatMode === 'multi' ? <><TeamOutlined /> Multi-Agent</> : <><UserOutlined /> Single-Agent</>}
                </span>
              </Title>
            </Space>
            <Space>
              <EndpointConfig onSave={handleEndpointChange} />
              <Tag color="error">Connection Failed</Tag>
            </Space>
          </div>
        </Header>
        <Content
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            backgroundColor: '#f0f2f5',
          }}
        >
          <Card style={{ maxWidth: '600px', textAlign: 'center' }}>
            <Space direction="vertical" size="large">
              <WarningOutlined style={{ fontSize: '48px', color: '#ff4d4f' }} />
              <Title level={3}>Connection Failed</Title>
              <Text type="secondary">{connectionError}</Text>
              <Space>
                <Button type="primary" onClick={() => {
                  setConnectionError('');
                  setConnecting(true);
                  initWebSocket();
                }}>
                  Retry
                </Button>
                <Button onClick={() => navigate('/')}>
                  Back to Home
                </Button>
              </Space>
            </Space>
          </Card>
        </Content>
      </Layout>
    );
  }

  return (
    <Layout style={{ height: '100vh', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
      <Header style={{ 
        backgroundColor: 'rgba(255, 255, 255, 0.95)', 
        padding: '0 24px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06)',
        backdropFilter: 'blur(8px)',
        borderBottom: '1px solid rgba(0, 0, 0, 0.06)',
      }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: '100%',
          }}
        >
          <Space size={16}>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate('/')}
              style={{ 
                borderRadius: '8px',
                height: '36px',
              }}
            >
              Back
            </Button>
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '10px',
              padding: '6px 16px',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              borderRadius: '20px',
            }}>
              <RobotOutlined style={{ color: 'white', fontSize: '18px' }} />
              <Title level={5} style={{ margin: 0, color: 'white', fontWeight: 600 }}>
                {agentName}
              </Title>
            </div>
          </Space>
          
          <Space size={12}>
            <EndpointConfig onSave={handleEndpointChange} />
            <Tag 
              color={wsService?.isConnected() ? 'success' : 'error'}
              style={{ 
                borderRadius: '12px', 
                padding: '2px 12px',
                fontWeight: 500,
              }}
            >
              {wsService?.isConnected() ? '● Connected' : '○ Disconnected'}
            </Tag>
          </Space>
        </div>
      </Header>

      <Content
        ref={contentRef}
        onScroll={handleScroll}
        style={{
          padding: '24px',
          background: 'linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%)',
          overflow: 'auto',
        }}
      >
        {messages.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              minHeight: '300px',
            }}
          >
            <div style={{
              width: '80px',
              height: '80px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: '20px',
              boxShadow: '0 8px 32px rgba(102, 126, 234, 0.3)',
            }}>
              <RobotOutlined style={{ fontSize: '36px', color: 'white' }} />
            </div>
            <Text style={{ fontSize: '18px', fontWeight: 500, color: '#374151', marginBottom: '8px' }}>
              Start chatting with {agentName}
            </Text>
            <Text style={{ color: '#9ca3af', fontSize: '14px' }}>
              Send a message to begin the conversation
            </Text>
          </div>
        ) : (
          messages.map((msg) => <div key={msg.id}>{renderMessageCard(msg)}</div>)
        )}
        <div ref={messagesEndRef} />
      </Content>

      <Footer style={{ 
        backgroundColor: 'rgba(255, 255, 255, 0.95)', 
        padding: '16px 24px',
        boxShadow: '0 -2px 8px rgba(0, 0, 0, 0.04)',
        backdropFilter: 'blur(8px)',
        borderTop: '1px solid rgba(0, 0, 0, 0.06)',
      }}>
        <div style={{ 
          display: 'flex', 
          gap: '12px',
          maxWidth: '900px',
          margin: '0 auto',
        }}>
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder={
              hasPendingClientTools() 
                ? "Please complete client tool input first..." 
                : "Type your message..."
            }
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ 
              flex: 1,
              borderRadius: '12px',
              padding: '10px 16px',
              fontSize: '14px',
              border: '1px solid #e5e7eb',
              boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
              resize: 'none',
            }}
            disabled={!wsService?.isConnected() || hasPendingClientTools()}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            disabled={!wsService?.isConnected() || !inputValue.trim() || hasPendingClientTools()}
            style={{
              height: '44px',
              width: '44px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              border: 'none',
              boxShadow: '0 4px 12px rgba(102, 126, 234, 0.4)',
            }}
          />
        </div>
      </Footer>

      {/* Raw AgentEvent Details Modal */}
      <Modal
        title={`Raw AgentEvent (${selectedMessage?.rawEvents.length || 0} events)`}
        open={isEventModalVisible}
        onCancel={() => setIsEventModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setIsEventModalVisible(false)}>
            Close
          </Button>,
        ]}
        width={900}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {selectedMessage?.rawEvents.map((event, index) => (
            <div key={index}>
              <Text strong>Event {index + 1}:</Text>
              <pre
                style={{
                  backgroundColor: '#f5f5f5',
                  padding: '16px',
                  borderRadius: '4px',
                  overflow: 'auto',
                  maxHeight: '400px',
                  marginTop: '8px',
                  marginBottom: index < (selectedMessage?.rawEvents.length || 0) - 1 ? '16px' : 0,
                }}
              >
                {JSON.stringify(event, null, 2)}
              </pre>
            </div>
          ))}
        </Space>
      </Modal>
    </Layout>
  );
};

export default ChatPage;

