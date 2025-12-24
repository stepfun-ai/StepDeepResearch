import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import AgentList from './pages/AgentList';
import ChatPage from './pages/ChatPage';
import { ErrorBoundary } from './components/ErrorBoundary';

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <ConfigProvider locale={zhCN}>
        <Router>
          <Routes>
            <Route path="/" element={<AgentList />} />
            <Route path="/chat/:agentName" element={<ChatPage />} />
          </Routes>
        </Router>
      </ConfigProvider>
    </ErrorBoundary>
  );
};

export default App;

