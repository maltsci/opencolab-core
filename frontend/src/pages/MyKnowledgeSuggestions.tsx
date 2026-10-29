import { CheckCircleOutlined, ClockCircleOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, Descriptions, Drawer, Empty, List, Space, Spin, Tag, Typography, message } from 'antd';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import { formatDateTime } from '../components/library/library-utils';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import type { KnowledgeSuggestion, KnowledgeSuggestionAudit, KnowledgeSuggestionStatus } from '../types/knowledge-suggestion';
import type { ResearchDirectionPage } from '../types/research-direction';

function suggestionKindKey(suggestion: KnowledgeSuggestion): string {
  if (suggestion.target_type === 'research_object_direction_link') return 'objectDirectionLink';
  if (suggestion.target_type === 'research_direction_relation') return 'directionRelation';
  if (suggestion.target_type === 'research_direction' && suggestion.action === 'create') return 'directionCreate';
  return 'other';
}

function getPayloadText(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === 'string' && value.trim() ? value : null;
}

function getDirectionId(suggestion: KnowledgeSuggestion): string | null {
  return suggestion.target_id
    || getPayloadText(suggestion.payload_json, 'direction_id')
    || getPayloadText(suggestion.payload_json, 'source_direction_id');
}

function statusIcon(status: KnowledgeSuggestionStatus) {
  if (status === 'approved') return <CheckCircleOutlined />;
  if (status === 'rejected') return <CloseCircleOutlined />;
  return <ClockCircleOutlined />;
}

function statusColor(status: KnowledgeSuggestionStatus): string {
  if (status === 'approved') return 'success';
  if (status === 'rejected') return 'error';
  return 'warning';
}

interface MyKnowledgeSuggestionsProps {
  embedded?: boolean;
}

