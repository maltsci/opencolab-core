import { Collapse, Descriptions, Drawer, List, Spin, Typography, theme } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import { formatDateTime } from './library-utils';

export interface SourceExtraction {
  id: string;
  source_id: string;
  status: string;
  document_type: string | null;
  schema_version: string;
  structured_json: Record<string, unknown>;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExtractionDrawerProps {
  open: boolean;
  sourceId: string | null;
  name?: string;
  processingState?: string | null;
  onClose: () => void;
}

interface ExtractionClaim {
  statement?: string;
  evidence?: string;
  confidence?: number;
}

type ExtractionViewState = 'idle' | 'pending' | 'missing' | 'error' | 'loaded';

function getExtractionString(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function getExtractionStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => getExtractionString(item))
    .filter((item): item is string => item !== null);
}

function getExtractionClaims(value: unknown): ExtractionClaim[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ExtractionClaim => (
    typeof item === 'object' && item !== null
  ));
}

export default function ExtractionDrawer({ open, sourceId, name, processingState, onClose }: ExtractionDrawerProps) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const [extractionData, setExtractionData] = useState<SourceExtraction | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewState, setViewState] = useState<ExtractionViewState>('idle');

  useEffect(() => {
    if (!open || !sourceId) {
      setExtractionData(null);
      setViewState('idle');
      setLoading(false);
      return;
    }
    if (processingState && processingState !== 'ready' && processingState !== 'failed') {
      setExtractionData(null);
      setViewState('pending');
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setViewState('idle');
    setExtractionData(null);
    apiClient.get(`/sources/${sourceId}/extraction`)
      .then(({ data }) => {
        if (cancelled) return;
        setExtractionData(data);
        setViewState('loaded');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const detail =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setViewState(detail === 'Source extraction not found' ? 'missing' : 'error');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [open, sourceId, processingState]);

  const sectionStyle = {
    padding: 12,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadius,
    background: token.colorFillQuaternary,
  };

  const getExtractionStatusLabel = (status?: string | null) => {
    if (status === 'ready') return t('source.extractionStatusReady');
    if (status === 'failed') return t('source.extractionStatusFailed');
    if (status === 'pending') return t('source.extractionStatusPending');
    return t('source.extractionStatusMissing');
  };

  const renderExtractionText = (value: unknown) => getExtractionString(value) || '-';

  const renderExtractionList = (items: string[], emptyLabel: string) => (
    items.length > 0 ? (
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    ) : (
      <span style={{ color: token.colorTextTertiary }}>{emptyLabel}</span>
    )
  );

  const renderExtractionClaims = (claims: ExtractionClaim[]) => (
    claims.length > 0 ? (
      <List
        size="small"
        split={false}
        dataSource={claims}
        renderItem={(claim, index) => (
          <List.Item style={{ padding: '0 0 12px' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div>
                <strong>{t('source.extractionFieldStatement', 'Statement')}:</strong>{' '}
                {renderExtractionText(claim.statement)}
              </div>
              <div>
                <strong>{t('source.extractionFieldEvidence', 'Evidence')}:</strong>{' '}
                {renderExtractionText(claim.evidence)}
              </div>
              <div>
                <strong>{t('source.extractionFieldConfidence', 'Confidence')}:</strong>{' '}
                {typeof claim.confidence === 'number' ? claim.confidence : '-'}
              </div>
              {index < claims.length - 1 && (
                <div style={{ borderBottom: `1px solid ${token.colorBorderSecondary}`, marginTop: 8 }} />
              )}
            </div>
          </List.Item>
        )}
      />
    ) : (
      <span style={{ color: token.colorTextTertiary }}>
        {t('source.extractionFieldClaimsEmpty', 'No claims extracted')}
      </span>
    )
  );

  return (
    <Drawer
      title={name ? t('source.extractionTitle', { name }) : t('source.extraction')}
      open={open}
      onClose={onClose}
      size={560}
      destroyOnHidden
    >
      <Spin spinning={loading}>
        {extractionData ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('source.extractionStatus')}>
                {getExtractionStatusLabel(extractionData.status)}
              </Descriptions.Item>
              <Descriptions.Item label={t('source.extractionDocumentType')}>
                {extractionData.document_type || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('source.extractionSchemaVersion')}>
                {extractionData.schema_version}
              </Descriptions.Item>
              <Descriptions.Item label={t('source.extractionUpdatedAt')}>
                {formatDateTime(extractionData.updated_at, i18n.language)}
              </Descriptions.Item>
              {extractionData.error_message ? (
                <Descriptions.Item label={t('source.extractionError')}>
                  <Typography.Text type="danger">{extractionData.error_message}</Typography.Text>
                </Descriptions.Item>
              ) : null}
            </Descriptions>

            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('source.extractionFieldTitle', 'Title')}>
                {renderExtractionText(extractionData.structured_json.title)}
              </Descriptions.Item>
              <Descriptions.Item label={t('source.extractionFieldSummary', 'Summary')}>
                {renderExtractionText(extractionData.structured_json.summary)}
              </Descriptions.Item>
            </Descriptions>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={sectionStyle}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  {t('source.extractionFieldHighlights', 'Highlights')}
                </div>
                {renderExtractionList(
                  getExtractionStringList(extractionData.structured_json.highlights),
                  t('source.extractionFieldHighlightsEmpty', 'No highlights extracted'),
                )}
              </div>

              <div style={sectionStyle}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  {t('source.extractionFieldClaims', 'Claims')}
                </div>
                {renderExtractionClaims(
                  getExtractionClaims(extractionData.structured_json.claims),
                )}
              </div>

              <div style={sectionStyle}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  {t('source.extractionFieldMethods', 'Methods')}
                </div>
                {renderExtractionList(
                  getExtractionStringList(extractionData.structured_json.methods),
                  t('source.extractionFieldMethodsEmpty', 'No methods extracted'),
                )}
              </div>

              <div style={sectionStyle}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  {t('source.extractionFieldLimitations', 'Limitations')}
                </div>
                {renderExtractionList(
                  getExtractionStringList(extractionData.structured_json.limitations),
                  t('source.extractionFieldLimitationsEmpty', 'No limitations extracted'),
                )}
              </div>

              <div style={sectionStyle}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>
                  {t('source.extractionFieldDatasets', 'Datasets')}
                </div>
                {renderExtractionList(
                  getExtractionStringList(extractionData.structured_json.datasets),
                  t('source.extractionFieldDatasetsEmpty', 'No datasets extracted'),
                )}
              </div>

              <Collapse
                items={[
                  {
                    key: 'raw',
                    label: t('source.extractionStructuredData'),
                    children: (
                      <pre
                        style={{
                          margin: 0,
                          maxHeight: 320,
                          overflow: 'auto',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                        }}
                      >
                        {JSON.stringify(extractionData.structured_json, null, 2)}
                      </pre>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        ) : viewState === 'pending' ? (
          <Typography.Text type="secondary">{t('source.extractionPending')}</Typography.Text>
        ) : viewState === 'missing' ? (
          <Typography.Text type="secondary">{t('source.extractionMissing')}</Typography.Text>
        ) : viewState === 'error' ? (
          <Typography.Text type="danger">{t('source.extractionUnavailable')}</Typography.Text>
        ) : !loading ? (
          <Typography.Text type="secondary">{t('source.extractionEmpty')}</Typography.Text>
        ) : null}
      </Spin>
    </Drawer>
  );
}
