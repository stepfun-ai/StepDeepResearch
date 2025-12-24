/**
 * FinalAnswer Component
 * Renders final answer with citations, supports Markdown and \cite{} format
 */

import React, { useMemo } from 'react';
import { Card, Typography, Tooltip, Tag } from 'antd';
import {
  CheckCircleOutlined,
  LinkOutlined,
  BookOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { CitationStore, CitationInfo } from '../types/citation';

const { Text, Link } = Typography;

interface FinalAnswerProps {
  content: string;  // Content with <answer>...</answer> tags or plain answer
  citations: CitationStore;  // Citation info storage
}

/**
 * Extract content between <answer>...</answer> tags
 */
function extractAnswerContent(content: string): string {
  const answerMatch = content.match(/<answer>([\s\S]*?)<\/answer>/);
  if (answerMatch) {
    return answerMatch[1].trim();
  }
  // If no answer tag, return original content
  return content;
}

/**
 * Convert \cite{web_xxx} to HTML span tags before Markdown rendering
 * This allows rehype-raw to render them properly
 */
function preprocessCitations(content: string, citations: CitationStore): string {
  // Match \cite{web_xxxxx} format
  const citeRegex = /\\cite\{(web_[a-zA-Z0-9]+)\}/g;
  
  return content.replace(citeRegex, (_, citeIndex: string) => {
    const citation = citations.get(citeIndex);
    const shortId = citeIndex.replace('web_', '').substring(0, 4);
    
    if (citation) {
      // Create a clickable citation tag with data attributes
      return `<cite-tag data-cite-index="${citeIndex}" data-url="${encodeURIComponent(citation.url)}" data-title="${encodeURIComponent(citation.title || '')}" data-snippet="${encodeURIComponent(citation.snippet || '')}">${shortId}</cite-tag>`;
    } else {
      // Unknown citation
      return `<cite-tag data-cite-index="${citeIndex}" data-unknown="true">${shortId}</cite-tag>`;
    }
  });
}

/**
 * Custom Markdown rendering components
 */
const createMarkdownComponents = (_citations: CitationStore) => ({
  // Custom cite-tag rendering
  'cite-tag': ({ node, children, ...props }: any) => {
    const citeIndex = props['data-cite-index'];
    const isUnknown = props['data-unknown'] === 'true';
    
    if (isUnknown) {
      return (
        <Tooltip title={`Citation ${citeIndex} not found`}>
          <Tag
            style={{
              fontSize: '10px',
              padding: '0 6px',
              margin: '0 2px',
              verticalAlign: 'super',
              lineHeight: '1.2',
              opacity: 0.5,
              background: '#e5e7eb',
              border: 'none',
              color: '#6b7280',
              borderRadius: '10px',
            }}
          >
            {children}
          </Tag>
        </Tooltip>
      );
    }
    
    const url = decodeURIComponent(props['data-url'] || '');
    const title = decodeURIComponent(props['data-title'] || '');
    const snippet = decodeURIComponent(props['data-snippet'] || '');
    
    return (
      <Tooltip
        title={
          <div style={{ maxWidth: '320px' }}>
            <div style={{ fontWeight: 600, marginBottom: '6px', fontSize: '13px' }}>
              {title || 'No Title'}
            </div>
            {snippet && (
              <div style={{ 
                fontSize: '12px', 
                color: 'rgba(255,255,255,0.85)',
                marginBottom: '6px',
                lineHeight: 1.5,
              }}>
                {snippet.substring(0, 150)}
                {snippet.length > 150 ? '...' : ''}
              </div>
            )}
            <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.6)' }}>
              Click to visit source →
            </div>
          </div>
        }
        placement="top"
      >
        <Tag
          style={{
            cursor: 'pointer',
            fontSize: '10px',
            padding: '0 6px',
            margin: '0 2px',
            verticalAlign: 'super',
            lineHeight: '1.2',
            background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            border: 'none',
            color: 'white',
            borderRadius: '10px',
          }}
          onClick={() => window.open(url, '_blank')}
        >
          <LinkOutlined style={{ marginRight: '2px', fontSize: '9px' }} />
          {children}
        </Tag>
      </Tooltip>
    );
  },
  // Custom heading rendering
  h1: ({ children, ...props }: any) => (
    <h1 {...props} style={{ 
      borderBottom: '2px solid transparent',
      borderImage: 'linear-gradient(90deg, #22c55e 0%, #16a34a 50%, transparent 100%) 1',
      paddingBottom: '10px', 
      marginTop: '28px',
      fontWeight: 700,
      color: '#166534',
    }}>
      {children}
    </h1>
  ),
  h2: ({ children, ...props }: any) => (
    <h2 {...props} style={{ 
      borderBottom: '1px solid #dcfce7', 
      paddingBottom: '8px', 
      marginTop: '24px',
      fontWeight: 600,
      color: '#15803d',
    }}>
      {children}
    </h2>
  ),
  h3: ({ children, ...props }: any) => (
    <h3 {...props} style={{ marginTop: '20px', color: '#166534', fontWeight: 600 }}>
      {children}
    </h3>
  ),
  // Custom table styles
  table: ({ children, ...props }: any) => (
    <div style={{ overflowX: 'auto', marginBottom: '16px', borderRadius: '12px', border: '1px solid #dcfce7' }}>
      <table 
        {...props} 
        style={{ 
          width: '100%', 
          borderCollapse: 'collapse',
          fontSize: '14px',
        }}
      >
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }: any) => (
    <th 
      {...props} 
      style={{ 
        border: '1px solid #dcfce7',
        padding: '10px 14px',
        background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
        fontWeight: 600,
        textAlign: 'left',
        color: '#166534',
      }}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }: any) => (
    <td 
      {...props} 
      style={{ 
        border: '1px solid #dcfce7',
        padding: '10px 14px',
        color: '#374151',
      }}
    >
      {children}
    </td>
  ),
  // Custom code block
  code: ({ inline, className, children, ...props }: any) => {
    if (inline) {
      return (
        <code
          {...props}
          style={{
            background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
            padding: '3px 8px',
            borderRadius: '6px',
            fontSize: '13px',
            fontFamily: 'Consolas, Monaco, monospace',
            color: '#166534',
            border: '1px solid #bbf7d0',
          }}
        >
          {children}
        </code>
      );
    }
    return (
      <pre
        style={{
          backgroundColor: '#1e293b',
          padding: '16px',
          borderRadius: '12px',
          overflow: 'auto',
          fontSize: '13px',
          border: '1px solid #334155',
        }}
      >
        <code {...props} className={className} style={{ color: '#e2e8f0' }}>
          {children}
        </code>
      </pre>
    );
  },
  // Custom blockquote
  blockquote: ({ children, ...props }: any) => (
    <blockquote
      {...props}
      style={{
        borderLeft: '4px solid #22c55e',
        paddingLeft: '16px',
        margin: '16px 0',
        color: '#166534',
        background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
        padding: '14px 18px',
        borderRadius: '0 12px 12px 0',
      }}
    >
      {children}
    </blockquote>
  ),
  // Horizontal rule
  hr: ({ ...props }: any) => (
    <hr
      {...props}
      style={{
        border: 'none',
        borderTop: '1px solid #dcfce7',
        margin: '28px 0',
      }}
    />
  ),
});

