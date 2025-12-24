import React, { Component, ReactNode } from 'react';
import { Result, Button } from 'antd';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="Page Load Error"
          subTitle={this.state.error?.message || 'An unknown error occurred'}
          extra={[
            <Button type="primary" key="reload" onClick={() => window.location.reload()}>
              Refresh Page
            </Button>,
            <Button key="home" onClick={() => window.location.href = '/'}>
              Back to Home
            </Button>,
          ]}
        />
      );
    }

    return this.props.children;
  }
}

