import { Tag, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';

const visibilityColor: Record<string, string> = {
  lab_public: 'green',
  lab_private: 'gold',
  project: 'blue',
  private: 'default',
};

const processingStatusColor: Record<string, string> = {
  ready: 'green',
  failed: 'red',
  pending: 'default',
  parsing: 'blue',
  embedding: 'processing',
};

const fileFormatColor: Record<string, string> = {
  doc: 'geekblue',
  docx: 'geekblue',
  markdown: 'blue',
  md: 'blue',
  pdf: 'red',
  txt: 'default',
};

export function FileFormatTag({ filename }: { filename: string | null | undefined }) {
  const extension = filename?.split('.').pop()?.trim().toLowerCase();
  if (!extension || extension === filename?.toLowerCase()) return null;
  return (
    <Tag color={fileFormatColor[extension] || 'default'} style={{ marginInlineEnd: 0 }}>
      {extension.toUpperCase()}
    </Tag>
  );
}

export function VisibilityTag({ value }: { value: string }) {
  const { t } = useTranslation();
  return (
    <Tag color={visibilityColor[value] || 'default'}>
      {t(`library.visibility.${value}`, value)}
    </Tag>
  );
}

export function PublicationStatusTag({ value }: { value: string }) {
  const { t } = useTranslation();
  return (
    <Tag color={value === 'withdrawn' ? 'orange' : 'green'}>
      {t(`library.status.${value}`, value)}
    </Tag>
  );
}

export function ProcessingStatusTag({ state, progress, errorMessage }: {
  state: string | null | undefined;
  progress?: number | null;
  errorMessage?: string | null;
}) {
  const { t } = useTranslation();
  const effectiveState = state || 'pending';
  const label = effectiveState === 'parsing' || effectiveState === 'embedding'
    ? t(`library.processingStatus.${effectiveState}`, { progress: progress ?? 0 })
    : t(`library.processingStatus.${effectiveState}`, effectiveState);
  const tag = <Tag color={processingStatusColor[effectiveState] || 'default'}>{label}</Tag>;
  return effectiveState === 'failed' && errorMessage ? (
    <Tooltip title={errorMessage}>{tag}</Tooltip>
  ) : tag;
}
