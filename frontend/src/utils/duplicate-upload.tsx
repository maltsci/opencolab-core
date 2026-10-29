import { Button, Form, Input, InputNumber, message, Modal, Space, Tag, Typography } from 'antd';
import type { TFunction } from 'i18next';
import { useState } from 'react';

import type { DuplicateUploadInfo, DuplicateUploadLocation } from '../types/upload';
import apiClient from '../services/api-client';

const { Paragraph, Text } = Typography;

export function getDuplicateUploadInfo(error: unknown): DuplicateUploadInfo | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (
    detail
    && typeof detail === 'object'
    && (detail as { code?: string }).code === 'duplicate_source'
  ) {
    return detail as DuplicateUploadInfo;
  }
  return null;
}

function locationLabel(t: TFunction, location: DuplicateUploadLocation): string {
  if (location.location_type === 'project') {
    return location.label;
  }
  return t(`uploadDuplicate.location.${location.location_type}`, location.label);
}

function DuplicateReadAccessRequest({ info, t }: { info: DuplicateUploadInfo; t: TFunction }) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [form] = Form.useForm<{ purpose: string; duration_days: number }>();

  const submit = async () => {
    let values: { purpose: string; duration_days: number };
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post(`/sources/${encodeURIComponent(info.existing_source_id)}/access-requests`, {
        ...values, content_hash: info.content_hash,
      });
      setSubmitted(true);
      setOpen(false);
      message.success(t('library.accessRequestSubmitted'));
    } catch (error: unknown) {
      const response = (error as { response?: { status?: number; data?: { detail?: string } } }).response;
      if (response?.status === 409 && response.data?.detail === 'Access request already exists') {
        setSubmitted(true);
        setOpen(false);
        message.info(t('library.accessRequestPending'));
      } else {
        message.error(t('library.accessRequestSubmitFailed'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <Button type="primary" disabled={submitted} onClick={() => setOpen(true)}>
        {t(submitted ? 'library.accessRequestPending' : 'library.requestAccess')}
      </Button>
      <Modal
        title={t('library.requestAccess')}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void submit()}
        confirmLoading={submitting}
        okText={t('common.submit')}
        cancelText={t('common.cancel')}
      >
        <Paragraph>{t('uploadDuplicate.requestHiddenHelp', { sourceId: info.existing_source_id })}</Paragraph>
        <Form form={form} layout="vertical" initialValues={{ purpose: '', duration_days: 30 }}>
          <Form.Item
            name="purpose" label={t('library.accessPurpose')}
            rules={[{ required: true, whitespace: true, message: t('library.accessPurposeRequired') }]}
          >
            <Input.TextArea rows={3} maxLength={2000} placeholder={t('library.accessPurposePlaceholder')} />
          </Form.Item>
          <Form.Item name="duration_days" label={t('library.accessDurationDays')} rules={[{ required: true }]}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

function DuplicateUploadContent({ info, t }: { info: DuplicateUploadInfo; t: TFunction }) {
  return (
    <Space orientation="vertical" size={8} style={{ width: '100%' }}>
      <Paragraph style={{ marginBottom: 0 }}>
        {t('uploadDuplicate.description')}
      </Paragraph>
      {info.locations.length > 0 ? (
        <Space orientation="vertical" size={6} style={{ width: '100%' }}>
          {info.locations.map((location) => (
            <Space key={`${location.location_type}-${location.asset_id || location.project_id || location.label}`}>
              <Text strong>{locationLabel(t, location)}</Text>
              <Tag color={location.can_use ? 'green' : 'orange'}>
                {location.can_use ? t('uploadDuplicate.canUse') : t('uploadDuplicate.noAccess')}
              </Tag>
              {!location.can_use && location.asset_id ? (
                <Button
                  type="link"
                  size="small"
                  href={`/resources/${encodeURIComponent(location.asset_id)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {t(location.visibility_scope === 'lab_private'
                    ? 'uploadDuplicate.requestAccess'
                    : 'uploadDuplicate.viewAccessDetails')}
                </Button>
              ) : null}
            </Space>
          ))}
        </Space>
      ) : null}
      {info.inaccessible_count > 0 ? (
        <Text type="warning">
          {t('uploadDuplicate.inaccessibleCount', { count: info.inaccessible_count })}
        </Text>
      ) : null}
      {!info.can_use_existing ? (
        <Paragraph style={{ marginBottom: 0 }}>
          {t(info.can_request_access ? 'uploadDuplicate.requestHiddenHelp' : 'uploadDuplicate.accessHelp', {
            sourceId: info.existing_source_id,
          })}
        </Paragraph>
      ) : null}
      {!info.can_use_existing && info.can_request_access && info.content_hash ? (
        <DuplicateReadAccessRequest info={info} t={t} />
      ) : null}
    </Space>
  );
}

export function showDuplicateUploadModal({
  info,
  t,
  onUseExisting,
}: {
  info: DuplicateUploadInfo;
  t: TFunction;
  onUseExisting?: () => void;
}) {
  const content = <DuplicateUploadContent info={info} t={t} />;
  if (info.can_use_existing && onUseExisting) {
    Modal.confirm({
      title: t('uploadDuplicate.title'),
      content,
      okText: t('uploadDuplicate.useExisting'),
      cancelText: t('common.cancel'),
      onOk: onUseExisting,
    });
    return;
  }
  Modal.info({
    title: t('uploadDuplicate.title'),
    content,
    okText: t('common.ok'),
  });
}
