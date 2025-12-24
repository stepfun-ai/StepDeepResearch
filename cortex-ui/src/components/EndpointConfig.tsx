import React, { useState } from 'react';
import { Input, Button, Typography, message } from 'antd';
import { EditOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import { getStoredEndpoint } from '../services/api';

const { Text } = Typography;

interface EndpointConfigProps {
  onSave?: (endpoint: string) => void;
}

export const EndpointConfig: React.FC<EndpointConfigProps> = ({ onSave }) => {
  const [endpoint, setEndpoint] = useState<string>(() => {
    return getStoredEndpoint() || '';
  });
  const [isEditing, setIsEditing] = useState(false);

  const handleSave = () => {
    localStorage.setItem('api_endpoint', endpoint);
    setIsEditing(false);
    message.success('Endpoint saved');
    if (onSave) {
      onSave(endpoint);
    }
  };

  const handleCancel = () => {
    setEndpoint(getStoredEndpoint() || '');
    setIsEditing(false);
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'nowrap' }}>
      {isEditing ? (
        <>
          <Input
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            placeholder="http://localhost:8001"
            style={{ width: 250 }}
            size="small"
          />
          <Button
            type="primary"
            size="small"
            icon={<SaveOutlined />}
            onClick={handleSave}
          >
            Save
          </Button>
          <Button
            size="small"
            icon={<CloseOutlined />}
            onClick={handleCancel}
          >
            Cancel
          </Button>
        </>
      ) : (
        <>
          {endpoint && (
            <Text type="secondary" style={{ fontSize: '12px', maxWidth: '200px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} ellipsis>
              {endpoint}
            </Text>
          )}
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => setIsEditing(true)}
          >
            Configure Endpoint
          </Button>
        </>
      )}
    </div>
  );
};

