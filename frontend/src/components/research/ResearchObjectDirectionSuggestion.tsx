import { SendOutlined } from '@ant-design/icons';
import { Alert, Button, Divider, Drawer, Empty, Form, Input, Select, Space, Spin, message } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '../../hooks/useAuth';
import apiClient from '../../services/api-client';
import type { ResearchDirection, ResearchDirectionPage } from '../../types/research-direction';
import type { SessionResearchObject } from './types';

interface SuggestionFormValues {
  direction_id: string;
  relation_type: 'belongs_to' | 'informs';
  reason: string;
}

interface CreateDirectionFormValues {
  name: string;
  reason: string;
}

interface ResearchObjectDirectionSuggestionProps {
  researchObject: SessionResearchObject;
  compact?: boolean;
}

export function ResearchObjectDirectionSuggestion({
  researchObject,
  compact = false,
}: ResearchObjectDirectionSuggestionProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [loadingDirections, setLoadingDirections] = useState(false);
  const [directions, setDirections] = useState<ResearchDirection[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [creatingDirection, setCreatingDirection] = useState(false);
  const [form] = Form.useForm<SuggestionFormValues>();
  const [createDirectionForm] = Form.useForm<CreateDirectionFormValues>();

  if (!user || researchObject.created_by !== user.id) return null;

  const openDrawer = async () => {
    form.resetFields();
    form.setFieldValue('relation_type', 'belongs_to');
    createDirectionForm.resetFields();
    setCreatingDirection(false);
    setOpen(true);
    setLoadingDirections(true);
    try {
      const response = await apiClient.get<ResearchDirectionPage>('/research-directions', {
        params: { status: 'active', limit: 100 },
      });
      setDirections(response.data.items);
    } catch {
      setDirections([]);
      message.error(t('researchObject.directionSuggestionLoadFailed'));
    } finally {
      setLoadingDirections(false);
    }
  };

  const submitSuggestion = async (values: SuggestionFormValues) => {
    setSubmitting(true);
    try {
      await apiClient.post(`/research-directions/${values.direction_id}/research-objects`, {
        research_object_id: researchObject.id,
        relation_type: values.relation_type,
        reason: values.reason,
      });
      setOpen(false);
      message.success(t('researchObject.directionSuggestionSuccess'));
    } catch {
      message.error(t('researchObject.directionSuggestionFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const submitCreateDirectionSuggestion = async (values: CreateDirectionFormValues) => {
    setSubmitting(true);
    try {
      await apiClient.post(`/research-objects/${researchObject.id}/direction-suggestions`, {
        name: values.name,
        reason: values.reason,
      });
      setOpen(false);
      message.success(t('researchObject.directionSuggestionCreateSuccess'));
    } catch {
      message.error(t('researchObject.directionSuggestionCreateFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button
        type={compact ? "link" : "default"}
        size="small"
        icon={<SendOutlined />}
        onClick={(event) => {
          event.stopPropagation();
          void openDrawer();
        }}
        style={compact ? { padding: 0 } : undefined}
      >
        {t('researchObject.directionSuggestion')}
      </Button>
      <Drawer
        title={t(creatingDirection ? 'researchObject.directionSuggestionCreateTitle' : 'researchObject.directionSuggestionTitle')}
        width={480}
        open={open}
        onClose={() => setOpen(false)}
        destroyOnHidden
      >
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message={t('researchObject.directionSuggestionGovernanceTitle')}
            description={t('researchObject.directionSuggestionGovernanceDescription')}
          />
          {loadingDirections ? (
            <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>
          ) : creatingDirection ? (
            <Form form={createDirectionForm} layout="vertical" onFinish={submitCreateDirectionSuggestion}>
              <Form.Item name="name" label={t('researchObject.directionSuggestionCreateName')} rules={[{ required: true, whitespace: true, message: t('researchObject.directionSuggestionCreateNameRequired') }]}>
                <Input maxLength={255} placeholder={t('researchObject.directionSuggestionCreateNamePlaceholder')} />
              </Form.Item>
              <Form.Item name="reason" label={t('researchObject.directionSuggestionReason')} rules={[{ required: true, whitespace: true, message: t('researchObject.directionSuggestionReasonRequired') }]}>
                <Input.TextArea rows={4} maxLength={2000} showCount placeholder={t('researchObject.directionSuggestionReasonPlaceholder')} />
              </Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={submitting}>
                  {t('researchObject.directionSuggestionCreateSubmit')}
                </Button>
                <Button onClick={() => setCreatingDirection(false)}>{t('researchObject.directionSuggestionBack')}</Button>
              </Space>
            </Form>
          ) : (
            <>
              {directions.length === 0 ? (
                <Empty description={t('researchObject.directionSuggestionNoDirections')} />
              ) : (
                <Form form={form} layout="vertical" onFinish={submitSuggestion}>
                  <Form.Item name="direction_id" label={t('researchObject.directionSuggestionDirection')} rules={[{ required: true, message: t('researchObject.directionSuggestionDirectionRequired') }]}>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      placeholder={t('researchObject.directionSuggestionDirectionPlaceholder')}
                      options={directions.map((direction) => ({
                        value: direction.id,
                        label: direction.name,
                      }))}
                    />
                  </Form.Item>
                  <Form.Item name="relation_type" label={t('researchObject.directionSuggestionRelationType')} rules={[{ required: true }]}>
                    <Select options={[
                      { value: 'belongs_to', label: t('researchObject.directionSuggestionBelongsTo') },
                      { value: 'informs', label: t('researchObject.directionSuggestionInforms') },
                    ]} />
                  </Form.Item>
                  <Form.Item name="reason" label={t('researchObject.directionSuggestionReason')} rules={[{ required: true, whitespace: true, message: t('researchObject.directionSuggestionReasonRequired') }]}>
                    <Input.TextArea rows={4} maxLength={2000} showCount placeholder={t('researchObject.directionSuggestionReasonPlaceholder')} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={submitting}>
                    {t('researchObject.directionSuggestionSubmit')}
                  </Button>
                </Form>
              )}
              <Divider />
              <Button type="link" onClick={() => setCreatingDirection(true)}>
                {t('researchObject.directionSuggestionCreateAction')}
              </Button>
            </>
          )}
        </Space>
      </Drawer>
    </>
  );
}
