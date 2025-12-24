/**
 * ShellPanel Component
 * Display shell command execution results with elegant terminal-style UI
 */

import React, { useState } from 'react';
import { Card, Typography, Space, Tag, Tooltip } from 'antd';
import {
  CodeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExpandOutlined,
  CompressOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

export interface ShellResult {
  cmd: string;
  exitCode: number;
  stdout: string;
  stderr: string;
}

interface ShellPanelProps {
  result: ShellResult;
  title?: string;
  agentName?: string;
  timestamp?: Date;
}

/**
 * Parse shell result from XML string
 */
export const parseShellResult = (resultStr: string): ShellResult | null => {
  try {
    const cmdMatch = resultStr.match(/<cmd>([\s\S]*?)<\/cmd>/);
    const exitCodeMatch = resultStr.match(/<exit_code>(\d+)<\/exit_code>/);
    const stdoutMatch = resultStr.match(/<stdout>([\s\S]*?)<\/stdout>/);
    const stderrMatch = resultStr.match(/<stderr>([\s\S]*?)<\/stderr>/);

    if (!cmdMatch) return null;

    return {
      cmd: cmdMatch[1] || '',
      exitCode: exitCodeMatch ? parseInt(exitCodeMatch[1], 10) : 0,
      stdout: stdoutMatch ? stdoutMatch[1] : '',
      stderr: stderrMatch ? stderrMatch[1] : '',
    };
  } catch (e) {
    return null;
  }
};

/**
 * Check if content is shell result
 */
export const isShellResult = (content: string): boolean => {
  return content.includes('<cmd>') && content.includes('<exit_code>');
};

/**
 * ShellPanel main component
 */
const ShellPanel: React.FC<ShellPanelProps> = ({
  result,
  title = 'Terminal',
  agentName,
  timestamp,
}) => {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const isSuccess = result.exitCode === 0;
  const hasOutput = result.stdout.trim() || result.stderr.trim();

  const copyCommand = () => {
    navigator.clipboard.writeText(result.cmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const maxOutputHeight = expanded ? 'none' : '200px';

  return (
    <Card
      size="small"
      style={{
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
        borderRadius: '12px',
        border: 'none',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.15)',
        overflow: 'hidden',
        minWidth: '450px',
        maxWidth: '800px',
      }}
      bodyStyle={{ padding: 0 }}
    >
      {/* Terminal header */}
      <div
        style={{
          background: 'linear-gradient(90deg, #2d2d44 0%, #1f1f35 100%)',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        <Space size={8}>
          {/* Traffic light buttons */}
          <Space size={6}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ff5f57' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#febc2e' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#28c840' }} />
          </Space>
          <Space size={6} style={{ marginLeft: 12 }}>
            <CodeOutlined style={{ color: '#7c7c9a', fontSize: 14 }} />
            <Text style={{ color: '#a8a8c0', fontSize: 13, fontWeight: 500 }}>
              {agentName ? `${agentName} • ${title}` : title}
            </Text>
          </Space>
        </Space>
        <Space size={12}>
          <Tag
            icon={isSuccess ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
            color={isSuccess ? 'success' : 'error'}
            style={{ 
              margin: 0, 
              borderRadius: 12,
              fontSize: 11,
              padding: '0 8px',
            }}
          >
            {isSuccess ? 'Success' : `Exit: ${result.exitCode}`}
          </Tag>
          {timestamp && (
            <Tooltip title={timestamp.toLocaleString()}>
              <ClockCircleOutlined style={{ color: '#7c7c9a', fontSize: 12 }} />
            </Tooltip>
          )}
        </Space>
      </div>

      {/* Command section */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <Text style={{ color: '#50fa7b', fontFamily: 'Monaco, Menlo, monospace', fontSize: 13, flexShrink: 0 }}>
            $
          </Text>
          <div style={{ flex: 1, position: 'relative' }}>
            <Text
              style={{
                color: '#f8f8f2',
                fontFamily: 'Monaco, Menlo, monospace',
                fontSize: 13,
                wordBreak: 'break-all',
                lineHeight: 1.5,
              }}
            >
              {result.cmd}
            </Text>
          </div>
          <Tooltip title={copied ? 'Copied!' : 'Copy command'}>
            <CopyOutlined
              onClick={copyCommand}
              style={{
                color: copied ? '#50fa7b' : '#7c7c9a',
                cursor: 'pointer',
                fontSize: 14,
                transition: 'color 0.2s',
                flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                if (!copied) e.currentTarget.style.color = '#a8a8c0';
              }}
              onMouseLeave={(e) => {
                if (!copied) e.currentTarget.style.color = '#7c7c9a';
              }}
            />
          </Tooltip>
        </div>
      </div>

      {/* Output section */}
      {hasOutput && (
        <div style={{ padding: '12px 16px' }}>
          {/* stdout */}
          {result.stdout.trim() && (
            <div
              style={{
                maxHeight: maxOutputHeight,
                overflow: expanded ? 'visible' : 'auto',
                marginBottom: result.stderr.trim() ? 12 : 0,
              }}
            >
              <pre
                style={{
                  margin: 0,
                  padding: '10px 12px',
                  backgroundColor: 'rgba(80, 250, 123, 0.08)',
                  borderRadius: 8,
                  border: '1px solid rgba(80, 250, 123, 0.2)',
                  color: '#f8f8f2',
                  fontFamily: 'Monaco, Menlo, monospace',
                  fontSize: 12,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {result.stdout}
              </pre>
            </div>
          )}

          {/* stderr */}
          {result.stderr.trim() && (
            <div
              style={{
                maxHeight: maxOutputHeight,
                overflow: expanded ? 'visible' : 'auto',
              }}
            >
              <div style={{ marginBottom: 4 }}>
                <Text style={{ color: '#ff5555', fontSize: 11, fontWeight: 500 }}>
                  stderr
                </Text>
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: '10px 12px',
                  backgroundColor: 'rgba(255, 85, 85, 0.08)',
                  borderRadius: 8,
                  border: '1px solid rgba(255, 85, 85, 0.2)',
                  color: '#ff5555',
                  fontFamily: 'Monaco, Menlo, monospace',
                  fontSize: 12,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {result.stderr}
              </pre>
            </div>
          )}

          {/* Expand/Collapse toggle */}
          {(result.stdout.length > 300 || result.stderr.length > 300) && (
            <div
              style={{
                marginTop: 8,
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <Tooltip title={expanded ? 'Collapse' : 'Expand'}>
                <div
                  onClick={() => setExpanded(!expanded)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '4px 12px',
                    borderRadius: 12,
                    backgroundColor: 'rgba(255, 255, 255, 0.05)',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                  }}
                >
                  {expanded ? (
                    <CompressOutlined style={{ color: '#7c7c9a', fontSize: 12 }} />
                  ) : (
                    <ExpandOutlined style={{ color: '#7c7c9a', fontSize: 12 }} />
                  )}
                  <Text style={{ color: '#7c7c9a', fontSize: 11 }}>
                    {expanded ? 'Collapse' : 'Expand'}
                  </Text>
                </div>
              </Tooltip>
            </div>
          )}
        </div>
      )}

      {/* Empty output hint */}
      {!hasOutput && (
        <div
          style={{
            padding: '16px',
            textAlign: 'center',
          }}
        >
          <Text style={{ color: '#7c7c9a', fontSize: 12, fontStyle: 'italic' }}>
            Command completed with no output
          </Text>
        </div>
      )}
    </Card>
  );
};

export default ShellPanel;
