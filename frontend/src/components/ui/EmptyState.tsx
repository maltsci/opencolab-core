import { Button, Empty, Typography, theme } from 'antd';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  cta?: {
    label: string;
    icon?: ReactNode;
    onClick: () => void;
  };
}

export default function EmptyState({ icon, title, description, cta }: EmptyStateProps) {
  const { token } = theme.useToken();
  const imageNode = icon ? (
    <div style={{ fontSize: 48, color: token.colorTextTertiary }}>{icon}</div>
  ) : undefined;

  return (
    <Empty
      image={imageNode}
      description={(
        <div style={{ maxWidth: 320, margin: '0 auto' }}>
          <Typography.Text strong style={{ display: 'block', fontSize: 16 }}>
            {title}
          </Typography.Text>
          {description ? (
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              {description}
            </Typography.Text>
          ) : null}
          {cta ? (
            <Button
              type="primary"
              icon={cta.icon}
              onClick={cta.onClick}
              style={{ marginTop: 16 }}
            >
              {cta.label}
            </Button>
          ) : null}
        </div>
      )}
    />
  );
}
