import {
  DeleteOutlined,
  EditOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { FileFormatTag, ProcessingStatusTag } from '../components/library/AssetTags';
import BibliographicMetadataSection from '../components/library/BibliographicMetadataSection';
import { formatDateTime } from '../components/library/library-utils';
import PageContainer from '../components/library/PageContainer';
import PdfPreviewModal from '../components/library/PdfPreviewModal';
import ResourceProfileSection from '../components/library/ResourceProfileSection';
import apiClient from '../services/api-client';
import type { ResearchAsset } from '../types/research-asset';
import './resource-detail.css';

interface AccessRequestFormValues {
  purpose: string;
  duration_days: number;
}

interface TrainingGrantFormValues {
  user_ids: string[];
  duration_days: number;
}

interface TrainingRecipient {
  id: string;
  username: string;
  display_name?: string | null;
}

interface SourceMember {
  id: string;
  child: {
    id: string;
    name: string;
    type: string;
  } | null;
}

export default function ResourcePreview() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { assetId } = useParams();
  const [asset, setAsset] = useState<ResearchAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [requestOpen, setRequestOpen] = useState(false);
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [trainingGrantOpen, setTrainingGrantOpen] = useState(false);
  const [trainingGrantSubmitting, setTrainingGrantSubmitting] = useState(false);
  const [trainingRecipients, setTrainingRecipients] = useState<TrainingRecipient[]>([]);
  const [collectionMembers, setCollectionMembers] = useState<SourceMember[]>([]);
  const [collectionMembersLoading, setCollectionMembersLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [titleEditing, setTitleEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [titleSaving, setTitleSaving] = useState(false);
  const [requestForm] = Form.useForm<AccessRequestFormValues>();
  const [trainingGrantForm] = Form.useForm<TrainingGrantFormValues>();

  const loadAsset = useCallback(async () => {
    if (!assetId) return;
    setLoading(true);
    setLoadFailed(false);
    try {
      const { data } = await apiClient.get<ResearchAsset>(`/research-assets/${assetId}`);
      setAsset(data);
    } catch {
      setAsset(null);
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [assetId]);

  useEffect(() => {
    setAsset(null);
    void loadAsset();
  }, [loadAsset]);

  useEffect(() => {
    if (!asset?.source_id || (asset.asset_type !== 'collection' && asset.source_type !== 'group')) {
      setCollectionMembers([]);
      return;
    }
    setCollectionMembersLoading(true);
    apiClient.get<SourceMember[]>(`/sources/${asset.source_id}/members`)
      .then((response) => setCollectionMembers(response.data))
      .catch(() => setCollectionMembers([]))
      .finally(() => setCollectionMembersLoading(false));
  }, [asset?.asset_type, asset?.source_id, asset?.source_type]);

  const openAccessRequest = () => {
    requestForm.setFieldsValue({ purpose: '', duration_days: 30 });
    setRequestOpen(true);
  };

  const submitAccessRequest = async () => {
    if (!asset) return;
    const values = await requestForm.validateFields();
    setRequestSubmitting(true);
    try {
      await apiClient.post(`/research-assets/${asset.id}/access-requests`, values);
      message.success(t('library.accessRequestSubmitted'));
      setRequestOpen(false);
      await loadAsset();
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      message.error(detail || t('library.accessRequestSubmitFailed'));
    } finally {
      setRequestSubmitting(false);
    }
  };

  const openTrainingGrant = async () => {
    trainingGrantForm.setFieldsValue({ user_ids: [], duration_days: 90 });
    setTrainingGrantOpen(true);
    try {
      const { data } = await apiClient.get<TrainingRecipient[]>('/auth/users');
      setTrainingRecipients(data);
    } catch {
      setTrainingRecipients([]);
      message.error(t('library.trainingGrantFailed'));
    }
  };

  const submitTrainingGrant = async () => {
    if (!asset) return;
    const values = await trainingGrantForm.validateFields();
    setTrainingGrantSubmitting(true);
    try {
      await apiClient.post(`/research-assets/${asset.id}/training-grants`, values);
      message.success(t('library.trainingGrantSuccess'));
      setTrainingGrantOpen(false);
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      message.error(detail || t('library.trainingGrantFailed'));
    } finally {
      setTrainingGrantSubmitting(false);
    }
  };

  const deleteAsset = async () => {
    if (!asset) return;
    setDeleting(true);
    try {
      await apiClient.post(`/library/assets/${asset.id}/delete`, {});
      message.success(t('library.deleteSuccess'));
      navigate('/library', { replace: true });
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })
        .response?.data?.detail;
      message.error(detail || t('library.deleteFailed'));
    } finally {
      setDeleting(false);
    }
  };

  const startTitleEdit = () => {
    if (!asset) return;
    setTitleDraft(asset.title);
    setTitleEditing(true);
  };

  const saveTitle = async () => {
    if (!asset || !titleDraft.trim()) return;
    setTitleSaving(true);
    try {
      const { data } = await apiClient.patch<ResearchAsset>(
        `/research-assets/${asset.id}/bibliographic-metadata`,
        { title: titleDraft.trim() },
      );
      setAsset(data);
      setTitleEditing(false);
      message.success(t('library.bibliographic.titleSaved'));
    } catch {
      message.error(t('library.bibliographic.actionFailed'));
    } finally {
      setTitleSaving(false);
    }
  };

  const canPreview = Boolean(
    asset?.source_id
    && asset.asset_type !== 'collection'
    && asset.can_preview_content,
  );
  const isPdf = Boolean(asset?.original_filename?.toLowerCase().endsWith('.pdf'));
  const isCollection = Boolean(
    asset?.asset_type === 'collection' || asset?.source_type === 'group',
  );

  return (
    <PageContainer
      title={titleEditing ? (
        <Input
          autoFocus
          maxLength={500}
          value={titleDraft}
          aria-label={t('library.bibliographic.editTitle')}
          style={{ width: 'min(680px, 70vw)' }}
          onChange={(event) => setTitleDraft(event.target.value)}
          onPressEnter={() => void saveTitle()}
        />
      ) : (asset?.title || t('resourcePreview.title'))}
      titleExtra={asset?.can_publish && isPdf ? (
        titleEditing ? (
          <Space size={4}>
            <Button
              type="primary"
              size="small"
              loading={titleSaving}
              disabled={!titleDraft.trim()}
              onClick={() => void saveTitle()}
            >
              {t('common.save')}
            </Button>
            <Button size="small" onClick={() => setTitleEditing(false)}>
              {t('common.cancel')}
            </Button>
          </Space>
        ) : (
          <Tooltip title={t('library.bibliographic.editTitle')}>
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              aria-label={t('library.bibliographic.editTitle')}
              onClick={startTitleEdit}
            />
          </Tooltip>
        )
      ) : null}
    >
      {loading ? (
        <div className="resource-detail-loading"><Spin tip={t('common.loading')} /></div>
      ) : null}

      {loadFailed ? (
        <Alert
          type="error"
          showIcon
          message={t('resourcePreview.loadFailed')}
          action={<Button onClick={() => void loadAsset()}>{t('common.retry')}</Button>}
        />
      ) : null}

      {asset ? (
        <div className="resource-detail">
          {asset.withdrawn_warning ? (
            <Alert type="warning" showIcon message={t(asset.withdrawn_warning)} />
          ) : null}

          {!asset.can_preview_content && (asset.source_id || asset.can_request_access) ? (
            <Alert
              type="info"
              showIcon
              message={asset.active_access_request_status === 'pending'
                ? t('library.accessRequestPending')
                : t('resourcePreview.readAccessRequired')}
              action={asset.can_request_access ? (
                <Button type="primary" onClick={openAccessRequest}>
                  {t('library.requestAccess')}
                </Button>
              ) : null}
            />
          ) : null}

          <div className="resource-detail-layout">
            <main className="resource-detail-main">
              <section className="resource-detail-section resource-detail-overview">
                <div className="resource-detail-section-heading">
                  <span>{t('resourcePreview.sectionKicker')}</span>
                  <Typography.Title level={4}>{t('resourcePreview.overview')}</Typography.Title>
                </div>
                {asset.description ? (
                  <Typography.Paragraph className="resource-detail-summary">
                    {asset.description}
                  </Typography.Paragraph>
                ) : null}
                <Descriptions column={{ xs: 1, md: 2 }} size="small">
                  <Descriptions.Item label={t('library.detail.type')}>
                    <Space size={6}>
                      {t(`library.assetType.${asset.asset_type}`, asset.asset_type)}
                      <FileFormatTag filename={asset.original_filename} />
                    </Space>
                  </Descriptions.Item>
                  {asset.original_filename ? (
                    <Descriptions.Item label={t('library.bibliographic.originalFilename')}>
                      <Typography.Text copyable>{asset.original_filename}</Typography.Text>
                    </Descriptions.Item>
                  ) : null}
                  <Descriptions.Item label={t('library.detail.publishedBy')}>
                    {asset.published_by_name || asset.owner_name || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('library.detail.publishedAt')}>
                    {formatDateTime(asset.published_at || asset.created_at, i18n.language)}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('library.detail.updatedAt')}>
                    {formatDateTime(asset.updated_at, i18n.language)}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('library.detail.originProject')}>
                    {asset.origin_project_name || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('project.researchGroup')}>
                    {asset.owning_group_name || t('resource.notProvided')}
                  </Descriptions.Item>
                  {asset.visibility_scope === 'project' ? (
                    <Descriptions.Item label={t('resourcePreview.accessScope')} span={2}>
                      {t('resourcePreview.projectAccessScope')}
                    </Descriptions.Item>
                  ) : null}
                  <Descriptions.Item label={t('library.bibliographic.status')}>
                    {asset.source_id ? (
                      <ProcessingStatusTag
                        state={asset.source_processing_state}
                        progress={asset.source_processing_progress}
                        errorMessage={asset.source_error_message}
                      />
                    ) : t('resource.notProvided')}
                  </Descriptions.Item>
                </Descriptions>
                {isPdf ? (
                  <BibliographicMetadataSection
                    asset={asset}
                    onAssetUpdated={setAsset}
                    variant="management"
                  />
                ) : null}
              </section>

              {canPreview ? (
                <section className="resource-detail-section resource-detail-preview">
                  <PdfPreviewModal
                    inline
                    open
                    sourceId={asset.source_id}
                    title={asset.title}
                    fileName={asset.original_filename || undefined}
                    onClose={() => undefined}
                  />
                </section>
              ) : null}

              {isCollection ? (
                <section className="resource-detail-section">
                  <div className="resource-detail-section-heading">
                    <span>{t('resourcePreview.collectionKicker')}</span>
                    <Typography.Title level={4}>{t('library.viewMembers')}</Typography.Title>
                  </div>
                  <Spin spinning={collectionMembersLoading}>
                    <List
                      dataSource={collectionMembers}
                      locale={{ emptyText: t('group.emptyGroup') }}
                      renderItem={(member) => (
                        <List.Item>
                          <List.Item.Meta
                            avatar={<TeamOutlined />}
                            title={member.child?.name || '-'}
                            description={member.child
                              ? t(`library.assetType.${member.child.type}`, member.child.type)
                              : undefined}
                          />
                        </List.Item>
                      )}
                    />
                  </Spin>
                </section>
              ) : null}
            </main>

            <aside className="resource-detail-sidebar">
              <section className="resource-detail-actions">
                <span className="resource-detail-sidebar-label">
                  {asset.can_grant_training || asset.can_delete
                    ? t('resourcePreview.management')
                    : t('resourcePreview.actions')}
                </span>
                <Typography.Paragraph type="secondary">
                  {asset.can_grant_training || asset.can_delete
                    ? t('resourcePreview.managementHint')
                    : t('resourcePreview.actionsHint')}
                </Typography.Paragraph>
                <Space orientation="vertical" style={{ width: '100%' }}>
                  {asset.can_grant_training && asset.source_processing_state === 'ready' ? (
                    <Button block icon={<SafetyCertificateOutlined />} onClick={() => void openTrainingGrant()}>
                      {t('library.grantTrainingAccess')}
                    </Button>
                  ) : null}
                  {!canPreview && asset.can_request_access ? (
                    <Button block type="primary" onClick={openAccessRequest}>
                      {t('library.requestAccess')}
                    </Button>
                  ) : null}
                  {asset.can_delete && !asset.deleted_at ? (
                    <Popconfirm
                      title={t('library.deleteConfirmTitle')}
                      description={t('library.deleteConfirm')}
                      okText={t('library.delete')}
                      cancelText={t('common.cancel')}
                      okButtonProps={{ danger: true, loading: deleting }}
                      onConfirm={() => void deleteAsset()}
                    >
                      <Button block danger icon={<DeleteOutlined />}>
                        {t('library.delete')}
                      </Button>
                    </Popconfirm>
                  ) : null}
                </Space>
              </section>

              <section className="resource-detail-management-profile">
                <ResourceProfileSection asset={asset} onUpdated={() => void loadAsset()} />
              </section>
            </aside>
          </div>
        </div>
      ) : null}

      <Modal
        title={t('library.requestAccess')}
        open={requestOpen}
        onCancel={() => setRequestOpen(false)}
        onOk={() => void submitAccessRequest()}
        confirmLoading={requestSubmitting}
        okText={t('common.submit')}
        cancelText={t('common.cancel')}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">{asset?.title}</Typography.Paragraph>
        <Form form={requestForm} layout="vertical">
          <Form.Item
            name="purpose"
            label={t('library.accessPurpose')}
            rules={[{ required: true, message: t('library.accessPurposeRequired') }]}
          >
            <Input.TextArea rows={3} placeholder={t('library.accessPurposePlaceholder')} />
          </Form.Item>
          <Form.Item name="duration_days" label={t('library.accessDurationDays')}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('library.grantTrainingAccess')}
        open={trainingGrantOpen}
        onCancel={() => setTrainingGrantOpen(false)}
        onOk={() => void submitTrainingGrant()}
        confirmLoading={trainingGrantSubmitting}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          {t('library.trainingGrantHint')}
        </Typography.Paragraph>
        <Form form={trainingGrantForm} layout="vertical">
          <Form.Item
            name="user_ids"
            label={t('library.trainingGrantRecipients')}
            rules={[{ required: true }]}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              options={trainingRecipients.map((recipient) => ({
                value: recipient.id,
                label: recipient.display_name || recipient.username,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="duration_days"
            label={t('library.trainingGrantDuration')}
            rules={[{ required: true }]}
          >
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </PageContainer>
  );
}
