import { CheckCircleOutlined, CloseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Empty, List, Space, Spin, Tag, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import { formatDateTime } from '../components/library/library-utils';
import { KNOWLEDGE_INBOX_UPDATED_EVENT } from '../constants/knowledge-inbox';
import apiClient from '../services/api-client';
import type { KnowledgeInbox, KnowledgeSuggestion, KnowledgeSuggestionStatus } from '../types/knowledge-suggestion';

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

function statusColor(status: KnowledgeSuggestionStatus): string {
  return status === 'approved' ? 'success' : 'error';
}

function statusIcon(status: KnowledgeSuggestionStatus) {
  return status === 'approved' ? <CheckCircleOutlined /> : <CloseCircleOutlined />;
}

interface KnowledgeInboxProps {
  embedded?: boolean;
  canReview?: boolean;
}

export default function KnowledgeInbox({ embedded = false, canReview = false }: KnowledgeInboxProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [inbox, setInbox] = useState<KnowledgeInbox>({
    review_items: [],
    decision_items: [],
    unread_decision_count: 0,
  });
  const [loading, setLoading] = useState(true);

  const loadInbox = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<KnowledgeInbox>('/knowledge-governance/inbox');
      setInbox(data);
      if (data.unread_decision_count > 0) {
        await apiClient.post('/knowledge-governance/inbox/decisions/mark-read');
        window.dispatchEvent(new Event(KNOWLEDGE_INBOX_UPDATED_EVENT));
      }
    } catch {
      message.error(t('knowledgeInbox.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadInbox();
  }, [loadInbox]);

  const content = (
    <>
      <Alert
        type="info"
        showIcon
        message={t('knowledgeInbox.scopeTitle')}
        description={t('knowledgeInbox.scopeDescription')}
        style={{ marginBottom: 16 }}
      />
      {loading ? (
        <Card><div style={{ textAlign: 'center', padding: 40 }}><Spin /></div></Card>
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <Card
            title={t('knowledgeInbox.reviewItems', { count: inbox.review_items.length })}
            extra={(
              <Space size="small">
                {canReview ? (
                  <Button type="link" onClick={() => navigate('/knowledge-governance?tab=review')}>
                    {t('knowledgeInbox.openReview')}
                  </Button>
                ) : null}
                <Button icon={<ReloadOutlined />} onClick={() => void loadInbox()}>
                  {t('knowledgeInbox.refresh')}
                </Button>
              </Space>
            )}
          >
            {inbox.review_items.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('knowledgeInbox.reviewEmpty')} />
            ) : (
              <List
                dataSource={inbox.review_items}
                renderItem={(suggestion) => {
                  const reason = getPayloadText(suggestion.payload_json, 'reason');
                  return (
                    <List.Item
                      actions={canReview ? [
                        <Button key="review" type="link" onClick={() => navigate('/knowledge-governance?tab=review')}>
                          {t('knowledgeInbox.reviewNow')}
                        </Button>,
                      ] : undefined}
                    >
                      <List.Item.Meta
                        title={(
                          <Space size={8} wrap>
                            <Typography.Text strong>
                              {t(`knowledgeReview.kind.${suggestionKindKey(suggestion)}`)}
                            </Typography.Text>
                            <Tag>{t(`knowledgeReview.action.${suggestion.action}`, { defaultValue: suggestion.action })}</Tag>
                          </Space>
                        )}
                        description={(
                          <Space orientation="vertical" size={2}>
                            <Typography.Text type="secondary">
                              {reason || t('knowledgeReview.noReason')}
                            </Typography.Text>
                            <Typography.Text type="secondary">
                              {t('knowledgeReview.submittedAt', {
                                time: formatDateTime(suggestion.created_at, i18n.language),
                              })}
                            </Typography.Text>
                          </Space>
                        )}
                      />
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>
          <Card
            title={t('knowledgeInbox.decisionItems', { count: inbox.decision_items.length })}
            extra={(
              <Button type="link" onClick={() => navigate('/knowledge-governance?tab=suggestions')}>
                {t('knowledgeInbox.openSuggestions')}
              </Button>
            )}
          >
            {inbox.decision_items.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('knowledgeInbox.decisionEmpty')} />
            ) : (
              <List
                dataSource={inbox.decision_items}
                renderItem={(suggestion) => (
                  <List.Item>
                    <List.Item.Meta
                      title={(
                        <Space size={8} wrap>
                          <Typography.Text strong>
                            {t(`knowledgeReview.kind.${suggestionKindKey(suggestion)}`)}
                          </Typography.Text>
                          <Tag color={statusColor(suggestion.status)} icon={statusIcon(suggestion.status)}>
                            {t(`mySuggestions.status.${suggestion.status}`)}
                          </Tag>
                        </Space>
                      )}
                      description={(
                        <Space orientation="vertical" size={2}>
                          <Typography.Text>
                            {t('mySuggestions.decisionReason', {
                              reason: suggestion.decision_reason || t('knowledgeReview.noReason'),
                            })}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {t('knowledgeInbox.decidedAt', {
                              time: suggestion.decided_at
                                ? formatDateTime(suggestion.decided_at, i18n.language)
                                : t('knowledgeInbox.unknownTime'),
                            })}
                          </Typography.Text>
                        </Space>
                      )}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
          <Card
            title={t('knowledgeInbox.maintenanceTitle')}
            extra={(
              <Button type="link" onClick={() => navigate('/maintenance')}>
                {t('knowledgeInbox.openMaintenance')}
              </Button>
            )}
          >
            <Typography.Text type="secondary">
              {t('knowledgeInbox.maintenanceDescription')}
            </Typography.Text>
          </Card>
        </Space>
      )}
    </>
  );

  return embedded ? content : (
    <PageContainer title={t('knowledgeInbox.title')} description={t('knowledgeInbox.description')}>
      {content}
    </PageContainer>
  );
}
