/**
 * FilePanel Component
 * Display file tool execution results with elegant UI
 */

import React, { useState } from 'react';
import { Card, Typography, Space, Tag, Tooltip } from 'antd';
import {
  FileOutlined,
  FileTextOutlined,
  FolderOutlined,
  EditOutlined,
  PlusOutlined,
  InfoCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExpandOutlined,
  CompressOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

export interface FileResult {
  action: string;
  path: string;
  size?: string;
  content?: string;
  error?: string;
  note?: string;
  entries?: string[];  // For list action
  modified?: string;
  created?: string;
}

interface FilePanelProps {
  result: FileResult;
  title?: string;
  agentName?: string;
  timestamp?: Date;
}

/**
 * Parse file result from XML-like string
 */
export const parseFileResult = (resultStr: string): FileResult | null => {
  try {
    // Try to extract the actual file_result content from nested JSON structure
    let actualContent = resultStr;
    
    // Handle nested JSON structure like {"type":"tool_result","content":[{"type":"text","text":"<file_result>..."}]}
    if (resultStr.includes('"type":"tool_result"') || resultStr.includes('"tool_result"')) {
      try {
        const parsed = JSON.parse(resultStr);
        if (parsed.content && Array.isArray(parsed.content)) {
          for (const item of parsed.content) {
            if (item.type === 'text' && item.text) {
              actualContent = item.text;
              break;
            }
          }
        }
      } catch {
        // If JSON parse fails, try regex extraction
        const textMatch = resultStr.match(/"text"\s*:\s*"([\s\S]*?)(?:"\s*}|\"\s*,)/);
        if (textMatch) {
          // Unescape the JSON string
          actualContent = textMatch[1].replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\\/g, '\\');
        }
      }
    }

    // Check if it's a file_result
    if (!actualContent.includes('<file_result>')) return null;

    const actionMatch = actualContent.match(/action:\s*(\w+)/);
    const pathMatch = actualContent.match(/path:\s*(.+?)(?:\n|$)/);
    const sizeMatch = actualContent.match(/size:\s*(.+?)(?:\n|$)/);
    const errorMatch = actualContent.match(/error:\s*(.+?)(?:\n|<\/file_result>)/s);
    const noteMatch = actualContent.match(/note:\s*(.+?)(?:\n|$)/);
    const modifiedMatch = actualContent.match(/modified:\s*(.+?)(?:\n|$)/);
    const createdMatch = actualContent.match(/created:\s*(.+?)(?:\n|$)/);

    if (!actionMatch || !pathMatch) return null;

    const result: FileResult = {
      action: actionMatch[1],
      path: pathMatch[1].trim(),
    };

    if (sizeMatch) result.size = sizeMatch[1].trim();
    if (errorMatch) result.error = errorMatch[1].trim();
    if (noteMatch) result.note = noteMatch[1].trim();
    if (modifiedMatch) result.modified = modifiedMatch[1].trim();
    if (createdMatch) result.created = createdMatch[1].trim();

    // Extract content for read action (between ``` markers)
    const contentMatch = actualContent.match(/```\n?([\s\S]*?)\n?```/);
    if (contentMatch) {
      result.content = contentMatch[1];
    }

    // Extract entries for list action
    if (actionMatch[1] === 'list') {
      const entriesSection = actualContent.match(/-{20,}\n([\s\S]*?)<\/file_result>/);
      if (entriesSection) {
        const lines = entriesSection[1].trim().split('\n').filter(line => line.trim());
        result.entries = lines;
      }
    }

    return result;
  } catch (e) {
    return null;
  }
};

/**
 * Check if content is file result
 */
export const isFileResult = (content: string): boolean => {
  // Check for direct file_result tag
  if (content.includes('<file_result>') && content.includes('action:')) {
    return true;
  }
  // Check for nested JSON structure containing file_result
  if (content.includes('"tool_result"') && content.includes('file_result')) {
    return true;
  }
  return false;
};

/**
 * Get icon based on action type
 */
const getActionIcon = (action: string) => {
  switch (action.toLowerCase()) {
    case 'read':
      return <FileTextOutlined />;
    case 'write':
      return <EditOutlined />;
    case 'append':
      return <PlusOutlined />;
    case 'list':
      return <FolderOutlined />;
    case 'stat':
      return <InfoCircleOutlined />;
    default:
      return <FileOutlined />;
  }
};

