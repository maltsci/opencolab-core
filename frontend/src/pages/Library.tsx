import { CheckOutlined, CloseOutlined, DatabaseOutlined, DeleteOutlined, FileSearchOutlined, LinkOutlined, RedoOutlined, UndoOutlined, UploadOutlined, WarningOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, List, Modal, Popconfirm, Segmented, Select, Space, Table, Tabs, Tag, Tooltip, Typography, Upload, message, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import {
  FileFormatTag,
  ProcessingStatusTag,
  PublicationStatusTag,
  VisibilityTag,
} from '../components/library/AssetTags';
import ExtractionDrawer from '../components/library/ExtractionDrawer';
import { formatDateTime } from '../components/library/library-utils';
import PageContainer from '../components/library/PageContainer';
import apiClient from '../services/api-client';
import type {
  AssetAccessRequest,
  LibraryCatalogSearchResult,
  LibraryFullTextSearchResult,
  LibrarySearchResponse,
  ResearchAsset,
} from '../types/research-asset';
import type { PersonDirectoryEntry } from '../types/person';
import type { ResearchDirectionPage } from '../types/research-direction';
import { getDuplicateUploadInfo, showDuplicateUploadModal } from '../utils/duplicate-upload';
import Sources from './Sources';

interface ProjectOption {
  id: string;
  name: string;
}

interface ExtractionTarget {
  sourceId: string;
  name: string;
  processingState: string | null;
}

interface AccessRequestTarget {
  id: string;
  title: string;
}

interface DataPackageFormValues {
  file: UploadFile[];
  title: string;
  description?: string;
  tags?: string[];
}

interface ManualResourceFormValues {
  title: string;
  asset_type: 'dataset' | 'code_repository' | 'model_weight' | 'gpu' | 'external_reference';
  description?: string;
  visibility_scope: 'lab_public' | 'lab_private';
}

const ASSET_TYPE_OPTIONS = [
  'uploaded_file',
  'generated_doc',
  'research_memory',
  'report',
  'dataset',
  'code_repository',
  'model_weight',
  'gpu',
  'protocol',
  'external_reference',
  'collection',
];

export default function Library() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab') ?? 'assets';
  const requestedRequestId = searchParams.get('request');
  const activeTab = ['assets', 'collections', 'mine', 'my-requests', 'pending-requests'].includes(requestedTab)
    ? requestedTab : 'assets';
  const searchFromAssistant = searchParams.get('search');
  const selectedAssetId = searchParams.get('asset');
  const { token } = theme.useToken();
  const [assets, setAssets] = useState<ResearchAsset[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [bulkUpdating, setBulkUpdating] = useState(false);
  const [uploadVisibility, setUploadVisibility] = useState<'lab_public' | 'lab_private'>('lab_public');
  const [visibilityFilter, setVisibilityFilter] = useState<'all' | 'lab_public' | 'lab_private'>('all');
  const [assetStateFilter, setAssetStateFilter] = useState<'active' | 'deleted'>('active');
  const [searchText, setSearchText] = useState('');
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [directionFilter, setDirectionFilter] = useState<string | null>(null);
  const [stewardFilter, setStewardFilter] = useState<string | null>(null);
  const [directions, setDirections] = useState<Array<{ id: string; name: string }>>([]);
  const [stewards, setStewards] = useState<PersonDirectoryEntry[]>([]);
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const [accessRequestAsset, setAccessRequestAsset] = useState<AccessRequestTarget | null>(null);
  const [requestProjectRequired, setRequestProjectRequired] = useState(false);
  const [requestSubmitting, setRequestSubmitting] = useState(false);
  const [myRequests, setMyRequests] = useState<AssetAccessRequest[]>([]);
  const [pendingRequests, setPendingRequests] = useState<AssetAccessRequest[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(false);
  const [requestForm] = Form.useForm<{ purpose: string; duration_days: number; project_id?: string }>();
  const [librarySearchResults, setLibrarySearchResults] = useState<LibrarySearchResponse | null>(null);
  const [librarySearchLoading, setLibrarySearchLoading] = useState(false);
  const [linkingSearchAsset, setLinkingSearchAsset] = useState<AccessRequestTarget | null>(null);
  const [linkingProjectId, setLinkingProjectId] = useState<string | null>(null);
  const [extractionTarget, setExtractionTarget] = useState<ExtractionTarget | null>(null);
  const [dataPackageOpen, setDataPackageOpen] = useState(false);
  const [dataPackageUploading, setDataPackageUploading] = useState(false);
  const [manualResourceOpen, setManualResourceOpen] = useState(false);
  const [manualResourceSaving, setManualResourceSaving] = useState(false);
  const [dataPackageForm] = Form.useForm<DataPackageFormValues>();
  const [manualResourceForm] = Form.useForm<ManualResourceFormValues>();

  const loadAssets = () => {
    setLoading(true);
    apiClient.get('/library/assets', {
      params: {
        include_deleted: assetStateFilter === 'deleted',
        asset_type: typeFilter || undefined,
        direction_id: directionFilter || undefined,
        steward_user_id: stewardFilter || undefined,
        visibility_scope: visibilityFilter === 'all' ? undefined : visibilityFilter,
      },
    })
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

  const loadRequests = () => {
    setRequestsLoading(true);
    Promise.all([
      apiClient.get<AssetAccessRequest[]>('/research-assets/access-requests/my'),
      apiClient.get<AssetAccessRequest[]>('/research-assets/access-requests/pending'),
    ])
      .then(([myResponse, pendingResponse]) => {
        setMyRequests(myResponse.data);
        setPendingRequests(pendingResponse.data);
      })
      .catch(() => message.error(t('library.accessRequestLoadFailed')))
      .finally(() => setRequestsLoading(false));
  };

  useEffect(() => {
    loadAssets();
    loadRequests();
    apiClient.get('/projects').then((response) => setProjects(response.data)).catch(() => setProjects([]));
  }, [assetStateFilter, directionFilter, stewardFilter, typeFilter, visibilityFilter, requestedRequestId]);

  useEffect(() => {
    Promise.all([
      apiClient.get<ResearchDirectionPage>('/research-directions', {
        params: { status: 'active', limit: 100 },
      }),
      apiClient.get<PersonDirectoryEntry[]>('/people'),
    ])
      .then(([directionsResponse, peopleResponse]) => {
        setDirections(directionsResponse.data.items);
        setStewards(peopleResponse.data);
      })
      .catch(() => {
        setDirections([]);
        setStewards([]);
      });
  }, []);

  const openAccessRequest = (asset: AccessRequestTarget, requireProject = false) => {
    setAccessRequestAsset(asset);
    setRequestProjectRequired(requireProject);
    requestForm.setFieldsValue({ purpose: '', duration_days: 30, project_id: undefined });
  };

  const searchLibrary = async (query: string) => {
    setSearchText(query);
    if (!query.trim()) {
      setLibrarySearchResults(null);
      return;
    }
    setLibrarySearchLoading(true);
    try {
      const { data } = await apiClient.get<LibrarySearchResponse>('/library/assets/search', {
        params: { query: query.trim() },
      });
      setLibrarySearchResults(data);
    } catch {
      message.error(t('library.searchFailed'));
    } finally {
      setLibrarySearchLoading(false);
    }
  };

  useEffect(() => {
    if (!searchFromAssistant) return;
    void searchLibrary(searchFromAssistant);
  }, [searchFromAssistant]);

  useEffect(() => {
    if (!selectedAssetId) return;
    navigate(`/resources/${encodeURIComponent(selectedAssetId)}`, { replace: true });
  }, [navigate, selectedAssetId]);

  const linkSearchAssetToProject = async () => {
    if (!linkingSearchAsset || !linkingProjectId) return;
    try {
      await apiClient.post('/library/assets/bulk-link', {
        asset_ids: [linkingSearchAsset.id],
        project_ids: [linkingProjectId],
        link_type: 'reference',
      });
      message.success(t('library.linkSuccess'));
      setLinkingSearchAsset(null);
      setLinkingProjectId(null);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (detail === 'Project access request required') {
        const asset = linkingSearchAsset;
        const projectId = linkingProjectId;
        setLinkingSearchAsset(null);
        setLinkingProjectId(null);
        if (asset && projectId) {
          openAccessRequest(asset, true);
          requestForm.setFieldValue('project_id', projectId);
        }
        return;
      }
      message.error(detail || t('library.linkFailed'));
    }
  };

  const submitAccessRequest = async () => {
    if (!accessRequestAsset) return;
    const values = await requestForm.validateFields();
    setRequestSubmitting(true);
    try {
      await apiClient.post(`/research-assets/${accessRequestAsset.id}/access-requests`, values);
      message.success(t('library.accessRequestSubmitted'));
      setAccessRequestAsset(null);
      setRequestProjectRequired(false);
      loadAssets();
      loadRequests();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.accessRequestSubmitFailed'));
    } finally {
      setRequestSubmitting(false);
    }
  };

  const reviewAccessRequest = async (requestId: string, action: 'approve' | 'reject') => {
    try {
      await apiClient.post(`/research-assets/access-requests/${requestId}/${action}`, {});
      message.success(t(action === 'approve' ? 'library.accessRequestApproved' : 'library.accessRequestRejected'));
      loadAssets();
      loadRequests();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.accessRequestReviewFailed'));
    }
  };

  const cancelAccessRequest = async (requestId: string) => {
    try {
      await apiClient.post(`/research-assets/access-requests/${requestId}/cancel`);
      message.success(t('library.accessRequestCanceled'));
      loadAssets();
      loadRequests();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.accessRequestCancelFailed'));
    }
  };

  const uploadAsset = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('visibility_scope', uploadVisibility);
    try {
      const { data } = await apiClient.post<ResearchAsset[]>('/library/assets/upload', formData, { timeout: 300000 });
      message.success(t('library.uploadSuccess'));
      const duplicateInfo = data.find((asset) => asset.duplicate_info)?.duplicate_info;
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
      }
      setSelectedAssetIds([]);
      loadAssets();
    } catch (err: unknown) {
      const duplicateInfo = getDuplicateUploadInfo(err);
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
        return false;
      }
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.uploadFailed'));
    } finally {
      setUploading(false);
    }
    return false;
  };

  const submitDataPackage = async () => {
    const values = await dataPackageForm.validateFields();
    const file = values.file[0]?.originFileObj;
    if (!file) return;
    setDataPackageUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('visibility_scope', uploadVisibility);
    formData.append('upload_kind', 'data_package');
    formData.append('meta_title', values.title);
    if (values.description) formData.append('meta_description', values.description);
    if (values.tags && values.tags.length > 0) formData.append('meta_tags', values.tags.join(','));
    try {
      await apiClient.post<ResearchAsset[]>('/library/assets/upload', formData, { timeout: 300000 });
      message.success(t('library.dataPackageSuccess'));
      setDataPackageOpen(false);
      dataPackageForm.resetFields();
      setSelectedAssetIds([]);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.dataPackageFailed'));
    } finally {
      setDataPackageUploading(false);
    }
  };

  const submitManualResource = async () => {
    const values = await manualResourceForm.validateFields();
    setManualResourceSaving(true);
    try {
      await apiClient.post('/library/assets/catalog', values);
      setManualResourceOpen(false);
      manualResourceForm.resetFields();
      message.success(t('library.manualResourceSuccess'));
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.manualResourceFailed'));
    } finally {
      setManualResourceSaving(false);
    }
  };

  const bulkPublishAssets = async (visibilityScope: 'lab_public' | 'lab_private') => {
    if (selectedAssetIds.length === 0) return;
    setBulkUpdating(true);
    try {
      await apiClient.post('/library/assets/bulk-publish', {
        asset_ids: selectedAssetIds,
        visibility_scope: visibilityScope,
      });
      message.success(t('library.bulkUpdateSuccess'));
      setSelectedAssetIds([]);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.bulkUpdateFailed'));
    } finally {
      setBulkUpdating(false);
    }
  };

  const runDeleteAssets = async (assetIds: string[]) => {
    if (assetIds.length === 0) return;
    setBulkUpdating(true);
    try {
      await Promise.all(assetIds.map((assetId) => (
        apiClient.post(`/library/assets/${assetId}/delete`, {})
      )));
      message.success(t('library.deleteSuccess'));
      setSelectedAssetIds([]);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.deleteFailed'));
    } finally {
      setBulkUpdating(false);
    }
  };

  const deleteAssets = async (assetIds: string[]) => {
    if (assetIds.length === 0) return;
    Modal.confirm({
      title: t('library.deleteConfirmTitle'),
      content: t('library.deleteConfirm'),
      okText: t('library.delete'),
      okButtonProps: { danger: true },
      onOk: () => runDeleteAssets(assetIds),
    });
  };

  const restoreAssets = async (assetIds: string[]) => {
    if (assetIds.length === 0) return;
    setBulkUpdating(true);
    try {
      await Promise.all(assetIds.map((assetId) => (
        apiClient.post(`/library/assets/${assetId}/restore`)
      )));
      message.success(t('library.restoreSuccess'));
      setSelectedAssetIds([]);
      loadAssets();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('library.restoreFailed'));
    } finally {
      setBulkUpdating(false);
    }
  };

  const columns: ColumnsType<ResearchAsset> = [
    {
      title: t('library.assetTitle'),
      dataIndex: 'title',
      width: 420,
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
            <FileFormatTag filename={record.original_filename} />
            {record.withdrawn_warning ? (
              <Tooltip title={t(record.withdrawn_warning)}>
                <WarningOutlined style={{ color: token.colorWarning }} />
              </Tooltip>
            ) : null}
            {record.source_type === 'data_package' ? (
              <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>{t('library.dataPackageTag')}</Tag>
            ) : null}
          </Space>
          <Typography.Text
            type="secondary"
            ellipsis={{ tooltip: record.description }}
            style={{ maxWidth: 'min(46vw, 360px)' }}
          >
            {record.original_filename && record.original_filename !== record.title
              ? record.original_filename
              : t(`library.assetType.${record.asset_type}`, record.asset_type)}
            {record.description ? ` · ${record.description}` : ''}
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
      width: 140,
      render: (_, record) => (
        <Space size={4}>
          {!record.deleted_at ? (
            <Tooltip title={t('library.linkToProject')}>
              <Button
                size="small"
                type="text"
                icon={<LinkOutlined />}
                onClick={() => setLinkingSearchAsset({ id: record.id, title: record.title })}
                aria-label={t('library.linkToProject')}
              />
            </Tooltip>
          ) : null}
          {!record.deleted_at && record.source_id && record.asset_type !== 'collection' && record.can_preview_content ? (
            <Tooltip title={t('source.extraction')}>
              <Button
                size="small"
                type="text"
                icon={<FileSearchOutlined />}
                onClick={() => setExtractionTarget({
                  sourceId: record.source_id as string,
                  name: record.title,
                  processingState: record.source_processing_state,
                })}
              />
            </Tooltip>
          ) : null}
          {record.deleted_at ? (
            <Tooltip title={t('library.restore')}>
              <Button
                size="small"
                type="text"
                icon={<UndoOutlined />}
                disabled={!record.can_publish}
                onClick={() => restoreAssets([record.id])}
              />
            </Tooltip>
          ) : (
            <Popconfirm
              title={t('library.deleteConfirmTitle')}
              description={t('library.deleteConfirm')}
              okText={t('library.delete')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true, loading: bulkUpdating }}
              onConfirm={() => runDeleteAssets([record.id])}
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
          )}
          {!record.deleted_at && !record.can_preview_content && record.can_request_access ? (
            <Button size="small" type="link" onClick={() => openAccessRequest(record)}>
              {t('library.requestAccess')}
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];

  const normalizedSearch = searchText.trim().toLowerCase();
  const visibleAssets = assets.filter((asset) => {
    if (normalizedSearch) {
      const identifiers = Object.values(asset.bibliographic_summary || {}).join(' ');
      const haystack = `${asset.title} ${asset.original_filename || ''} ${asset.description || ''} ${identifiers}`.toLowerCase();
      if (!haystack.includes(normalizedSearch)) return false;
    }
    return true;
  });
  const requestColumns: ColumnsType<AssetAccessRequest> = [
    {
      title: t('library.assetTitle'),
      dataIndex: 'asset_title',
      render: (value: string | null, record) => value ? (
        <Button type="link" onClick={() => navigate(`/resources/${record.research_asset_id}`)}>
          {value}
        </Button>
      ) : t('uploadDuplicate.requestedMaterial', { sourceId: record.source_id || record.research_asset_id }),
    },
    {
      title: t('library.accessRequester'),
      dataIndex: 'requester_name',
      width: 140,
      render: (value: string | null) => value || '-',
    },
    {
      title: t('library.accessPurpose'),
      dataIndex: 'purpose',
      ellipsis: true,
    },
    {
      title: t('library.accessStatus'),
      dataIndex: 'status',
      width: 120,
      render: (value: string) => <Tag>{t(`library.accessStatus.${value}`, value)}</Tag>,
    },
    {
      title: t('library.accessGrantedUntil'),
      dataIndex: 'grant_valid_until',
      width: 180,
      render: (value: string | null) => formatDateTime(value, i18n.language),
    },
  ];

  const pendingRequestColumns: ColumnsType<AssetAccessRequest> = [
    ...requestColumns,
    {
      title: t('common.actions'),
      width: 180,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            type="primary"
            icon={<CheckOutlined />}
            onClick={() => reviewAccessRequest(record.id, 'approve')}
          >
            {t('library.approve')}
          </Button>
          <Button
            size="small"
            icon={<CloseOutlined />}
            onClick={() => reviewAccessRequest(record.id, 'reject')}
          >
            {t('library.reject')}
          </Button>
        </Space>
      ),
    },
  ];

  const myRequestColumns: ColumnsType<AssetAccessRequest> = [
    ...requestColumns,
    {
      title: t('common.actions'),
      width: 120,
      render: (_, record) => record.status === 'pending' ? (
        <Button size="small" onClick={() => cancelAccessRequest(record.id)}>
          {t('library.cancelRequest')}
        </Button>
      ) : null,
    },
  ];

  const uploadControls = (
    <Space wrap>
      <Select
        size="middle"
        value={uploadVisibility}
        onChange={setUploadVisibility}
        style={{ width: 150 }}
        options={[
          { value: 'lab_public', label: t('library.uploadPublic') },
          { value: 'lab_private', label: t('library.uploadPrivate') },
        ]}
      />
      <Upload beforeUpload={uploadAsset} showUploadList={false} multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.tsv,.txt,.md,.json,.jsonl,.png,.jpg,.jpeg,.tif,.tiff,.bam,.sam,.fastq,.fq,.fasta,.fa,.seq,.zip">
        <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
          {t('library.upload')}
        </Button>
      </Upload>
      <Button icon={<DatabaseOutlined />} onClick={() => setDataPackageOpen(true)}>
        {t('library.dataPackageButton')}
      </Button>
      <Button onClick={() => {
        manualResourceForm.setFieldsValue({ visibility_scope: uploadVisibility });
        setManualResourceOpen(true);
      }}>
        {t('library.manualResourceButton')}
      </Button>
    </Space>
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
    <Tooltip title={item.title}>
      <Typography.Link
        strong
        ellipsis
        href={`/resources/${encodeURIComponent(item.id)}`}
        target="_blank"
        rel="noreferrer"
        style={{ display: 'inline-block', maxWidth: 'min(46vw, 360px)' }}
      >
        {item.title}
      </Typography.Link>
    </Tooltip>
  );

  const renderFullTextResult = (item: LibraryFullTextSearchResult) => (
    <List.Item
      actions={[
        <Button
          key="link"
          size="small"
          type="link"
          onClick={() => setLinkingSearchAsset({ id: item.id, title: item.title })}
        >
          {t('library.linkToProject')}
        </Button>,
      ]}
    >
      <List.Item.Meta title={renderSearchTitle(item)} description={renderSearchMetadata(item)} />
      <Typography.Paragraph ellipsis={{ rows: 2 }} style={{ marginBottom: 0, maxWidth: 560 }}>
        {item.snippet}
      </Typography.Paragraph>
    </List.Item>
  );

  const renderCatalogResult = (item: LibraryCatalogSearchResult) => (
    <List.Item
      actions={item.can_request_access ? [
        <Button
          key="request"
          size="small"
          type="link"
          onClick={() => openAccessRequest({ id: item.id, title: item.title }, true)}
        >
          {t('library.requestAccessAndLink')}
        </Button>,
      ] : undefined}
    >
      <List.Item.Meta title={renderSearchTitle(item)} description={renderSearchMetadata(item)} />
      <Typography.Text type="secondary">{t('library.catalogOnly')}</Typography.Text>
    </List.Item>
  );

  return (
    <PageContainer
      title={t('library.title')}
      description={t('library.pageDescription')}
      extra={uploadControls}
    >
      <Tabs
        activeKey={activeTab}
        onChange={(tab) => setSearchParams((previous) => {
          const next = new URLSearchParams(previous);
          next.set('tab', tab);
          next.delete('request');
          return next;
        })}
        items={[
          {
            key: 'assets',
            label: t('library.assetsTab'),
            children: (
              <Space orientation="vertical" style={{ width: '100%' }} size="middle">
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <Space wrap>
                    <Input.Search
                      allowClear
                      placeholder={t('library.searchLibraryPlaceholder')}
                      style={{ width: 260 }}
                      onSearch={searchLibrary}
                      onChange={(event) => setSearchText(event.target.value)}
                    />
                    <Select
                      allowClear
                      placeholder={t('library.typeFilter')}
                      style={{ width: 150 }}
                      value={typeFilter}
                      onChange={(value) => setTypeFilter(value ?? null)}
                      options={ASSET_TYPE_OPTIONS.map((assetType) => ({
                        value: assetType,
                        label: t(`library.assetType.${assetType}`, assetType),
                      }))}
                    />
                    <Select
                      allowClear
                      placeholder={t('library.directionFilter')}
                      style={{ width: 180 }}
                      value={directionFilter}
                      onChange={(value) => setDirectionFilter(value ?? null)}
                      options={directions.map((direction) => ({
                        value: direction.id,
                        label: direction.name,
                      }))}
                    />
                    <Select
                      allowClear
                      placeholder={t('library.stewardFilter')}
                      style={{ width: 170 }}
                      value={stewardFilter}
                      onChange={(value) => setStewardFilter(value ?? null)}
                      options={stewards.map((person) => ({
                        value: person.id,
                        label: person.display_name || person.username,
                      }))}
                    />
                  </Space>
                  <Segmented
                    value={assetStateFilter}
                    onChange={(value) => {
                      setAssetStateFilter(value as 'active' | 'deleted');
                      setSelectedAssetIds([]);
                    }}
                    options={[
                      { value: 'active', label: t('library.filterAvailable') },
                      { value: 'deleted', label: t('library.filterDeleted') },
                    ]}
                  />
                  <Segmented
                    value={visibilityFilter}
                    onChange={(value) => setVisibilityFilter(value as 'all' | 'lab_public' | 'lab_private')}
                    options={[
                      { value: 'all', label: t('library.filterAll') },
                      { value: 'lab_public', label: t('library.filterPublic') },
                      { value: 'lab_private', label: t('library.filterPrivate') },
                    ]}
                  />
                </div>
                {librarySearchResults ? (
                  <Space orientation="vertical" style={{ width: '100%' }} size="middle">
                    {!librarySearchResults.full_text_search_available ? (
                      <Typography.Text type="warning">
                        {t('library.fullTextSearchUnavailable')}
                      </Typography.Text>
                    ) : null}
                    <List
                      bordered
                      loading={librarySearchLoading}
                      header={t('library.fullTextResults')}
                      locale={{ emptyText: t('library.noFullTextResults') }}
                      dataSource={librarySearchResults.full_text_results}
                      renderItem={renderFullTextResult}
                    />
                    <List
                      bordered
                      header={t('library.catalogResults')}
                      locale={{ emptyText: t('library.noCatalogResults') }}
                      dataSource={librarySearchResults.catalog_results}
                      renderItem={renderCatalogResult}
                    />
                  </Space>
                ) : null}
                {selectedAssetIds.length > 0 ? (
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 12,
                      padding: '8px 12px',
                      border: `1px solid ${token.colorInfoBorder}`,
                      borderRadius: token.borderRadius,
                      background: token.colorInfoBg,
                    }}
                  >
                    <Typography.Text>
                      {t('library.selectedCount', { count: selectedAssetIds.length })}
                    </Typography.Text>
                    <Space wrap>
                      {assetStateFilter === 'deleted' ? (
                        <Button
                          icon={<UndoOutlined />}
                          loading={bulkUpdating}
                          onClick={() => restoreAssets(selectedAssetIds)}
                        >
                          {t('library.restore')}
                        </Button>
                      ) : (
                        <>
                          <Button loading={bulkUpdating} onClick={() => bulkPublishAssets('lab_public')}>
                            {t('library.setPublic')}
                          </Button>
                          <Button loading={bulkUpdating} onClick={() => bulkPublishAssets('lab_private')}>
                            {t('library.setPrivate')}
                          </Button>
                          <Button
                            danger
                            icon={<DeleteOutlined />}
                            loading={bulkUpdating}
                            onClick={() => deleteAssets(selectedAssetIds)}
                          >
                            {t('library.delete')}
                          </Button>
                        </>
                      )}
                    </Space>
                  </div>
                ) : null}
                <Table
                  rowKey="id"
                  dataSource={visibleAssets}
                  columns={columns}
                  loading={loading}
                  size="middle"
                  tableLayout="fixed"
                  scroll={{ x: 1060 }}
                  pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
                  rowSelection={{
                    selectedRowKeys: selectedAssetIds,
                    onChange: (keys) => setSelectedAssetIds(keys as string[]),
                    getCheckboxProps: (record) => ({ disabled: !record.can_publish && !record.deleted_at }),
                  }}
                />
              </Space>
            ),
          },
          {
            key: 'collections',
            label: t('library.collectionsTab'),
            children: <Sources embedded allowedTabs={['groups']} defaultTab="groups" />,
          },
          {
            key: 'mine',
            label: t('library.myMaterialsTab'),
            children: <Sources embedded allowedTabs={['files', 'notes']} defaultTab="files" />,
          },
          {
            key: 'my-requests',
            label: t('library.myRequestsTab'),
            children: (
              <Table
                rowKey="id"
                dataSource={myRequests}
                key={`${requestedRequestId ?? 'my-requests'}:${myRequests.findIndex((row) => row.id === requestedRequestId)}`}
                onRow={(record) => ({ style: record.id === requestedRequestId ? { background: token.colorInfoBg } : undefined })}
                columns={myRequestColumns}
                loading={requestsLoading}
                scroll={{ x: 'max-content' }}
                pagination={{ pageSize: 10, defaultCurrent: Math.max(1, Math.floor(myRequests.findIndex((row) => row.id === requestedRequestId) / 10) + 1), hideOnSinglePage: true, showSizeChanger: false }}
              />
            ),
          },
          {
            key: 'pending-requests',
            label: t('library.pendingRequestsTab'),
            children: (
              <Table
                rowKey="id"
                dataSource={pendingRequests}
                key={`${requestedRequestId ?? 'pending-requests'}:${pendingRequests.findIndex((row) => row.id === requestedRequestId)}`}
                onRow={(record) => ({ style: record.id === requestedRequestId ? { background: token.colorInfoBg } : undefined })}
                columns={pendingRequestColumns}
                loading={requestsLoading}
                scroll={{ x: 'max-content' }}
                pagination={{ pageSize: 10, defaultCurrent: Math.max(1, Math.floor(pendingRequests.findIndex((row) => row.id === requestedRequestId) / 10) + 1), hideOnSinglePage: true, showSizeChanger: false }}
              />
            ),
          },
        ]}
      />

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
          <Form.Item
            name="project_id"
            label={t('library.targetProject')}
            rules={requestProjectRequired ? [{ required: true, message: t('library.targetProjectRequired') }] : undefined}
          >
            <Select
              allowClear={!requestProjectRequired}
              placeholder={t('library.selectProject')}
              options={projects.map((project) => ({ value: project.id, label: project.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('library.dataPackageModalTitle')}
        open={dataPackageOpen}
        onCancel={() => setDataPackageOpen(false)}
        onOk={() => void submitDataPackage()}
        confirmLoading={dataPackageUploading}
        destroyOnHidden
      >
        <Form form={dataPackageForm} layout="vertical" preserve={false}>
          <Form.Item
            name="file"
            label={t('library.dataPackageFile')}
            valuePropName="fileList"
            getValueFromEvent={(event) => (Array.isArray(event) ? event : event?.fileList)}
            rules={[{ required: true, message: t('library.dataPackageFileRequired') }]}
          >
            <Upload.Dragger beforeUpload={() => false} maxCount={1} accept=".zip">
              <p className="ant-upload-drag-icon">
                <DatabaseOutlined />
              </p>
              <p className="ant-upload-text">{t('library.dataPackageFileHint')}</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item
            name="title"
            label={t('library.dataPackageName')}
            rules={[{ required: true, message: t('library.dataPackageNameRequired') }]}
          >
            <Input placeholder={t('library.dataPackageNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('library.dataPackageDescription')}>
            <Input.TextArea rows={3} placeholder={t('library.dataPackageDescriptionPlaceholder')} />
          </Form.Item>
          <Form.Item name="tags" label={t('library.dataPackageTags')}>
            <Select mode="tags" open={false} placeholder={t('library.dataPackageTagsPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('library.manualResourceModalTitle')}
        open={manualResourceOpen}
        onCancel={() => setManualResourceOpen(false)}
        onOk={() => void submitManualResource()}
        confirmLoading={manualResourceSaving}
        destroyOnHidden
      >
        <Form form={manualResourceForm} layout="vertical" preserve={false}>
          <Form.Item
            name="title"
            label={t('library.manualResourceName')}
            rules={[{ required: true, whitespace: true, message: t('library.manualResourceNameRequired') }]}
          >
            <Input placeholder={t('library.manualResourceNamePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="asset_type"
            label={t('library.typeFilter')}
            rules={[{ required: true, message: t('library.manualResourceTypeRequired') }]}
          >
            <Select
              options={['dataset', 'code_repository', 'model_weight', 'gpu', 'external_reference'].map((assetType) => ({
                value: assetType,
                label: t(`library.assetType.${assetType}`, assetType),
              }))}
            />
          </Form.Item>
          <Form.Item name="description" label={t('library.dataPackageDescription')}>
            <Input.TextArea rows={3} placeholder={t('library.dataPackageDescriptionPlaceholder')} />
          </Form.Item>
          <Form.Item name="visibility_scope" label={t('library.detail.visibility')}>
            <Select options={[
              { value: 'lab_public', label: t('library.uploadPublic') },
              { value: 'lab_private', label: t('library.uploadPrivate') },
            ]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('library.linkToProject')}
        open={!!linkingSearchAsset}
        onCancel={() => {
          setLinkingSearchAsset(null);
          setLinkingProjectId(null);
        }}
        onOk={linkSearchAssetToProject}
        okButtonProps={{ disabled: !linkingProjectId }}
      >
        <Typography.Paragraph type="secondary">{linkingSearchAsset?.title}</Typography.Paragraph>
        <Select
          style={{ width: '100%' }}
          placeholder={t('library.selectProject')}
          value={linkingProjectId}
          onChange={setLinkingProjectId}
          options={projects.map((project) => ({ value: project.id, label: project.name }))}
        />
      </Modal>

      <ExtractionDrawer
        open={!!extractionTarget}
        sourceId={extractionTarget?.sourceId ?? null}
        name={extractionTarget?.name}
        processingState={extractionTarget?.processingState}
        onClose={() => setExtractionTarget(null)}
      />
    </PageContainer>
  );
}