/**
 * FinalAnswer main component
 */
const FinalAnswer: React.FC<FinalAnswerProps> = ({ content, citations }) => {
  // Extract answer content
  const answerContent = useMemo(() => extractAnswerContent(content), [content]);
  
  // Preprocess citations - convert \cite{web_xxx} to HTML tags
  const processedContent = useMemo(
    () => preprocessCitations(answerContent, citations),
    [answerContent, citations]
  );
  
  // Create Markdown components
  const components = useMemo(() => createMarkdownComponents(citations), [citations]);
  
  // Collect all used citations
  const usedCitations = useMemo(() => {
    const used: CitationInfo[] = [];
    const citeRegex = /\\cite\{(web_[a-zA-Z0-9]+)\}/g;
    let match;
    const seen = new Set<string>();
    
    while ((match = citeRegex.exec(answerContent)) !== null) {
      const citeIndex = match[1];
      if (!seen.has(citeIndex)) {
        seen.add(citeIndex);
        const citation = citations.get(citeIndex);
        if (citation) {
          used.push(citation);
        }
      }
    }
    
    return used;
  }, [answerContent, citations]);
  
  return (
    <Card
      size="small"
      style={{
        marginBottom: '16px',
        borderRadius: '16px',
        border: 'none',
        boxShadow: '0 4px 20px rgba(34, 197, 94, 0.15)',
        overflow: 'hidden',
      }}
      styles={{
        header: {
          background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
          borderBottom: '1px solid rgba(34, 197, 94, 0.15)',
          padding: '14px 20px',
        },
        body: {
          padding: '20px 24px',
          background: '#fefffe',
        }
      }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(34, 197, 94, 0.3)',
          }}>
            <CheckCircleOutlined style={{ color: 'white', fontSize: '18px' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: '15px', color: '#166534' }}>
              Final Answer
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
              Research completed
            </div>
          </div>
          {usedCitations.length > 0 && (
            <Tag 
              icon={<BookOutlined />}
              style={{ 
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                border: 'none',
                color: 'white',
                fontSize: '11px',
                padding: '2px 10px',
              }}
            >
              {usedCitations.length} citations
            </Tag>
          )}
        </div>
      }
    >
      <div className="final-answer-content">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={components}
        >
          {processedContent}
        </ReactMarkdown>
      </div>
      
      {/* Citation list */}
      {usedCitations.length > 0 && (
        <div
          style={{
            marginTop: '28px',
            paddingTop: '20px',
            borderTop: '1px solid #dcfce7',
          }}
        >
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px', 
            marginBottom: '14px',
          }}>
            <div style={{
              width: '24px',
              height: '24px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <BookOutlined style={{ color: 'white', fontSize: '12px' }} />
            </div>
            <Text strong style={{ color: '#1e40af', fontSize: '14px' }}>
              References
            </Text>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {usedCitations.map((citation) => (
              <div
                key={citation.cite_index}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  padding: '12px 14px',
                  backgroundColor: '#f8fafc',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  transition: 'all 0.2s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = '#f0fdf4';
                  e.currentTarget.style.borderColor = '#bbf7d0';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = '#f8fafc';
                  e.currentTarget.style.borderColor = '#e2e8f0';
                }}
              >
                <Tag 
                  style={{ 
                    flexShrink: 0, 
                    fontSize: '10px',
                    borderRadius: '8px',
                    background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                    border: 'none',
                    color: 'white',
                  }}
                >
                  {citation.cite_index.replace('web_', '').substring(0, 6)}
                </Tag>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Link
                    href={citation.url}
                    target="_blank"
                    style={{
                      fontSize: '13px',
                      display: '-webkit-box',
                      WebkitLineClamp: 1,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                      color: '#166534',
                      fontWeight: 500,
                    }}
                  >
                    {citation.title}
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
};

export default FinalAnswer;
