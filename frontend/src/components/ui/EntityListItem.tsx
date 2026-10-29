import { Button, Space, Tooltip, Typography, theme } from 'antd';
import type { ReactNode } from 'react';

export interface EntityListItemAction {
  key: string;
  icon?: ReactNode;
  label?: string;
  tooltip?: string;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

interface EntityListItemProps {
  icon?: ReactNode;
  iconColor?: string;
  title: ReactNode;
  meta?: ReactNode;
  active?: boolean;
  actions?: EntityListItemAction[];
  onClick?: () => void;
  extra?: ReactNode;
}

export default function EntityListItem({
  icon,
  iconColor,
  title,
  meta,
  active,
  actions,
  onClick,
  extra,
}: EntityListItemProps) {
  const { token } = theme.useToken();

  const actionNodes = actions?.map((action) => {
    const button = (
      <Button
        key={action.key}
        type="text"
        size="small"
        icon={action.icon}
        danger={action.danger}
        disabled={action.disabled}
        onClick={(event) => {
          event.stopPropagation();
          action.onClick();
        }}
        style={{ paddingLeft: 4, paddingRight: 4 }}
      >
        {action.label}
      </Button>
    );
    if (action.tooltip) {
      return (
        <Tooltip key={action.key} title={action.tooltip}>
          {button}
        </Tooltip>
      );
    }
    return button;
  });

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '12px 16px',
        borderRadius: token.borderRadius,
        background: active ? token.colorPrimaryBg : 'transparent',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'background 0.15s',
      }}
      onKeyDown={onClick ? (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      } : undefined}
    >
      {icon ? (
        <div style={{ color: iconColor || token.colorTextSecondary, fontSize: 18, lineHeight: 1, marginTop: 2 }}>
          {icon}
        </div>
      ) : null}
      <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
        <Typography.Text strong ellipsis style={{ display: 'block' }}>
          {title}
        </Typography.Text>
        {meta ? (
          <Typography.Text type="secondary" ellipsis style={{ display: 'block', fontSize: 13 }}>
            {meta}
          </Typography.Text>
        ) : null}
      </div>
      {actionNodes?.length ? (
        <Space size={0} onClick={(event) => event.stopPropagation()}>
          {actionNodes}
        </Space>
      ) : null}
      {extra}
    </div>
  );
}
