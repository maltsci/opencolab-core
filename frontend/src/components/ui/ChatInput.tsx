import { PaperClipOutlined, SendOutlined } from '@ant-design/icons';
import { Badge, Button, Input, Space, Tooltip, theme } from 'antd';
import type { KeyboardEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  selectedSourcesCount?: number;
  onSourcesClick?: () => void;
  sourcesCollapsed?: boolean;
  extraActions?: ReactNode;
}

export default function ChatInput({
  value,
  onChange,
  onSubmit,
  placeholder,
  disabled = false,
  loading = false,
  selectedSourcesCount = 0,
  onSourcesClick,
  sourcesCollapsed = false,
  extraActions,
}: ChatInputProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!disabled && value.trim()) {
        onSubmit();
      }
    }
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!disabled && value.trim()) {
        onSubmit();
      }
    }
  };

  return (
    <div
      className="chat-input-wrapper"
      style={{
        border: `1px solid ${token.colorBorder}`,
        borderRadius: token.borderRadius * 1.5,
        background: token.colorBgContainer,
        boxShadow: token.boxShadowTertiary,
      }}
    >
      <Input.TextArea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoSize={{ minRows: 2, maxRows: 8 }}
        style={{
          border: 'none',
          boxShadow: 'none',
          resize: 'none',
          padding: '12px 16px',
          fontSize: 15,
        }}
      />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          borderTop: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Space size={4}>
          <Tooltip title={sourcesCollapsed ? t('source.expandSessionMaterials') : t('source.collapseSessionMaterials')}>
            <Button
              type={sourcesCollapsed ? 'primary' : 'text'}
              size="small"
              icon={
                <Badge count={selectedSourcesCount} size="small" offset={[2, -2]}>
                  <PaperClipOutlined />
                </Badge>
              }
              onClick={onSourcesClick}
            >
              {selectedSourcesCount > 0
                ? t('chat.selectedSources', { count: selectedSourcesCount })
                : t('chat.sources')}
            </Button>
          </Tooltip>
          {extraActions}
        </Space>
        <div style={{ flex: 1 }} />
        <Button
          type="primary"
          icon={loading ? undefined : <SendOutlined />}
          loading={loading}
          disabled={disabled || !value.trim()}
          onClick={onSubmit}
        >
          {t('chat.send')}
        </Button>
      </div>
    </div>
  );
}
