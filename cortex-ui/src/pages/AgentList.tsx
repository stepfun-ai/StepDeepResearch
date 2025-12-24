import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Modal, Button, Spin, Typography, Alert, Dropdown } from 'antd';
import { MessageOutlined, RobotOutlined, ReloadOutlined, DownOutlined, TeamOutlined, UserOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { fetchAgents } from '../services/api';
import { AgentConfig } from '../types';
import { EndpointConfig } from '../components/EndpointConfig';

const { Title, Paragraph } = Typography;

const AgentList: React.FC = () => {
  const [agents, setAgents] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>('');
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [chatModes, setChatModes] = useState<Map<string, 'multi' | 'single'>>(new Map());
  const navigate = useNavigate();

  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      setLoading(true);
      setError('');
      const data = await fetchAgents();
      setAgents(data);
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Failed to load agent list';
      setError(errorMsg);
      console.error('Failed to fetch agents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCardClick = (agent: AgentConfig) => {
    setSelectedAgent(agent);
    setModalVisible(true);
  };

  const handleChatClick = (agent: AgentConfig, e: React.MouseEvent) => {
    e.stopPropagation();
    const mode = chatModes.get(agent.name) || 'multi';
    navigate(`/chat/${agent.name}?mode=${mode}`);
  };

  const getChatMode = (agentName: string): 'multi' | 'single' => {
    return chatModes.get(agentName) || 'multi';
  };

  const setChatMode = (agentName: string, mode: 'multi' | 'single') => {
    setChatModes(prev => {
      const newMap = new Map(prev);
      newMap.set(agentName, mode);
      return newMap;
    });
  };

  const handleModalClose = () => {
    setModalVisible(false);
    setSelectedAgent(null);
  };

  if (loading) {
    return (
      <div style={{ 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'center', 
        height: '100vh' 
      }}>
        <Spin size="large" tip="Loading..." />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', backgroundColor: '#f0f2f5', minHeight: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <Title level={2} style={{ margin: 0 }}>
          <RobotOutlined /> Agent List
        </Title>
        <EndpointConfig onSave={loadAgents} />
      </div>
      
      {error && (
        <Alert
          message="Loading Failed"
          description={error}
          type="error"
          showIcon
          closable
          onClose={() => setError('')}
          action={
            <Button size="small" icon={<ReloadOutlined />} onClick={loadAgents}>
              Retry
            </Button>
          }
          style={{ marginBottom: '16px' }}
        />
      )}
      
      <Row gutter={[16, 16]}>
        {agents.map((agent, index) => (
          <Col xs={24} sm={12} md={8} lg={6} key={index}>
            <Card
              hoverable
              onClick={() => handleCardClick(agent)}
              style={{ height: '100%', position: 'relative' }}
              actions={[
                <Button.Group key="chat-group">
                  <Button
                    type="primary"
                    icon={getChatMode(agent.name) === 'multi' ? <TeamOutlined /> : <UserOutlined />}
                    onClick={(e) => handleChatClick(agent, e)}
                  >
                    {getChatMode(agent.name) === 'multi' ? 'Multi-Agent Chat' : 'Single-Agent Chat'}
                  </Button>
                  <Dropdown
                    menu={{
                      items: [
                        {
                          key: 'multi',
                          icon: <TeamOutlined />,
                          label: 'Multi-Agent Chat',
                          onClick: () => setChatMode(agent.name, 'multi'),
                        },
                        {
                          key: 'single',
                          icon: <UserOutlined />,
                          label: 'Single-Agent Chat',
                          onClick: () => setChatMode(agent.name, 'single'),
                        },
                      ],
                      selectedKeys: [getChatMode(agent.name)],
                    }}
                    trigger={['click']}
                  >
                    <Button 
                      type="primary" 
                      icon={<DownOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Dropdown>
                </Button.Group>,
              ]}
            >
              <Card.Meta
                avatar={<RobotOutlined style={{ fontSize: '32px', color: '#1890ff' }} />}
                title={<strong>{agent.name || 'Unnamed Agent'}</strong>}
                description={
                  <>
                    <Paragraph
                      ellipsis={{ rows: 2 }}
                      style={{ marginBottom: '8px', minHeight: '44px' }}
                    >
                      {agent.description || 'No description'}
                    </Paragraph>
                    <div style={{ fontSize: '12px', color: '#999' }}>
                      <div>Type: {agent.agent_type || 'default'}</div>
                      <div>Model: {agent.model?.name || agent.model?.model_name || 'N/A'}</div>
                    </div>
                  </>
                }
              />
            </Card>
          </Col>
        ))}
      </Row>

      {agents.length === 0 && (
        <div style={{ 
          textAlign: 'center', 
          marginTop: '48px',
          fontSize: '16px',
          color: '#999'
        }}>
          No available agents
        </div>
      )}

      <Modal
        title={`Agent Config: ${selectedAgent?.name || ''}`}
        open={modalVisible}
        onCancel={handleModalClose}
        footer={[
          <Button key="close" onClick={handleModalClose}>
            Close
          </Button>,
          <Button
            key="chat"
            type="primary"
            icon={<MessageOutlined />}
            onClick={() => {
              if (selectedAgent) {
                handleModalClose();
                navigate(`/chat/${selectedAgent.name}`);
              }
            }}
          >
            Start Chat
          </Button>,
        ]}
        width={800}
      >
        <pre
          style={{
            backgroundColor: '#f5f5f5',
            padding: '16px',
            borderRadius: '4px',
            maxHeight: '500px',
            overflow: 'auto',
            fontSize: '13px',
          }}
        >
          {JSON.stringify(selectedAgent, null, 2)}
        </pre>
      </Modal>
    </div>
  );
};

export default AgentList;