/**
 * Get action display text
 */
const getActionText = (action: string): string => {
  switch (action.toLowerCase()) {
    case 'read':
      return 'Read File';
    case 'write':
      return 'Write File';
    case 'append':
      return 'Append File';
    case 'list':
      return 'List Directory';
    case 'stat':
      return 'File Info';
    default:
      return action;
  }
};

/**
 * Get action color
 */
const getActionColor = (action: string): string => {
  switch (action.toLowerCase()) {
    case 'read':
      return '#3b82f6';
    case 'write':
      return '#22c55e';
    case 'append':
      return '#f59e0b';
    case 'list':
      return '#8b5cf6';
    case 'stat':
      return '#6366f1';
    default:
      return '#64748b';
  }
};

/**
 * FilePanel main component
 */
const FilePanel: React.FC<FilePanelProps> = ({
  result,
  title = 'File Tool',
  agentName,
  timestamp,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasError = !!result.error;
  const hasContent = !!result.content;
  const hasEntries = result.entries && result.entries.length > 0;
  const actionColor = getActionColor(result.action);

  const copyPath = () => {
    navigator.clipboard.writeText(result.path);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const copyContent = () => {
    if (result.content) {
      navigator.clipboard.writeText(result.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Extract filename from path
  const filename = result.path.split('/').pop() || result.path;

  return (
    <Card
      size="small"
      style={{
        background: '#ffffff',
        borderRadius: '16px',
        border: 'none',
        boxShadow: '0 4px 20px rgba(99, 102, 241, 0.12)',
        overflow: 'hidden',
        minWidth: '420px',
        maxWidth: '800px',
      }}
      styles={{
        body: { padding: 0 }
      }}
    >
      {/* Header */}
      <div
        style={{
          background: `linear-gradient(135deg, ${actionColor}15 0%, ${actionColor}08 100%)`,
          padding: '14px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: `1px solid ${actionColor}20`,
        }}
      >
        <Space size={12}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: '10px',
              background: `linear-gradient(135deg, ${actionColor} 0%, ${actionColor}cc 100%)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: `0 4px 12px ${actionColor}40`,
            }}
          >
            {React.cloneElement(getActionIcon(result.action), { style: { color: 'white', fontSize: '16px' } })}
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontWeight: 600, fontSize: '14px', color: '#1e293b' }}>
                {agentName ? `${agentName}` : title}
              </span>
              <Tag 
                style={{ 
                  margin: 0, 
                  borderRadius: '6px', 
                  fontSize: '11px',
                  background: `${actionColor}15`,
                  color: actionColor,
                  border: `1px solid ${actionColor}30`,
                  fontWeight: 500,
                }}
              >
                {result.action.toUpperCase()}
              </Tag>
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
              {getActionText(result.action)} • {result.size || 'N/A'}
            </div>
          </div>
        </Space>
        <Space size={12}>
          <Tag
            icon={hasError ? <CloseCircleOutlined /> : <CheckCircleOutlined />}
            color={hasError ? 'error' : 'success'}
            style={{
              margin: 0,
              borderRadius: 12,
              fontSize: 11,
              padding: '0 8px',
            }}
          >
            {hasError ? 'Error' : 'Success'}
          </Tag>
          {timestamp && (
            <Tooltip title={timestamp.toLocaleString()}>
              <ClockCircleOutlined style={{ color: '#9ca3af', fontSize: 12 }} />
            </Tooltip>
          )}
        </Space>
      </div>

      {/* Path section */}
      <div
        style={{
          padding: '12px 20px',
          background: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Space size={8}>
            <FileOutlined style={{ color: actionColor, fontSize: 14 }} />
            <Text
              style={{
                fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
                fontSize: '13px',
                color: '#334155',
                wordBreak: 'break-all',
              }}
              ellipsis={{ tooltip: result.path }}
            >
              {filename}
            </Text>
          </Space>
          <Tooltip title={copied ? 'Copied!' : 'Copy path'}>
            <CopyOutlined
              onClick={copyPath}
              style={{
                color: copied ? '#22c55e' : '#9ca3af',
                cursor: 'pointer',
                fontSize: 14,
                transition: 'color 0.2s',
              }}
            />
          </Tooltip>
        </div>
        <Text
          type="secondary"
          style={{
            fontSize: '11px',
            display: 'block',
            marginTop: '4px',
            fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
          }}
          ellipsis={{ tooltip: result.path }}
        >
          {result.path}
        </Text>
      </div>

      {/* Error section */}
      {hasError && (
        <div
          style={{
            padding: '12px 20px',
            background: '#fef2f2',
            borderBottom: '1px solid #fecaca',
          }}
        >
          <Text style={{ color: '#dc2626', fontSize: '13px' }}>
            <CloseCircleOutlined style={{ marginRight: 8 }} />
            {result.error}
          </Text>
        </div>
      )}

      {/* Note section */}
      {result.note && !hasError && (
        <div
          style={{
            padding: '8px 20px',
            background: '#fefce8',
            borderBottom: '1px solid #fef08a',
          }}
        >
          <Text style={{ color: '#a16207', fontSize: '12px' }}>
            <InfoCircleOutlined style={{ marginRight: 8 }} />
            {result.note}
          </Text>
        </div>
      )}

      {/* Stat info section */}
      {result.action === 'stat' && (result.modified || result.created) && (
        <div style={{ padding: '12px 20px', background: '#ffffff' }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            {result.modified && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary" style={{ fontSize: '12px' }}>Modified:</Text>
                <Text style={{ fontSize: '12px', fontFamily: 'monospace' }}>{result.modified}</Text>
              </div>
            )}
            {result.created && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary" style={{ fontSize: '12px' }}>Created:</Text>
                <Text style={{ fontSize: '12px', fontFamily: 'monospace' }}>{result.created}</Text>
              </div>
            )}
          </Space>
        </div>
      )}

      {/* List entries section */}
      {hasEntries && (
        <div style={{ padding: '12px 20px', background: '#ffffff' }}>
          <div style={{ marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              Entries ({result.entries!.length})
            </Text>
            <Text
              style={{
                fontSize: '12px',
                color: actionColor,
                cursor: 'pointer',
              }}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <>
                  <CompressOutlined style={{ marginRight: 4 }} /> Collapse
                </>
              ) : (
                <>
                  <ExpandOutlined style={{ marginRight: 4 }} /> Expand
                </>
              )}
            </Text>
          </div>
          <div
            style={{
              maxHeight: expanded ? 'none' : '150px',
              overflow: 'auto',
              background: '#f8fafc',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
            }}
          >
            <pre
              style={{
                margin: 0,
                padding: '12px',
                fontSize: '12px',
                fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {result.entries!.join('\n')}
            </pre>
          </div>
        </div>
      )}

      {/* Content section */}
      {hasContent && (
        <div style={{ padding: '12px 20px', background: '#ffffff' }}>
          <div style={{ marginBottom: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text type="secondary" style={{ fontSize: '12px' }}>
              Content
            </Text>
            <Space size={12}>
              <Tooltip title="Copy content">
                <CopyOutlined
                  onClick={copyContent}
                  style={{
                    color: '#9ca3af',
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                />
              </Tooltip>
              <Text
                style={{
                  fontSize: '12px',
                  color: actionColor,
                  cursor: 'pointer',
                }}
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? (
                  <>
                    <CompressOutlined style={{ marginRight: 4 }} /> Collapse
                  </>
                ) : (
                  <>
                    <ExpandOutlined style={{ marginRight: 4 }} /> Expand
                  </>
                )}
              </Text>
            </Space>
          </div>
          <div
            style={{
              maxHeight: expanded ? '600px' : '200px',
              overflow: 'auto',
              background: '#1e293b',
              borderRadius: '8px',
              border: '1px solid #334155',
            }}
          >
            <pre
              style={{
                margin: 0,
                padding: '16px',
                fontSize: '13px',
                fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                color: '#e2e8f0',
              }}
            >
              {result.content}
            </pre>
          </div>
        </div>
      )}

      {/* Timestamp footer */}
      {timestamp && (
        <div
          style={{
            padding: '8px 20px',
            borderTop: '1px solid #e2e8f0',
            background: '#fafafa',
          }}
        >
          <Text style={{ fontSize: '11px', color: '#9ca3af', textAlign: 'right', display: 'block' }}>
            {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </Text>
        </div>
      )}
    </Card>
  );
};

export default FilePanel;