export default function MyKnowledgeSuggestions({ embedded = false }: MyKnowledgeSuggestionsProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [suggestions, setSuggestions] = useState<KnowledgeSuggestion[]>([]);
  const [directionNames, setDirectionNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [auditSuggestion, setAuditSuggestion] = useState<KnowledgeSuggestion | null>(null);
  const [audit, setAudit] = useState<KnowledgeSuggestionAudit | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const [suggestionResult, directionResult] = await Promise.allSettled([
        apiClient.get<KnowledgeSuggestion[]>('/knowledge-governance/suggestions', {
          params: { limit: 100 },
        }),
        apiClient.get<ResearchDirectionPage>('/research-directions', {
          params: { status: 'all', limit: 100 },
        }),
      ]);
      if (suggestionResult.status === 'rejected') {
        throw suggestionResult.reason;
      }
      setSuggestions(suggestionResult.value.data);
      if (directionResult.status === 'fulfilled') {
        setDirectionNames(Object.fromEntries(
          directionResult.value.data.items.map((direction) => [direction.id, direction.name]),
        ));
      } else {
        setDirectionNames({});
      }
    } catch {
      message.error(t('mySuggestions.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadSuggestions();
  }, [loadSuggestions]);

  const openAudit = async (suggestion: KnowledgeSuggestion) => {
    setAuditSuggestion(suggestion);
    setAudit(null);
    setAuditLoading(true);
    try {
      const { data } = await apiClient.get<KnowledgeSuggestionAudit | null>(
        `/knowledge-governance/suggestions/${suggestion.id}/audit`,
      );
      setAudit(data);
    } catch {
      message.error(t('mySuggestions.auditLoadFailed'));
    } finally {
      setAuditLoading(false);
    }
  };

  const submittedSuggestions = useMemo(
    () => suggestions.filter((suggestion) => suggestion.submitted_by === user?.id),
    [suggestions, user?.id],
  );

  const content = (
    <>
      <Card
        title={t('mySuggestions.submitted', { count: submittedSuggestions.length })}
        extra={<Button icon={<ReloadOutlined />} onClick={() => void loadSuggestions()} loading={loading}>{t('mySuggestions.refresh')}</Button>}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : submittedSuggestions.length === 0 ? (
          <Empty description={t('mySuggestions.empty')} />
        ) : (
          <List
            dataSource={submittedSuggestions}
            renderItem={(suggestion) => {
              const requestReason = getPayloadText(suggestion.payload_json, 'reason');
              const proposedDirectionName = getPayloadText(suggestion.payload_json, 'name');
              const directionId = getDirectionId(suggestion);
              const directionName = directionId ? directionNames[directionId] : null;
              const actions: ReactNode[] = [];
              if (directionId && directionName) {
                actions.push(
                  <Button key="direction" type="link" onClick={() => navigate(`/research?direction=${encodeURIComponent(directionId)}`)}>
                    {t('mySuggestions.viewDirection')}
                  </Button>,
                );
              }
              if (suggestion.status === 'approved') {
                actions.push(
                  <Button key="audit" type="link" onClick={() => void openAudit(suggestion)}>
                    {t('mySuggestions.viewAudit')}
                  </Button>,
                );
              }
              return (
                <List.Item actions={actions.length > 0 ? actions : undefined}>
                  <List.Item.Meta
                    title={
                      <Space size={8} wrap>
                        <Typography.Text strong>{t(`knowledgeReview.kind.${suggestionKindKey(suggestion)}`)}</Typography.Text>
                        <Tag>{t(`knowledgeReview.action.${suggestion.action}`, { defaultValue: suggestion.action })}</Tag>
                        <Tag color={statusColor(suggestion.status)} icon={statusIcon(suggestion.status)}>{t(`mySuggestions.status.${suggestion.status}`)}</Tag>
                      </Space>
                    }
                    description={
                      <Space orientation="vertical" size={2}>
                        <Typography.Text type="secondary">{requestReason || t('mySuggestions.noReason')}</Typography.Text>
                        {proposedDirectionName ? <Typography.Text type="secondary">{t('mySuggestions.proposedDirection', { name: proposedDirectionName })}</Typography.Text> : null}
                        {directionName ? <Typography.Text type="secondary">{t('mySuggestions.direction', { name: directionName })}</Typography.Text> : null}
                        <Typography.Text type="secondary">{t('mySuggestions.submittedAt', { time: formatDateTime(suggestion.created_at, i18n.language) })}</Typography.Text>
                        {suggestion.decision_reason ? (
                          <Typography.Text>{t('mySuggestions.decisionReason', { reason: suggestion.decision_reason })}</Typography.Text>
                        ) : null}
                      </Space>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </Card>

      <Drawer
        title={t('mySuggestions.auditTitle')}
        width={560}
        open={auditSuggestion !== null}
        onClose={() => setAuditSuggestion(null)}
        destroyOnHidden
      >
        {auditLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : audit ? (
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('mySuggestions.auditAction')}>
                {t(`knowledgeReview.action.${audit.action}`, { defaultValue: audit.action })}
              </Descriptions.Item>
              <Descriptions.Item label={t('mySuggestions.auditEntity')}>
                {audit.entity_type}
              </Descriptions.Item>
              <Descriptions.Item label={t('mySuggestions.auditRecordedAt')}>
                {formatDateTime(audit.created_at, i18n.language)}
              </Descriptions.Item>
            </Descriptions>
            <div>
              <Typography.Text strong>{t('mySuggestions.auditBefore')}</Typography.Text>
              <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {JSON.stringify(audit.before_json, null, 2)}
              </Typography.Paragraph>
            </div>
            <div>
              <Typography.Text strong>{t('mySuggestions.auditAfter')}</Typography.Text>
              <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {JSON.stringify(audit.after_json, null, 2)}
              </Typography.Paragraph>
            </div>
          </Space>
        ) : (
          <Empty description={t('mySuggestions.auditEmpty')} />
        )}
      </Drawer>
    </>
  );

  return embedded ? content : (
    <PageContainer title={t('mySuggestions.title')} description={t('mySuggestions.description')}>
      {content}
    </PageContainer>
  );
}
