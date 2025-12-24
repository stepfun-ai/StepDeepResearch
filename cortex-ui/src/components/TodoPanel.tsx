/**
 * TodoPanel Component
 * Display task list results from todo tool
 */

import React from 'react';
import { Card, Typography, Space, Tag, Progress, Tooltip, Timeline } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  SyncOutlined,
  UnorderedListOutlined,
  CalendarOutlined,
  LinkOutlined,
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

// Task status type
type TaskStatus = 'completed' | 'in_progress' | 'pending' | 'not_started';

// Single task item
export interface TodoItem {
  step: number;
  title: string;
  status: TaskStatus;
  description?: string;
  dependsOn?: number[];
  updatedAt?: string;
  createdAt?: string;
  priority?: 'high' | 'medium' | 'low';
}

// TodoPanel props
interface TodoPanelProps {
  items: TodoItem[];
  title?: string;
  totalTasks?: number;
  completedTasks?: number;
  agentName?: string;
  timestamp?: Date;
}

/**
 * Parse task list from todo_result XML string
 */
export function parseTodoResult(content: string): TodoItem[] {
  const items: TodoItem[] = [];
  
  // Normalize content - handle escaped newlines from JSON serialization
  const normalizedContent = content
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t');
  
  // Match each task line
  // Format: ✅ Step 1: Title 🟠
  // Status icons: ✅(completed) ⏳(pending) 🔄(in_progress) 🚫(blocked)
  // Priority icons: 🔴(critical) 🟠(high) 🟡(medium) 🔵(low)
  const taskRegex = /([✅⏳🔄🚫]) Step ([^\s:]+): ([^\n🔴🟠🟡🔵]+)([🔴🟠🟡🔵])?/g;
  let match;
  
  while ((match = taskRegex.exec(normalizedContent)) !== null) {
    const statusIcon = match[1];
    const stepId = match[2].trim();
    const step = parseInt(stepId, 10) || 0; // Support non-numeric step IDs
    const title = match[3].trim();
    const priorityIcon = match[4];
    
    // Parse status
    let status: TaskStatus = 'not_started';
    if (statusIcon === '✅') status = 'completed';
    else if (statusIcon === '⏳') status = 'pending';
    else if (statusIcon === '🔄') status = 'in_progress';
    else if (statusIcon === '🚫') status = 'pending'; // Map blocked to pending for display
    
    // Parse priority - match todo.py output format
    let priority: 'high' | 'medium' | 'low' | undefined;
    if (priorityIcon === '🔴') priority = 'high'; // critical -> high
    else if (priorityIcon === '🟠') priority = 'high'; // high
    else if (priorityIcon === '🟡') priority = 'medium'; // medium  
    else if (priorityIcon === '🔵') priority = 'low'; // low
    
    // Try to extract description and dependencies
    const taskBlock = normalizedContent.substring(match.index);
    const nextTaskMatch = taskBlock.substring(match[0].length).match(/[✅⏳🔄🚫] Step [^\s:]+:/);
    const taskContent = nextTaskMatch 
      ? taskBlock.substring(0, match[0].length + (nextTaskMatch.index || 0))
      : taskBlock;
    
    // Extract description (lines starting with 📝)
    const descMatch = taskContent.match(/📝\s*([^\n]+)/);
    const description = descMatch ? descMatch[1].trim() : undefined;
    
    // Extract dependencies (🔗 Depends on: [x, y])
    const depsMatch = taskContent.match(/🔗\s*Depends on:\s*\[([^\]]+)\]/);
    const dependsOn = depsMatch 
      ? depsMatch[1].split(',').map(d => parseInt(d.trim(), 10)).filter(n => !isNaN(n))
      : undefined;
    
    // Extract time - handle ISO format timestamps
    const updatedMatch = taskContent.match(/updated_at:\s*([\d\-T:]+)/);
    const createdMatch = taskContent.match(/created_at:\s*([\d\-T:]+)/);
    
    items.push({
      step: step || items.length + 1, // Use parsed step or fallback to sequential number
      title,
      status,
      description,
      dependsOn,
      priority,
      updatedAt: updatedMatch ? updatedMatch[1].trim() : undefined,
      createdAt: createdMatch ? createdMatch[1].trim() : undefined,
    });
  }
  
  return items.sort((a, b) => a.step - b.step);
}

/**
 * Check if content is todo result
 */
export function isTodoResult(content: string): boolean {
  // Normalize content for checking
  const normalizedContent = content.replace(/\\n/g, '\n');
  // Check for todo_result tags or characteristic patterns
  return normalizedContent.includes('<todo_result>') || 
         (normalizedContent.includes('Step') && normalizedContent.includes('📊') && normalizedContent.includes('tasks'));
}

/**
 * Get icon and color for status
 */
