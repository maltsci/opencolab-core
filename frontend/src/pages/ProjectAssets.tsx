import { ArrowLeftOutlined, DeleteOutlined, FolderOutlined, PlusOutlined, RedoOutlined, UploadOutlined, WarningOutlined } from '@ant-design/icons';
import { Button, Empty, Form, Input, InputNumber, List, Modal, Popconfirm, Radio, Space, Table, Tag, Tooltip, Typography, Upload, message, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { ProcessingStatusTag, PublicationStatusTag, VisibilityTag } from '../components/library/AssetTags';
import { formatDateTime } from '../components/library/library-utils';
import PageContainer from '../components/library/PageContainer';
import SectionCard from '../components/ui/SectionCard';
import { isAcceptedUploadFile } from '../hooks/use-file-drop';
import apiClient from '../services/api-client';
import type {
  LibraryCatalogSearchResult,
  LibraryFullTextSearchResult,
  LibrarySearchResponse,
  ResearchAsset,
} from '../types/research-asset';
import { getDuplicateUploadInfo, showDuplicateUploadModal } from '../utils/duplicate-upload';

interface ProjectOption {
  id: string;
  name: string;
}

export default function ProjectAssets({ embedded = false }: { embedded?: boolean }) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { projectId } = useParams();
  const [assets, setAssets] = useState<ResearchAsset[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [projectSearchResults, setProjectSearchResults] = useState<LibrarySearchResponse | null>(null);
  const [projectSearchLoading, setProjectSearchLoading] = useState(false);
  const [accessRequestAsset, setAccessRequestAsset] = useState<ResearchAsset | null>(null);
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [requestForm] = Form.useForm<{ purpose: string; duration_days: number }>();
  const [showCollectionModal, setShowCollectionModal] = useState(false);
  const [collectionName, setCollectionName] = useState('');
  const [creatingCollection, setCreatingCollection] = useState(false);

  const loadAssets = () => {
    if (!projectId) return;
    setLoading(true);
    apiClient.get(`/projects/${projectId}/assets`)
      .then((response) => setAssets(response.data))
      .catch(() => message.error(t('library.loadFailed')))
      .finally(() => setLoading(false));
  };

  const retrySource = (sourceId: string) => {
    apiClient.post(`/sources/${sourceId}/retry`)
      .then(() => {
        message.success(t('source.retrySuccess'));
        loadAssets();
      })
      .catch(() => message.error(t('source.retryFailed')));
  };

  const openAccessRequest = (asset: ResearchAsset) => {
    setAccessRequestAsset(asset);
    requestForm.setFieldsValue({ purpose: '', duration_days: 30 });
  };

  const submitAccessRequest = async () => {
    if (!accessRequestAsset) return;
    const values = await requestForm.validateFields();
    setRequestSubmitting(true);
    try {
      await apiClient.post(`/research-assets/${accessRequestAsset.id}/access-requests`, values);
      message.success(t('library.accessRequestSubmitted'));
      setAccessRequestAsset(null);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.accessRequestSubmitFailed'));
    } finally {
      setRequestSubmitting(false);
    }
  };

  useEffect(loadAssets, [projectId]);

  useEffect(() => {
    apiClient.get('/projects').then((response) => setProjects(response.data)).catch(() => setProjects([]));
  }, []);

  const searchProjectAssets = async (query: string) => {
    setSearchText(query);
    if (!query.trim() || !projectId) {
      setProjectSearchResults(null);
      return;
    }
    setProjectSearchLoading(true);
    try {
      const { data } = await apiClient.get<LibrarySearchResponse>(
        `/projects/${projectId}/assets/search`,
        { params: { query: query.trim() } },
      );
      setProjectSearchResults(data);
    } catch {
      message.error(t('library.searchFailed'));
    } finally {
      setProjectSearchLoading(false);
    }
  };

  const [publishing, setPublishing] = useState(false);
  const [publishTarget, setPublishTarget] = useState<ResearchAsset | null>(null);
  const [publishScope, setPublishScope] = useState<'lab_public' | 'lab_private'>('lab_public');
  const [deletingAssetId, setDeletingAssetId] = useState<string | null>(null);

  const publishAsset = async (asset: ResearchAsset, visibilityScope: 'lab_private' | 'lab_public') => {
    setPublishing(true);
    try {
      await apiClient.post(`/library/assets/${asset.id}/publish`, {
        visibility_scope: visibilityScope,
        description: asset.description,
        publication_note: '',
      });
      message.success(t('library.publishSuccess'));
      setPublishTarget(null);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.publishFailed'));
    } finally {
      setPublishing(false);
    }
  };

  const openPublishModal = (asset: ResearchAsset) => {
    setPublishTarget(asset);
    setPublishScope('lab_public');
  };

  const deleteAsset = async (asset: ResearchAsset) => {
    setDeletingAssetId(asset.id);
    try {
      await apiClient.post(`/library/assets/${asset.id}/delete`, {});
      message.success(t('library.deleteSuccess'));
      setProjectSearchResults((current) => (
        current ? {
          ...current,
          full_text_results: current.full_text_results.filter((item) => item.id !== asset.id),
          catalog_results: current.catalog_results.filter((item) => item.id !== asset.id),
        } : current
      ));
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.deleteFailed'));
    } finally {
      setDeletingAssetId(null);
    }
  };

  const unlinkAsset = async (assetId: string) => {
    if (!projectId) return;
    try {
      await apiClient.delete(`/projects/${projectId}/assets/${assetId}`);
      message.success(t('library.removeFromProjectSuccess'));
      setProjectSearchResults((current) => (
        current ? {
          ...current,
          full_text_results: current.full_text_results.filter((item) => item.id !== assetId),
          catalog_results: current.catalog_results.filter((item) => item.id !== assetId),
        } : current
      ));
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.removeFromProjectFailed'));
    }
  };

  const confirmUnlink = (assetId: string, title: string) => {
    Modal.confirm({
      title: t('library.removeFromProject'),
      content: `${t('library.removeFromProjectConfirm')} ${title}`,
      okText: t('library.removeFromProject'),
      okButtonProps: { danger: true },
      onOk: () => unlinkAsset(assetId),
    });
  };

  const uploadProjectAsset = async (file: File) => {
    if (!projectId || !isAcceptedUploadFile(file)) {
      return false;
    }
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const { data } = await apiClient.post<ResearchAsset[]>(
        `/projects/${projectId}/assets/upload`,
        formData,
        { timeout: 300000 },
      );
      const duplicateInfo = data.find((asset) => asset.duplicate_info)?.duplicate_info;
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
      }
      message.success(t('projectAssets.uploadSuccess'));
      loadAssets();
    } catch (err: unknown) {
      const duplicateInfo = getDuplicateUploadInfo(err);
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
        return false;
      }
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('projectAssets.uploadFailed'));
    } finally {
      setUploading(false);
    }
    return false;
  };

  const columns: ColumnsType<ResearchAsset> = [
    {
      title: t('library.assetTitle'),
      dataIndex: 'title',
      render: (_, record) => (
        <Space orientation="vertical" size={2} style={{ minWidth: 0, width: '100%' }}>
          <Space size={4} style={{ minWidth: 0, maxWidth: '100%' }}>
            <Tooltip title={record.title}>
              <Typography.Link
                strong
                ellipsis
                href={`/resources/${encodeURIComponent(record.id)}`}
                target="_blank"
                rel="noreferrer"
                style={{ maxWidth: 'min(46vw, 360px)' }}
              >
                {record.title}
              </Typography.Link>
            </Tooltip>
            {record.withdrawn_warning ? (
              <Tooltip title={t(record.withdrawn_warning)}>
                <WarningOutlined style={{ color: token.colorWarning }} />
              </Tooltip>
            ) : null}
          </Space>
          <Typography.Text type="secondary">
            {t(`library.assetType.${record.asset_type}`, record.asset_type)}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: t('library.visibility'),
      dataIndex: 'visibility_scope',
      width: 130,
      render: (value: string) => <VisibilityTag value={value} />,
    },
    {
      title: t('library.assetSource'),
      width: 140,
      render: (_, record) => renderAssetSource(record.id),
    },
    {
      title: t('library.status'),
      dataIndex: 'publication_status',
      width: 180,
      render: (value: string, record) => (
        <Space size={4} wrap>
          <PublicationStatusTag value={value} />
          {record.has_source ?? Boolean(record.source_id) ? (
            <ProcessingStatusTag
              state={record.source_processing_state}
              progress={record.source_processing_progress}
              errorMessage={record.source_error_message}
            />
          ) : (
            <Tag>{t('library.processingStatus.notApplicable')}</Tag>
          )}
          {record.source_processing_state === 'failed' && record.source_id ? (
            <Tooltip title={t('source.retry')}>
              <Button
                size="small"
                type="text"
                icon={<RedoOutlined />}
                aria-label={t('source.retry')}
                onClick={() => retrySource(record.source_id as string)}
              />
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
    {
      title: t('library.updatedAt'),
      dataIndex: 'updated_at',
      width: 180,
      render: (value: string) => formatDateTime(value, i18n.language),
    },
    {
      title: t('common.actions'),
      width: 170,
      render: (_, record) => {
        if (record.origin_project_id === projectId) {
          return (
            <Space size={4}>
              {record.can_publish ? (
                <Button size="small" onClick={() => openPublishModal(record)}>
                  {t('library.publishToLab')}
                </Button>
              ) : null}
              <Popconfirm
                title={t('library.deleteConfirmTitle')}
                description={t('library.deleteConfirm')}
                okText={t('library.delete')}
                cancelText={t('common.cancel')}
                okButtonProps={{ danger: true, loading: deletingAssetId === record.id }}
                onConfirm={() => deleteAsset(record)}
                disabled={!record.can_publish}
              >
                <Tooltip title={t('library.delete')}>
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    disabled={!record.can_publish}
                    aria-label={t('library.delete')}
                  />
                </Tooltip>
              </Popconfirm>
            </Space>
          );
        }
        return (
          <Space size={4}>
            {record.can_request_access ? (
              <Button size="small" type="primary" onClick={() => openAccessRequest(record)}>
                {t('library.requestAccess')}
              </Button>
            ) : null}
            <Button danger size="small" type="link" onClick={() => confirmUnlink(record.id, record.title)}>
              {t('library.removeFromProject')}
            </Button>
          </Space>
        );
      },
    },
  ];

  const normalizedSearch = searchText.trim().toLowerCase();
  // In embedded mode collections are shown in their own section below.
  const visibleAssets = assets.filter((asset) => {
    if (embedded && asset.source_type === 'group') return false;
    if (!normalizedSearch) return true;
    const haystack = `${asset.title} ${asset.description || ''}`.toLowerCase();
    return haystack.includes(normalizedSearch);
  });
  const collections = assets.filter((asset) => asset.source_type === 'group');

  const createCollection = async () => {
    const name = collectionName.trim();
    if (!name || !projectId) return;
    setCreatingCollection(true);
    try {
      await apiClient.post('/sources/groups', { name, project_id: projectId });
      setShowCollectionModal(false);
      setCollectionName('');
      message.success(t('projectAssets.collectionCreated'));
      loadAssets();
    } catch {
      message.error(t('projectAssets.collectionCreateFailed'));
    } finally {
      setCreatingCollection(false);
    }
  };

  const currentProject = projects.find((project) => project.id === projectId);

  const isProjectOriginAsset = (assetId: string) => (
    assets.find((item) => item.id === assetId)?.origin_project_id === projectId
  );

  const renderAssetSource = (assetId: string) => (
    isProjectOriginAsset(assetId) ? (
      <Tag>{t('library.projectOrigin')}</Tag>
    ) : (
      <Tag>{t('library.labLibrarySource')}</Tag>
    )
  );

  const renderSearchMetadata = (item: LibraryCatalogSearchResult) => {
    const values = [
      item.authors.join(', '),
      item.tags.join(', '),
      item.steward_name,
      item.project_name,
      item.date,
    ].filter(Boolean);
    return values.join(' · ');
  };

  const renderSearchTitle = (item: LibraryCatalogSearchResult) => (
    <Space size={6} wrap>
      <Tooltip title={item.title}>
        <Typography.Link
          strong
          ellipsis
          href={`/resources/${encodeURIComponent(item.id)}`}
          target="_blank"
          rel="noreferrer"
          style={{ display: 'inline-block', maxWidth: 'min(42vw, 320px)' }}
        >
          {item.title}
        </Typography.Link>
      </Tooltip>
      {renderAssetSource(item.id)}
    </Space>
  );

  const renderSearchActions = (assetId: string, title: string) => {
    const asset = assets.find((item) => item.id === assetId);
    if (isProjectOriginAsset(assetId)) {
      if (!asset) return [];
      return [
        <Popconfirm
          key="delete"
          title={t('library.deleteConfirmTitle')}
          description={t('library.deleteConfirm')}
          okText={t('library.delete')}
          cancelText={t('common.cancel')}
          okButtonProps={{ danger: true, loading: deletingAssetId === assetId }}
          onConfirm={() => deleteAsset(asset)}
          disabled={!asset.can_publish}
        >
          <Button
            danger
            size="small"
            type="link"
            icon={<DeleteOutlined />}
            disabled={!asset.can_publish}
            aria-label={t('library.delete')}
          />
        </Popconfirm>,
      ];
    }
    return [
      <Button
        danger
        key="unlink"
        size="small"
        type="link"
        onClick={() => confirmUnlink(assetId, title)}
      >
        {t('library.removeFromProject')}
      </Button>,
    ];
  };

  const renderFullTextResult = (item: LibraryFullTextSearchResult) => (
    <List.Item actions={renderSearchActions(item.id, item.title)}>
      <List.Item.Meta title={renderSearchTitle(item)} description={renderSearchMetadata(item)} />
      <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0, maxWidth: 560 }}>
        {item.snippet}
      </Typography.Paragraph>
    </List.Item>
  );

  const renderCatalogResult = (item: LibraryCatalogSearchResult) => (
    <List.Item actions={renderSearchActions(item.id, item.title)}>
      <List.Item.Meta title={renderSearchTitle(item)} description={renderSearchMetadata(item)} />
      <Typography.Text type="secondary">{t('library.catalogOnly')}</Typography.Text>
    </List.Item>
  );

  const uploadButton = (
    <Upload beforeUpload={uploadProjectAsset} showUploadList={false} multiple accept=".pdf,.docx,.txt,.md,.zip">
      <Button type="primary" icon={<UploadOutlined />} loading={uploading} disabled={uploading}>
        {uploading ? t('projectAssets.uploading') : t('projectAssets.upload')}
      </Button>
    </Upload>
  );

  const content = (
    <>
      <Space orientation="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Input.Search
            allowClear
            placeholder={t('library.searchProjectPlaceholder')}
            style={{ width: 260 }}
            loading={projectSearchLoading}
            onSearch={searchProjectAssets}
            onChange={(event) => {
              const value = event.target.value;
              setSearchText(value);
              if (!value.trim()) setProjectSearchResults(null);
            }}
          />
        </div>
        {projectSearchResults ? (
          <Space orientation="vertical" style={{ width: '100%' }} size="middle">
            {!projectSearchResults.full_text_search_available ? (
              <Typography.Text type="warning">
                {t('library.fullTextSearchUnavailable')}
              </Typography.Text>
            ) : null}
            <List
              bordered
              loading={projectSearchLoading}
              header={t('library.fullTextResults')}
              locale={{ emptyText: t('library.noFullTextResults') }}
              dataSource={projectSearchResults.full_text_results}
              renderItem={renderFullTextResult}
            />
            <List
              bordered
              header={t('library.catalogResults')}
              locale={{ emptyText: t('library.noCatalogResults') }}
              dataSource={projectSearchResults.catalog_results}
              renderItem={renderCatalogResult}
            />
          </Space>
        ) : (
          <Table
            rowKey="id"
            dataSource={visibleAssets}
            columns={columns}
            loading={loading}
            size="middle"
            scroll={{ x: 'max-content' }}
            pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
            locale={{ emptyText: loading ? null : <Empty description={t('library.projectEmpty')} /> }}
          />
        )}
      </Space>

      <Modal
        title={t('library.publishToLab')}
        open={!!publishTarget}
        onCancel={() => setPublishTarget(null)}
        onOk={() => publishTarget && publishAsset(publishTarget, publishScope)}
        okText={t('library.publishToLab')}
        cancelText={t('common.cancel')}
        confirmLoading={publishing}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">{publishTarget?.title}</Typography.Paragraph>
        <Radio.Group
          value={publishScope}
          onChange={(event) => setPublishScope(event.target.value)}
          style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
        >
          <Radio value="lab_public">
            <Space orientation="vertical" size={0}>
              <Typography.Text>{t('library.publishPublic')}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('library.publishPublicDesc')}
              </Typography.Text>
            </Space>
          </Radio>
          <Radio value="lab_private">
            <Space orientation="vertical" size={0}>
              <Typography.Text>{t('library.publishPrivate')}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('library.publishPrivateDesc')}
              </Typography.Text>
            </Space>
          </Radio>
        </Radio.Group>
      </Modal>
      <Modal
        title={t('library.requestAccess')}
        open={!!accessRequestAsset}
        onCancel={() => setAccessRequestAsset(null)}
        onOk={submitAccessRequest}
        confirmLoading={requestSubmitting}
      >
        <Form form={requestForm} layout="vertical" initialValues={{ duration_days: 30 }}>
          <Typography.Paragraph type="secondary">
            {accessRequestAsset?.title}
          </Typography.Paragraph>
          <Form.Item
            name="purpose"
            label={t('library.accessPurpose')}
            rules={[{ required: true, message: t('library.accessPurposeRequired') }]}
          >
            <Input.TextArea rows={4} placeholder={t('library.accessPurposePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="duration_days"
            label={t('library.accessDurationDays')}
            rules={[{ required: true }]}
          >
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
      {embedded && (
        <div style={{ marginTop: 24 }}>
          <SectionCard
            title={t('library.collectionsTab')}
            extra={(
              <Button icon={<PlusOutlined />} onClick={() => setShowCollectionModal(true)}>
                {t('projectAssets.newCollection')}
              </Button>
            )}
          >
            <List
              size="small"
              dataSource={collections}
              locale={{ emptyText: loading ? null : <Empty description={t('projectAssets.collectionEmpty')} /> }}
              renderItem={(asset) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={<FolderOutlined />}
                    title={(
                      <Typography.Link
                        href={`/resources/${encodeURIComponent(asset.id)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {asset.title}
                      </Typography.Link>
                    )}
                    description={formatDateTime(asset.created_at, i18n.language)}
                  />
                </List.Item>
              )}
            />
          </SectionCard>
        </div>
      )}
      <Modal
        title={t('projectAssets.newCollection')}
        open={showCollectionModal}
        onCancel={() => setShowCollectionModal(false)}
        onOk={createCollection}
        confirmLoading={creatingCollection}
        okButtonProps={{ disabled: !collectionName.trim() }}
        destroyOnHidden
      >
        <Input
          value={collectionName}
          onChange={(event) => setCollectionName(event.target.value)}
          onPressEnter={createCollection}
          placeholder={t('projectAssets.collectionNamePlaceholder')}
          maxLength={200}
          autoFocus
        />
      </Modal>
    </>
  );

  if (embedded) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
          {uploadButton}
        </div>
        {content}
      </div>
    );
  }

  return (
    <PageContainer
      title={currentProject ? `${t('library.projectTitle')} · ${currentProject.name}` : t('library.projectTitle')}
      extra={(
        <Space>
          {uploadButton}
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
            {t('common.back')}
          </Button>
        </Space>
      )}
    >
      {content}
    </PageContainer>
  );
}
