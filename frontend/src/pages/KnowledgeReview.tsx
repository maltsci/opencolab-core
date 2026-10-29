import { CheckOutlined, CloseOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Checkbox, Descriptions, Drawer, Empty, Form, Input, List, Space, Spin, Tag, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import PageContainer from '../components/library/PageContainer';
import { formatDateTime } from '../components/library/library-utils';
import apiClient from '../services/api-client';
import type { KnowledgeSuggestion } from '../types/knowledge-suggestion';

interface DecisionFormValues {
  reason: string;
}

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

interface KnowledgeReviewProps {
  embedded?: boolean;
}

export default function KnowledgeReview({ embedded = false }: KnowledgeReviewProps) {
  const { t, i18n } = useTranslation();
  const [suggestions, setSuggestions] = useState<KnowledgeSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSuggestion, setSelectedSuggestion] = useState<KnowledgeSuggestion | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<string[]>([]);
  const [bulkReason, setBulkReason] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  const [decisionForm] = Form.useForm<DecisionFormValues>();

  const loadSuggestions = useCallback(async () => {
    setLoading(true);
    try {
      const response = await apiClient.get<KnowledgeSuggestion[]>('/knowledge-governance/suggestions', {
        params: { status: 'pending', reviewable_only: true, limit: 100 },
      });
      setSuggestions(response.data);
      setSelectedSuggestionIds((selected) => selected.filter((id) => (
        response.data.some((suggestion) => suggestion.id === id)
      )));
    } catch {
      message.error(t('knowledgeReview.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadSuggestions();
  }, [loadSuggestions]);

  const openSuggestion = (suggestion: KnowledgeSuggestion) => {
    decisionForm.resetFields();
    setSelectedSuggestion(suggestion);
  };

  const decide = async (decision: 'approve' | 'reject') => {
    if (!selectedSuggestion) return;
    try {
      const values = await decisionForm.validateFields();
      setSaving(true);
      await apiClient.post(
        `/knowledge-governance/suggestions/${selectedSuggestion.id}/${decision}`,
        values,
      );
      setSuggestions((items) => items.filter((item) => item.id !== selectedSuggestion.id));
      setSelectedSuggestionIds((ids) => ids.filter((id) => id !== selectedSuggestion.id));
      setSelectedSuggestion(null);
      message.success(t(decision === 'approve' ? 'knowledgeReview.approveSuccess' : 'knowledgeReview.rejectSuccess'));
    } catch (error) {
      if ('errorFields' in (error as object)) return;
      message.error(t(decision === 'approve' ? 'knowledgeReview.approveFailed' : 'knowledgeReview.rejectFailed'));
    } finally {
      setSaving(false);
    }
  };

  const decideBulk = async (decision: 'approve' | 'reject') => {
    if (selectedSuggestionIds.length === 0 || !bulkReason.trim()) {
      message.error(t('knowledgeReview.bulkReasonRequired'));
      return;
    }
    setBulkSaving(true);
    try {
      await apiClient.post(`/knowledge-governance/suggestions/bulk/${decision}`, {
        suggestion_ids: selectedSuggestionIds,
        reason: bulkReason.trim(),
      });
      const selectedIds = new Set(selectedSuggestionIds);
      setSuggestions((items) => items.filter((item) => !selectedIds.has(item.id)));
      setSelectedSuggestionIds([]);
      setBulkReason('');
      setSelectedSuggestion(null);
      message.success(t(decision === 'approve' ? 'knowledgeReview.bulkApproveSuccess' : 'knowledgeReview.bulkRejectSuccess'));
    } catch {
      message.error(t(decision === 'approve' ? 'knowledgeReview.bulkApproveFailed' : 'knowledgeReview.bulkRejectFailed'));
    } finally {
      setBulkSaving(false);
    }
  };

  const toggleSuggestionSelection = (suggestionId: string, checked: boolean) => {
    setSelectedSuggestionIds((current) => (
      checked ? [...current, suggestionId] : current.filter((id) => id !== suggestionId)
    ));
  };

  const reason = selectedSuggestion ? getPayloadText(selectedSuggestion.payload_json, 'reason') : null;
  const relationType = selectedSuggestion ? getPayloadText(selectedSuggestion.payload_json, 'relation_type') : null;
  const proposedDirectionName = selectedSuggestion ? getPayloadText(selectedSuggestion.payload_json, 'name') : null;
  const hasEvidence = selectedSuggestion && Object.keys(selectedSuggestion.evidence_json).length > 0;

  const content = (
    <>
      <Alert
        type="info"
        showIcon
        message={t('knowledgeReview.governanceTitle')}
        description={t('knowledgeReview.governanceDescription')}
        style={{ marginBottom: 16 }}
      />
      <Card
        title={t('knowledgeReview.pending', { count: suggestions.length })}
        extra={<Button icon={<ReloadOutlined />} onClick={() => void loadSuggestions()} loading={loading}>{t('knowledgeReview.refresh')}</Button>}
      >
        {selectedSuggestionIds.length > 0 ? (
          <Space orientation="vertical" size="small" style={{ width: '100%', marginBottom: 16 }}>
            <Typography.Text>{t('knowledgeReview.bulkSelected', { count: selectedSuggestionIds.length })}</Typography.Text>
            <Input.TextArea
              rows={2}
              maxLength={2000}
              showCount
              value={bulkReason}
              onChange={(event) => setBulkReason(event.target.value)}
              placeholder={t('knowledgeReview.bulkReasonPlaceholder')}
            />
            <Space>
              <Button type="primary" icon={<CheckOutlined />} loading={bulkSaving} onClick={() => void decideBulk('approve')}>
                {t('knowledgeReview.bulkApprove')}
              </Button>
              <Button danger icon={<CloseOutlined />} loading={bulkSaving} onClick={() => void decideBulk('reject')}>
                {t('knowledgeReview.bulkReject')}
              </Button>
            </Space>
          </Space>
        ) : null}
        {loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : suggestions.length === 0 ? (
          <Empty description={t('knowledgeReview.empty')} />
        ) : (
          <List
            dataSource={suggestions}
            renderItem={(suggestion) => (
              <List.Item actions={[
                <Checkbox
                  key="select"
                  checked={selectedSuggestionIds.includes(suggestion.id)}
                  onChange={(event) => toggleSuggestionSelection(suggestion.id, event.target.checked)}
                  aria-label={t('knowledgeReview.selectSuggestion')}
                >
                  {t('knowledgeReview.selectSuggestion')}
                </Checkbox>,
                <Button key="review" type="link" onClick={() => openSuggestion(suggestion)}>{t('knowledgeReview.review')}</Button>,
              ]}>
                <List.Item.Meta
                  title={<Space size={8}><Typography.Text strong>{t(`knowledgeReview.kind.${suggestionKindKey(suggestion)}`)}</Typography.Text><Tag>{t(`knowledgeReview.action.${suggestion.action}`, { defaultValue: suggestion.action })}</Tag></Space>}
                  description={
                    <Space orientation="vertical" size={2}>
                      <Typography.Text type="secondary">{reason || t('knowledgeReview.noReason')}</Typography.Text>
                      <Typography.Text type="secondary">{t('knowledgeReview.submittedAt', { time: formatDateTime(suggestion.created_at, i18n.language) })}</Typography.Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Drawer
        title={t('knowledgeReview.reviewTitle')}
        width={520}
        open={selectedSuggestion !== null}
        onClose={() => setSelectedSuggestion(null)}
        destroyOnHidden
        extra={selectedSuggestion ? <Tag color="gold">{t('knowledgeReview.pendingTag')}</Tag> : null}
      >
        {selectedSuggestion ? (
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('knowledgeReview.kindLabel')}>{t(`knowledgeReview.kind.${suggestionKindKey(selectedSuggestion)}`)}</Descriptions.Item>
              <Descriptions.Item label={t('knowledgeReview.actionLabel')}>{t(`knowledgeReview.action.${selectedSuggestion.action}`, { defaultValue: selectedSuggestion.action })}</Descriptions.Item>
              <Descriptions.Item label={t('knowledgeReview.submittedAtLabel')}>{formatDateTime(selectedSuggestion.created_at, i18n.language)}</Descriptions.Item>
              {proposedDirectionName ? <Descriptions.Item label={t('knowledgeReview.proposedDirection')}>{proposedDirectionName}</Descriptions.Item> : null}
              {relationType ? <Descriptions.Item label={t('knowledgeReview.relationType')}>{relationType}</Descriptions.Item> : null}
            </Descriptions>

            <div>
              <Typography.Text strong>{t('knowledgeReview.requestReason')}</Typography.Text>
              <Typography.Paragraph style={{ margin: '8px 0 0' }}>{reason || t('knowledgeReview.noReason')}</Typography.Paragraph>
            </div>

            {hasEvidence ? (
              <div>
                <Typography.Text strong>{t('knowledgeReview.evidence')}</Typography.Text>
                <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                  {JSON.stringify(selectedSuggestion.evidence_json, null, 2)}
                </Typography.Paragraph>
              </div>
            ) : null}

            <Form form={decisionForm} layout="vertical">
              <Form.Item name="reason" label={t('knowledgeReview.decisionReason')} rules={[{ required: true, whitespace: true, message: t('knowledgeReview.decisionReasonRequired') }]}>
                <Input.TextArea rows={4} maxLength={2000} showCount placeholder={t('knowledgeReview.decisionReasonPlaceholder')} />
              </Form.Item>
              <Space>
                <Button type="primary" icon={<CheckOutlined />} loading={saving} onClick={() => void decide('approve')}>{t('knowledgeReview.approve')}</Button>
                <Button danger icon={<CloseOutlined />} loading={saving} onClick={() => void decide('reject')}>{t('knowledgeReview.reject')}</Button>
              </Space>
            </Form>
          </Space>
        ) : null}
      </Drawer>
    </>
  );

  return embedded ? content : (
    <PageContainer title={t('knowledgeReview.title')} description={t('knowledgeReview.description')}>
      {content}
    </PageContainer>
  );
}
