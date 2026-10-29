import { Card } from 'antd';
import type { CardProps } from 'antd';
import type { ReactNode } from 'react';

interface SectionCardProps {
  title?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  styles?: CardProps['styles'];
}

export default function SectionCard({ title, extra, children, className, styles }: SectionCardProps) {
  return (
    <Card
      className={className}
      title={title}
      extra={extra}
      styles={{ body: { padding: 20 }, ...styles }}
    >
      {children}
    </Card>
  );
}
