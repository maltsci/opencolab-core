import { Typography } from 'antd';
import type { ReactNode } from 'react';

export interface PageContainerProps {
  title: ReactNode;
  titleExtra?: ReactNode;
  description?: string;
  extra?: ReactNode;
  children: ReactNode;
}

export default function PageContainer({
  title,
  titleExtra,
  description,
  extra,
  children,
}: PageContainerProps) {
  return (
    <div style={{ padding: 24 }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
            flexWrap: 'wrap',
            gap: 8,
          }}
        >
          {/* flex-basis lets the title claim a full row when the header wraps on narrow screens */}
          <div style={{ flex: '1 1 240px', minWidth: 0 }}>
            <Typography.Title level={4} style={{ marginBottom: 0, display: 'flex', alignItems: 'center', gap: 4 }}>
              {typeof title === 'string' ? <span>{title}</span> : title}
              {titleExtra}
            </Typography.Title>
            {description ? (
              <Typography.Text type="secondary" style={{ display: 'block' }}>
                {description}
              </Typography.Text>
            ) : null}
          </div>
          {extra ? <div style={{ marginLeft: 'auto' }}>{extra}</div> : null}
        </div>
        {children}
      </div>
    </div>
  );
}
