/**
 * SearchResultsPanel Component
 * Display search results from batch_search tool
 */

import React, { useState } from 'react';
import { Card, Collapse, Tag, Typography, Space, Tooltip, Empty } from 'antd';
import {
  SearchOutlined,
  ClockCircleOutlined,
  GlobalOutlined,
  ExpandOutlined,
  CompressOutlined,
} from '@ant-design/icons';
import { QueryResult, SearchResultItem } from '../types/citation';

const { Text, Paragraph, Link } = Typography;

interface SearchResultsPanelProps {
  queryResults: QueryResult[];
  title?: string;
  agentName?: string;
  timestamp?: Date;
}

/**
 * Single search result item component
 */
const SearchResultItemCard: React.FC<{ item: SearchResultItem; index: number }> = ({ item }) => {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div
      style={{
        padding: '12px',
        backgroundColor: '#fafafa',
        borderRadius: '8px',
        marginBottom: '8px',
        border: '1px solid #f0f0f0',
        transition: 'all 0.2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#1890ff';
        e.currentTarget.style.boxShadow = '0 2px 8px rgba(24, 144, 255, 0.15)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#f0f0f0';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={4}>
        {/* Title and citation index */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div style={{ flex: 1, marginRight: '8px' }}>
            <Link
              href={item.url}
              target="_blank"
              style={{ 
                fontSize: '14px', 
                fontWeight: 500,
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {item.title}
            </Link>
          </div>
          <Tooltip title={`Citation ID: ${item.cite_index}`}>
            <Tag 
              color="blue" 
              style={{ 
                fontSize: '10px', 
                padding: '0 4px',
                cursor: 'pointer',
                flexShrink: 0,
              }}
            >
              {item.cite_index}
            </Tag>
          </Tooltip>
        </div>
        
        {/* URL and metadata */}
        <Space size={12} wrap style={{ fontSize: '12px' }}>
          {item.site && (
            <span style={{ color: '#52c41a' }}>
              <GlobalOutlined style={{ marginRight: '4px' }} />
              {item.site}
            </span>
          )}
          {item.published_time && (
            <span style={{ color: '#8c8c8c' }}>
              <ClockCircleOutlined style={{ marginRight: '4px' }} />
              {item.published_time.split('T')[0]}
            </span>
          )}
        </Space>
        
        {/* Summary */}
        {item.snippet && (
          <Paragraph
            style={{
              fontSize: '13px',
              color: '#595959',
              margin: '4px 0 0 0',
              lineHeight: '1.6',
            }}
            ellipsis={!expanded ? { rows: 2 } : false}
          >
            {item.snippet}
          </Paragraph>
        )}
        
        {/* Full content (expandable) */}
        {item.content && item.content !== item.snippet && (
          <div style={{ marginTop: '4px' }}>
            <Text
              type="secondary"
              style={{ 
                fontSize: '12px', 
                cursor: 'pointer',
                color: '#1890ff',
              }}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <>
                  <CompressOutlined style={{ marginRight: '4px' }} />
                  Collapse
                </>
              ) : (
                <>
                  <ExpandOutlined style={{ marginRight: '4px' }} />
                  Show more
                </>
              )}
            </Text>
            {expanded && (
              <div
                style={{
                  marginTop: '8px',
                  padding: '8px',
                  backgroundColor: '#fff',
                  borderRadius: '4px',
                  border: '1px solid #e8e8e8',
                  maxHeight: '200px',
                  overflow: 'auto',
                }}
              >
                <pre
                  style={{
                    fontSize: '12px',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    margin: 0,
                    fontFamily: 'inherit',
                  }}
                >
                  {item.content}
                </pre>
              </div>
            )}
          </div>
        )}
      </Space>
    </div>
  );
};

/**
 * SearchResultsPanel main component
 */
const SearchResultsPanel: React.FC<SearchResultsPanelProps> = ({ 
  queryResults, 
  title = 'Search Results',
  agentName,
  timestamp,
}) => {
  if (!queryResults || queryResults.length === 0) {
    return (
      <Card size="small" style={{ marginBottom: '16px' }}>
        <Empty description="No search results" />
      </Card>
    );
  }
  
  // Calculate total results count
  const totalItems = queryResults.reduce((sum, qr) => sum + qr.items.length, 0);
  
  // Prepare Collapse items
  const collapseItems = queryResults.map((queryResult, index) => ({
    key: `query_${index}`,
    label: (
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <div style={{
          width: '24px',
          height: '24px',
          borderRadius: '6px',
          background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <SearchOutlined style={{ color: 'white', fontSize: '12px' }} />
        </div>
        <Text strong style={{ maxWidth: '280px', fontSize: '13px' }} ellipsis>
          {queryResult.query}
        </Text>
        <Tag 
          style={{ 
            borderRadius: '10px', 
            fontSize: '11px',
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            border: 'none',
            color: 'white',
          }}
        >
          {queryResult.items.length} results
        </Tag>
      </div>
    ),
    children: (
      <div style={{ padding: '4px 0' }}>
        {queryResult.items.length === 0 ? (
          <Text type="secondary">No results for this query</Text>
        ) : (
          queryResult.items.map((item, itemIndex) => (
            <SearchResultItemCard 
              key={item.cite_index || itemIndex} 
              item={item} 
              index={itemIndex}
            />
          ))
        )}
      </div>
    ),
  }));
  
  return (
    <Card
      size="small"
      style={{
        minWidth: '420px',
        maxWidth: '75%',
        borderRadius: '16px',
        border: 'none',
        boxShadow: '0 4px 20px rgba(59, 130, 246, 0.12)',
        overflow: 'hidden',
      }}
      styles={{
        header: {
          background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
          borderBottom: '1px solid rgba(59, 130, 246, 0.1)',
          padding: '14px 20px',
        },
        body: {
          padding: '12px 16px',
          background: '#fafbfc',
        }
      }}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '32px',
            height: '32px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(59, 130, 246, 0.3)',
          }}>
            <SearchOutlined style={{ color: 'white', fontSize: '16px' }} />
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '14px', color: '#1e40af' }}>
              {agentName ? `${agentName}` : title}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
              {queryResults.length} queries • {totalItems} results
            </div>
          </div>
        </div>
      }
    >
      <Collapse
        ghost
        defaultActiveKey={queryResults.length === 1 ? ['query_0'] : []}
        items={collapseItems}
        style={{ background: 'transparent' }}
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

export default SearchResultsPanel;