function getStatusConfig(status: TaskStatus) {
  switch (status) {
    case 'completed':
      return { icon: <CheckCircleOutlined />, color: '#52c41a', text: 'Completed' };
    case 'in_progress':
      return { icon: <SyncOutlined spin />, color: '#1890ff', text: 'In Progress' };
    case 'pending':
      return { icon: <ClockCircleOutlined />, color: '#faad14', text: 'Pending' };
    default:
      return { icon: <ClockCircleOutlined />, color: '#d9d9d9', text: 'Not Started' };
  }
}

/**
 * Get priority tag
 */
function getPriorityTag(priority?: 'high' | 'medium' | 'low') {
  if (!priority) return null;
  const config = {
    high: { color: 'red', text: 'High' },
    medium: { color: 'orange', text: 'Medium' },
    low: { color: 'green', text: 'Low' },
  };
  return <Tag color={config[priority].color} style={{ fontSize: '10px' }}>{config[priority].text}</Tag>;
}

/**
 * Format time
 */
function formatTime(timeStr?: string) {
  if (!timeStr) return null;
  try {
    // Ensure the time string is valid ISO format
    const cleanedTimeStr = timeStr.trim();
    const date = new Date(cleanedTimeStr);
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return cleanedTimeStr; // Return original string if parsing fails
    }
    return date.toLocaleString('en-US', { 
      month: '2-digit', 
      day: '2-digit', 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  } catch {
    return timeStr;
  }
}

/**
 * TodoPanel main component
 */
const TodoPanel: React.FC<TodoPanelProps> = ({ 
  items, 
  title = 'Task Manager',
  agentName,
  timestamp,
}) => {
  if (!items || items.length === 0) {
    return null;
  }
  
  // Task status statistics
  const completedCount = items.filter(i => i.status === 'completed').length;
  const inProgressCount = items.filter(i => i.status === 'in_progress').length;
  const totalCount = items.length;
  const progressPercent = Math.round((completedCount / totalCount) * 100);
  
  // Prepare Timeline items
  const timelineItems = items.map((item) => {
    const statusConfig = getStatusConfig(item.status);
    
    return {
      key: item.step,
      dot: statusConfig.icon,
      color: statusConfig.color,
      children: (
        <div style={{ paddingBottom: '8px' }}>
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            {/* Title row */}
            <Space wrap>
              <Text strong style={{ fontSize: '14px' }}>
                Step {item.step}: {item.title}
              </Text>
              <Tag color={statusConfig.color} style={{ fontSize: '11px' }}>
                {statusConfig.text}
              </Tag>
              {getPriorityTag(item.priority)}
            </Space>
            
            {/* Description */}
            {item.description && (
              <Paragraph 
                style={{ 
                  margin: '4px 0 0 0', 
                  color: '#666',
                  fontSize: '13px',
                }}
                ellipsis={{ rows: 2, expandable: true, symbol: 'more' }}
              >
                {item.description}
              </Paragraph>
            )}
            
            {/* Meta info */}
            <Space size={16} style={{ marginTop: '4px', fontSize: '12px', color: '#999' }}>
              {item.dependsOn && item.dependsOn.length > 0 && (
                <Tooltip title={`Depends on: ${item.dependsOn.join(', ')}`}>
                  <span>
                    <LinkOutlined style={{ marginRight: '4px' }} />
                    Deps: {item.dependsOn.join(', ')}
                  </span>
                </Tooltip>
              )}
              {item.updatedAt && (
                <Tooltip title={`Updated: ${item.updatedAt}`}>
                  <span>
                    <CalendarOutlined style={{ marginRight: '4px' }} />
                    {formatTime(item.updatedAt)}
                  </span>
                </Tooltip>
              )}
            </Space>
          </Space>
        </div>
      ),
    };
  });

  return (
    <Card
      size="small"
      style={{
        minWidth: '420px',
        maxWidth: '75%',
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
            <UnorderedListOutlined style={{ color: 'white', fontSize: '16px' }} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, fontSize: '14px', color: '#6b21a8' }}>
              {agentName || title}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
              {completedCount}/{totalCount} tasks completed
            </div>
          </div>
          {inProgressCount > 0 && (
            <Tag 
              icon={<SyncOutlined spin />}
              style={{ 
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
                border: 'none',
                color: 'white',
                fontSize: '11px',
              }}
            >
              {inProgressCount} active
            </Tag>
          )}
        </div>
      }
    >
      {/* Progress bar */}
      <div style={{ marginBottom: '20px' }}>
        <Progress 
          percent={progressPercent} 
          status={completedCount === totalCount ? 'success' : 'active'}
          strokeColor={{
            '0%': '#8b5cf6',
            '100%': '#22c55e',
          }}
          trailColor="#e5e7eb"
          format={() => (
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#6b21a8' }}>
              {progressPercent}%
            </span>
          )}
          style={{ marginBottom: 0 }}
        />
      </div>
      
      {/* Task timeline */}
      <Timeline
        items={timelineItems}
        style={{ marginTop: '8px' }}
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

export default TodoPanel;
