/**
 * WebPagePanel Component
 * Display web page content from batch_open tool
 */

import React, { useState } from 'react';
import { Card, Collapse, Tag, Typography, Space, Tooltip, Button } from 'antd';
import {
  GlobalOutlined,
  LinkOutlined,
  FileTextOutlined,
  ExpandOutlined,
  CompressOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  ExportOutlined,
} from '@ant-design/icons';
import { message } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const { Text, Link } = Typography;

// Web page result interface
export interface WebPageResult {
  url: string;
  title: string;
  snippet?: string;
  content?: string;
  host?: string;
  site?: string;
  success: boolean;
  error?: string;
}

interface WebPagePanelProps {
  pages: WebPageResult[];
  title?: string;
  agentName?: string;
  timestamp?: Date;
}

/**
 * Single web page card component
 */
const WebPageCard: React.FC<{ page: WebPageResult; index: number }> = ({ page, index }) => {
  const [expanded, setExpanded] = useState(false);
  
  const handleCopyContent = () => {
    if (page.content) {
      navigator.clipboard.writeText(page.content);
      message.success('Content copied to clipboard');
    }
  };

  const handleOpenUrl = () => {
    window.open(page.url, '_blank');
  };

  // Process markdown content - unescape \n to actual newlines
  const processedContent = page.content 
    ? page.content
        .replace(/\\n/g, '\n')  // Convert \n to actual newlines
        .replace(/\\t/g, '\t')  // Convert \t to actual tabs
        .replace(/\\\\/g, '\\') // Convert \\ to \
    : '';

  // Truncate content for preview
  const previewContent = processedContent 
    ? (processedContent.length > 500 ? processedContent.substring(0, 500) + '...' : processedContent)
    : '';
  
  return (
    <div
      style={{
        padding: '14px 16px',
        backgroundColor: '#fafbfc',
        borderRadius: '12px',
        marginBottom: '10px',
        border: '1px solid #e5e7eb',
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#a78bfa';
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(139, 92, 246, 0.1)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#e5e7eb';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {/* Header: Title and status */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <Tag 
                style={{ 
                  fontSize: '10px', 
                  padding: '0 6px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
                  border: 'none',
                  color: 'white',
                  flexShrink: 0,
                }}
              >
                #{index + 1}
              </Tag>
              {page.success ? (
                <Tag 
                  icon={<CheckCircleOutlined />}
                  style={{ 
                    fontSize: '10px',
                    borderRadius: '8px',
                    background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
                    border: 'none',
                    color: 'white',
                  }}
                >
                  Loaded
                </Tag>
              ) : (
                <Tag 
                  icon={<CloseCircleOutlined />}
                  style={{ 
                    fontSize: '10px',
                    borderRadius: '8px',
                    background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                    border: 'none',
                    color: 'white',
                  }}
                >
                  Failed
                </Tag>
              )}
            </div>
            <Link
              href={page.url}
              target="_blank"
              style={{ 
                fontSize: '14px', 
                fontWeight: 600,
                color: '#1e293b',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {page.title || 'Untitled Page'}
            </Link>
          </div>
          
          {/* Action buttons */}
          <Space size={4}>
            {page.content && (
              <Tooltip title="Copy content">
                <Button
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={handleCopyContent}
                  style={{ color: '#64748b' }}
                />
              </Tooltip>
            )}
            <Tooltip title="Open in new tab">
              <Button
                type="text"
                size="small"
                icon={<ExportOutlined />}
                onClick={handleOpenUrl}
                style={{ color: '#64748b' }}
              />
            </Tooltip>
          </Space>
        </div>
        
        {/* URL and site info */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {page.site && (
            <span style={{ 
              fontSize: '12px', 
              color: '#22c55e',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}>
              <GlobalOutlined />
              {page.site}
            </span>
          )}
          <span style={{ 
            fontSize: '11px', 
            color: '#94a3b8',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            maxWidth: '300px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            <LinkOutlined />
            {page.host || new URL(page.url).hostname}
          </span>
        </div>
        
        {/* Snippet */}
        {page.snippet && (
          <div style={{
            fontSize: '12px',
            color: '#64748b',
            backgroundColor: '#f1f5f9',
            padding: '8px 12px',
            borderRadius: '8px',
            borderLeft: '3px solid #8b5cf6',
          }}>
            {page.snippet}
          </div>
        )}
        
        {/* Content preview */}
        {page.content && (
          <div style={{ marginTop: '4px' }}>
            <div 
              style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between',
                marginBottom: '6px',
              }}
            >
              <Text type="secondary" style={{ fontSize: '11px', color: '#64748b' }}>
                <FileTextOutlined style={{ marginRight: '4px' }} />
                Page Content ({page.content.length.toLocaleString()} chars)
              </Text>
              <Button
                type="text"
                size="small"
                icon={expanded ? <CompressOutlined /> : <ExpandOutlined />}
                onClick={() => setExpanded(!expanded)}
                style={{ fontSize: '11px', color: '#8b5cf6', padding: '0 4px' }}
              >
                {expanded ? 'Collapse' : 'Expand'}
              </Button>
            </div>
            <div
              className="markdown-content"
              style={{
                backgroundColor: '#ffffff',
                padding: '16px',
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
                maxHeight: expanded ? '500px' : '150px',
                overflow: 'auto',
                transition: 'max-height 0.3s ease',
              }}
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  h1: ({node, ...props}) => <h1 style={{fontSize: '20px', fontWeight: 700, marginTop: '16px', marginBottom: '12px', color: '#1e293b', borderBottom: '2px solid #e2e8f0', paddingBottom: '8px'}} {...props} />,
                  h2: ({node, ...props}) => <h2 style={{fontSize: '18px', fontWeight: 600, marginTop: '14px', marginBottom: '10px', color: '#334155'}} {...props} />,
                  h3: ({node, ...props}) => <h3 style={{fontSize: '16px', fontWeight: 600, marginTop: '12px', marginBottom: '8px', color: '#475569'}} {...props} />,
                  h4: ({node, ...props}) => <h4 style={{fontSize: '14px', fontWeight: 600, marginTop: '10px', marginBottom: '6px', color: '#64748b'}} {...props} />,
                  p: ({node, ...props}) => <p style={{fontSize: '13px', lineHeight: '1.7', marginBottom: '10px', color: '#334155'}} {...props} />,
                  ul: ({node, ...props}) => <ul style={{fontSize: '13px', marginLeft: '20px', marginBottom: '10px', color: '#334155'}} {...props} />,
                  ol: ({node, ...props}) => <ol style={{fontSize: '13px', marginLeft: '20px', marginBottom: '10px', color: '#334155'}} {...props} />,
                  li: ({node, ...props}) => <li style={{marginBottom: '4px', lineHeight: '1.6'}} {...props} />,
                  code: ({node, inline, ...props}: any) => 
                    inline ? (
                      <code style={{backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: '4px', fontSize: '12px', fontFamily: 'monospace', color: '#dc2626'}} {...props} />
                    ) : (
                      <code style={{display: 'block', backgroundColor: '#f8fafc', padding: '12px', borderRadius: '6px', fontSize: '12px', fontFamily: 'monospace', overflowX: 'auto', border: '1px solid #e2e8f0'}} {...props} />
                    ),
                  pre: ({node, ...props}) => <pre style={{marginBottom: '10px', borderRadius: '6px', overflow: 'hidden'}} {...props} />,
                  blockquote: ({node, ...props}) => <blockquote style={{borderLeft: '3px solid #8b5cf6', paddingLeft: '12px', marginLeft: 0, marginBottom: '10px', color: '#64748b', fontStyle: 'italic', backgroundColor: '#faf5ff', padding: '8px 12px', borderRadius: '4px'}} {...props} />,
                  a: ({node, ...props}) => <a style={{color: '#8b5cf6', textDecoration: 'none', fontWeight: 500}} target="_blank" rel="noopener noreferrer" {...props} />,
                  img: ({node, ...props}) => <img style={{maxWidth: '100%', borderRadius: '8px', marginTop: '8px', marginBottom: '8px', border: '1px solid #e2e8f0'}} {...props} />,
                  table: ({node, ...props}) => <table style={{width: '100%', borderCollapse: 'collapse', marginBottom: '12px', fontSize: '13px'}} {...props} />,
                  thead: ({node, ...props}) => <thead style={{backgroundColor: '#f8fafc'}} {...props} />,
                  th: ({node, ...props}) => <th style={{border: '1px solid #e2e8f0', padding: '8px', textAlign: 'left', fontWeight: 600, color: '#334155'}} {...props} />,
                  td: ({node, ...props}) => <td style={{border: '1px solid #e2e8f0', padding: '8px', color: '#475569'}} {...props} />,
                  hr: ({node, ...props}) => <hr style={{border: 'none', borderTop: '1px solid #e2e8f0', margin: '16px 0'}} {...props} />,
                  strong: ({node, ...props}) => <strong style={{fontWeight: 700, color: '#1e293b'}} {...props} />,
                  em: ({node, ...props}) => <em style={{fontStyle: 'italic', color: '#475569'}} {...props} />,
                }}
              >
                {expanded ? processedContent : previewContent}
              </ReactMarkdown>
            </div>
          </div>
        )}
        
        {/* Error message */}
        {!page.success && page.error && (
          <div style={{
            fontSize: '12px',
            color: '#ef4444',
            backgroundColor: '#fef2f2',
            padding: '8px 12px',
            borderRadius: '8px',
            border: '1px solid #fecaca',
          }}>
            {page.error}
          </div>
        )}
      </Space>
    </div>
  );
};

/**
 * Parse batch_open result string
 */
export function parseBatchOpenResult(resultStr: string): WebPageResult[] {
  const pages: WebPageResult[] = [];
  
  // Match each <url_result> block
  const urlResultRegex = /<url_result[^>]*>([\s\S]*?)<\/url_result>/g;
  let match;
  
  while ((match = urlResultRegex.exec(resultStr)) !== null) {
    const block = match[1];
    
    // Extract URL
    const urlMatch = block.match(/<url>(.*?)<\/url>/);
    const url = urlMatch ? urlMatch[1].trim() : '';
    
    // Extract title
    const titleMatch = block.match(/<title>([\s\S]*?)<\/title>/);
    const title = titleMatch ? titleMatch[1].trim() : '';
    
    // Extract snippet
    const snippetMatch = block.match(/<snippet>([\s\S]*?)<\/snippet>/);
    const snippet = snippetMatch ? snippetMatch[1].trim() : undefined;
    
    // Extract content
    const contentMatch = block.match(/<content>([\s\S]*?)<\/content>/);
    const content = contentMatch ? contentMatch[1].trim() : undefined;
    
    // Extract host
    const hostMatch = block.match(/<host>(.*?)<\/host>/);
    const host = hostMatch ? hostMatch[1].trim() : undefined;
    
    // Extract site
    const siteMatch = block.match(/<site>(.*?)<\/site>/);
    const site = siteMatch ? siteMatch[1].trim() : undefined;
    
    // Check for error
    const errorMatch = block.match(/<error>([\s\S]*?)<\/error>/);
    const error = errorMatch ? errorMatch[1].trim() : undefined;
    
    if (url) {
      pages.push({
        url,
        title,
        snippet,
        content,
        host,
        site,
        success: !error,
        error,
      });
    }
  }
  
  return pages;
}

/**
 * Check if result is a batch_open result
 */
export function isBatchOpenResult(resultStr: string): boolean {
  return resultStr.includes('<batch_open_results>') || 
         (resultStr.includes('<url_result') && resultStr.includes('<content>'));
}

/**
 * WebPagePanel main component
 */
const WebPagePanel: React.FC<WebPagePanelProps> = ({
  pages,
  title = 'Web Pages',
  agentName,
  timestamp,
}) => {
  const [expandAll, setExpandAll] = useState(false);
  
  const successCount = pages.filter(p => p.success).length;
  const failureCount = pages.length - successCount;
  
  // Prepare collapse items
  const collapseItems = pages.map((page, index) => ({
    key: `page-${index}`,
    label: (
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
        <div style={{
          width: '22px',
          height: '22px',
          borderRadius: '6px',
          background: page.success 
            ? 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)'
            : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          {page.success ? (
            <CheckCircleOutlined style={{ color: 'white', fontSize: '12px' }} />
          ) : (
            <CloseCircleOutlined style={{ color: 'white', fontSize: '12px' }} />
          )}
        </div>
        <span style={{ 
          flex: 1, 
          overflow: 'hidden', 
          textOverflow: 'ellipsis', 
          whiteSpace: 'nowrap',
          fontSize: '13px',
          fontWeight: 500,
          color: '#334155',
        }}>
          {page.title || page.url}
        </span>
        {page.site && (
          <Tag style={{ 
            fontSize: '10px', 
            borderRadius: '6px',
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            color: '#16a34a',
          }}>
            {page.site}
          </Tag>
        )}
      </div>
    ),
    children: <WebPageCard page={page} index={index} />,
  }));
  
  return (
    <Card
      size="small"
      style={{
        minWidth: '450px',
        maxWidth: '80%',
        borderRadius: '16px',
        border: 'none',
        boxShadow: '0 4px 20px rgba(139, 92, 246, 0.12)',
        overflow: 'hidden',
      }}
      styles={{
        header: {
          background: 'linear-gradient(135deg, #f3e8ff 0%, #e9d5ff 100%)',
          borderBottom: '1px solid rgba(139, 92, 246, 0.1)',
          padding: '14px 20px',
        },
        body: {
          padding: '16px 20px',
          background: '#fafbfc',
        }
      }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(139, 92, 246, 0.3)',
          }}>
            <GlobalOutlined style={{ color: 'white', fontSize: '16px' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '14px', color: '#6b21a8' }}>
              {agentName || title}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
              {pages.length} page{pages.length !== 1 ? 's' : ''} loaded
            </div>
          </div>
          <Space size={6}>
            {successCount > 0 && (
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
                {successCount} success
              </Tag>
            )}
            {failureCount > 0 && (
              <Tag 
                icon={<CloseCircleOutlined />}
                style={{ 
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                  border: 'none',
                  color: 'white',
                  fontSize: '11px',
                }}
              >
                {failureCount} failed
              </Tag>
            )}
          </Space>
        </div>
      }
      extra={
        <Button
          type="text"
          size="small"
          icon={expandAll ? <CompressOutlined /> : <ExpandOutlined />}
          onClick={() => setExpandAll(!expandAll)}
          style={{ color: '#8b5cf6', fontSize: '12px' }}
        >
          {expandAll ? 'Collapse All' : 'Expand All'}
        </Button>
      }
    >
      <Collapse
        ghost
        items={collapseItems}
        defaultActiveKey={expandAll ? collapseItems.map(item => item.key) : (pages.length === 1 ? ['page-0'] : [])}
        style={{
          background: 'transparent',
        }}
      />
      
      {timestamp && (
        <div style={{ 
          marginTop: '12px', 
          paddingTop: '12px',
          borderTop: '1px solid #e5e7eb',
          fontSize: '11px', 
          color: '#9ca3af',
          textAlign: 'right',
        }}>
          {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      )}
    </Card>
  );
};

export default WebPagePanel;
