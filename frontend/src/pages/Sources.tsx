import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, EyeOutlined, FilePdfOutlined, FolderOutlined, PlusOutlined, RedoOutlined, ShareAltOutlined, UploadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, List, Modal, Popconfirm, Popover, Radio, Segmented, Select, Space, Spin, Table, Tabs, Tag, Tooltip, Typography, Upload, message, notification, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ProcessingStatusTag } from '../components/library/AssetTags';
import ExtractionDrawer from '../components/library/ExtractionDrawer';
import { formatDateTime } from '../components/library/library-utils';
import PdfPreviewModal from '../components/library/PdfPreviewModal';
import SourceThumbnail from '../components/library/SourceThumbnail';
import { isAcceptedUploadFile, useFileDrop } from '../hooks/use-file-drop';
import apiClient from '../services/api-client';
import type { DuplicateUploadInfo } from '../types/upload';
import { getDuplicateUploadInfo, showDuplicateUploadModal } from '../utils/duplicate-upload';

interface ShareInfo {
  shared_by: string | null;
  shared_by_name: string | null;
  scope: string;
  project_id: string | null;
  permission: string;
  shared_at: string;
}

interface SourceItem {
  id: string;
  type: string;
  name: string;
  content_hash: string | null;
  created_at: string;
  member_count: number | null;
  processing_state: string;
  extraction_status?: string | null;
  progress: number;
  error_message: string | null;
  owner_id: string | null;
  owner_name: string | null;
  share: ShareInfo | null;
  is_shared: boolean;
  can_edit: boolean;
  duplicate_info?: DuplicateUploadInfo | null;
}

interface ProjectItem {
  id: string;
  name: string;
}

const TERMINAL_STATES = new Set(['ready', 'failed']);

interface SourceMember {
  id: string;
  parent_id: string;
  child_id: string;
  added_at: string;
  child: SourceItem | null;
}

interface SourceOption {
  value: string;
  label: string;
}

interface LibraryAssetOption {
  id: string;
  title: string;
  source_id: string | null;
  asset_type: string;
  visibility_scope: string;
}

interface Note {
  id: string;
  content: string;
  created_at: string;
  owner_id?: string | null;
  owner_name?: string | null;
  share?: ShareInfo | null;
  is_shared?: boolean;
  can_edit?: boolean;
}

interface ExtractionTarget {
  sourceId: string;
  name: string;
  processingState: string | null;
}

type SourceTabKey = 'files' | 'groups' | 'notes';
type GroupScopeFilter = 'all' | 'lab' | 'mine';

function GroupMemberPreview({ groupId }: { groupId: string }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [memberNames, setMemberNames] = useState<string[] | null>(null);

  useEffect(() => {
    apiClient.get(`/sources/${groupId}/members`).then((r) => {
      setMemberNames(r.data.map((m: SourceMember) => m.child?.name || m.child_id));
    });
  }, [groupId]);

  if (memberNames === null) return <Spin size="small" />;
  if (memberNames.length === 0) return <span style={{ color: token.colorTextTertiary }}>{t('group.emptyGroup')}</span>;
  return (
    <List
      size="small"
      dataSource={memberNames}
      renderItem={(name) => (
        <List.Item style={{ padding: '4px 0' }}>
          <FilePdfOutlined style={{ marginRight: 6, color: token.colorError }} />
          {name}
        </List.Item>
      )}
      style={{ maxHeight: 300, overflow: 'auto' }}
    />
  );
}

export default function Sources({
  embedded = false,
  allowedTabs,
  defaultTab,
}: {
  embedded?: boolean;
  allowedTabs?: SourceTabKey[];
  defaultTab?: SourceTabKey;
}) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const visibleTabs = allowedTabs || ['files', 'groups', 'notes'];
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<SourceTabKey>(
    defaultTab && visibleTabs.includes(defaultTab) ? defaultTab : visibleTabs[0],
  );

  // Group state
  const [showCreate, setShowCreate] = useState(false);
  const [showRename, setShowRename] = useState(false);
  const [showAddMember, setShowAddMember] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<SourceItem | null>(null);
  const [members, setMembers] = useState<SourceMember[]>([]);
  const [availableSources, setAvailableSources] = useState<SourceOption[]>([]);
  const [groupScopeFilter, setGroupScopeFilter] = useState<GroupScopeFilter>('all');

  // File state
  const [uploading, setUploading] = useState(false);
  const [pdfViewerSource, setPdfViewerSource] = useState<SourceItem | null>(null);
  const [fileSearchText, setFileSearchText] = useState('');

  // Notes state
  const [notes, setNotes] = useState<Note[]>([]);
  const [notesLoading, setNotesLoading] = useState(false);

  const [showFileRename, setShowFileRename] = useState(false);
  const [fileRenameTarget, setFileRenameTarget] = useState<SourceItem | null>(null);
  const [extractionTarget, setExtractionTarget] = useState<ExtractionTarget | null>(null);

  // Sharing state
  const [shareTarget, setShareTarget] = useState<SourceItem | null>(null);
  const [shareScope, setShareScope] = useState<string>('all');
  const [shareProjectId, setShareProjectId] = useState<string | null>(null);
  const [sharePermission, setSharePermission] = useState<string>('read');
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [sharePreviewCount, setSharePreviewCount] = useState<number>(0);
  const [currentUserId, setCurrentUserId] = useState<string>('');

  const [createForm] = Form.useForm();
  const [renameForm] = Form.useForm();
  const [fileRenameForm] = Form.useForm();

  // Load current user ID
  useEffect(() => {
    apiClient.get('/auth/me').then((r) => setCurrentUserId(r.data.id));
  }, []);

  const loadSources = () => {
    apiClient.get('/sources').then((r) => setSources(r.data));
  };

  const retrySource = (sourceId: string) => {
    apiClient.post(`/sources/${sourceId}/retry`).then(() => {
      message.success(t('source.retrySuccess'));
      loadSources();
    });
  };

  const loadNotes = () => {
    setNotesLoading(true);
    apiClient.get('/notes').then((r) => setNotes(r.data)).finally(() => setNotesLoading(false));
  };

  useEffect(() => {
    apiClient.get('/sources')
      .then((r) => setSources(r.data))
      .finally(() => setPageLoading(false));
  }, []);

  // Poll while any file source is still processing. Stops automatically once
  // every file row is in a terminal (ready/failed) state.
  useEffect(() => {
    const hasInFlight = sources.some(
      (s) => s.type === 'file' && !TERMINAL_STATES.has(s.processing_state),
    );
    if (!hasInFlight) return;
    const handle = window.setInterval(() => {
      apiClient.get('/sources').then((r) => setSources(r.data));
    }, 1000);
    return () => window.clearInterval(handle);
  }, [sources]);

  useEffect(() => {
    if (activeTab === 'notes') loadNotes();
  }, [activeTab]);

  useEffect(() => {
    if (!visibleTabs.includes(activeTab)) {
      setActiveTab(visibleTabs[0]);
    }
  }, [activeTab, visibleTabs]);

  const loadMembers = (groupId: string) => {
    apiClient.get(`/sources/${groupId}/members`)
      .then((r) => setMembers(r.data))
      .catch(() => message.error(t('group.loadMembersFailed')));
  };

  const loadAvailableSources = async () => {
    const [sourcesResult, assetsResult] = await Promise.allSettled([
      apiClient.get('/sources'),
      apiClient.get('/library/assets'),
    ]);
    const options = new Map<string, SourceOption>();

    if (sourcesResult.status === 'fulfilled') {
      (sourcesResult.value.data as SourceItem[])
        .filter((source) => source.id !== selectedGroup?.id)
        .forEach((source) => {
          options.set(source.id, {
            value: source.id,
            label: `${source.name} (${source.type})`,
          });
        });
    }

    if (assetsResult.status === 'fulfilled') {
      (assetsResult.value.data as LibraryAssetOption[])
        .filter((asset) => asset.source_id && asset.source_id !== selectedGroup?.id)
        .forEach((asset) => {
          if (!asset.source_id || options.has(asset.source_id)) return;
          options.set(asset.source_id, {
            value: asset.source_id,
            label: `${asset.title} (${t(`library.visibility.${asset.visibility_scope}`)})`,
          });
        });
    }

    setAvailableSources(Array.from(options.values()));
  };

  const handleUpload = async (file: File) => {
    if (!isAcceptedUploadFile(file)) {
      notification.error({
        message: t('source.unsupportedFileType'),
        description: file.name,
        duration: 5,
      });
      return false;
    }
    setUploading(true);
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const isZip = file.name.toLowerCase().endsWith('.zip');
    const optimistic: SourceItem = {
      id: tempId,
      type: 'file',
      name: file.name,
      content_hash: null,
      created_at: new Date().toISOString(),
      member_count: null,
      processing_state: 'pending',
      progress: 0,
      error_message: null,
      owner_id: null,
      owner_name: null,
      share: null,
      is_shared: false,
      can_edit: true,
    };
    setSources((prev) => [optimistic, ...prev]);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await apiClient.post('/sources/upload', formData, { timeout: 300000 });
      if (isZip && res.data.sources) {
        // ZIP response: replace optimistic entry with all extracted sources
        setSources((prev) => {
          const withoutTemp = prev.filter((s) => s.id !== tempId);
          const existingIds = new Set(withoutTemp.map((s) => s.id));
          const newSources = res.data.sources.filter(
            (s: SourceItem) => !existingIds.has(s.id),
          );
          return [...newSources, ...withoutTemp];
        });
        if (res.data.errors?.length) {
          res.data.errors.forEach((err: string) =>
            notification.warning({ message: err, duration: 0 }),
          );
        }
      } else {
        setSources((prev) => {
          const withoutTemp = prev.filter((s) => s.id !== tempId);
          const exists = withoutTemp.some((s) => s.id === res.data.id);
          return exists ? withoutTemp : [res.data, ...withoutTemp];
        });
        if (res.data.duplicate_info) {
          showDuplicateUploadModal({ info: res.data.duplicate_info, t });
        }
      }
      loadSources();
    } catch (err: unknown) {
      setSources((prev) => prev.filter((s) => s.id !== tempId));
      const duplicateInfo = getDuplicateUploadInfo(err);
      if (duplicateInfo) {
        showDuplicateUploadModal({ info: duplicateInfo, t });
        return false;
      }
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      notification.error({
        message: t('source.uploadFailed'),
        description: typeof detail === 'string' ? detail : undefined,
        duration: 0,
      });
    } finally {
      setUploading(false);
    }
    return false;
  };

  const createGroup = async (values: { name: string }) => {
    await apiClient.post('/sources/groups', values);
    setShowCreate(false);
    createForm.resetFields();
    loadSources();
  };

  const renameGroup = async (values: { name: string }) => {
    if (!selectedGroup) return;
    await apiClient.patch(`/sources/${selectedGroup.id}`, values);
    setShowRename(false);
    renameForm.resetFields();
    setSelectedGroup({ ...selectedGroup, name: values.name });
    loadSources();
  };

  const deleteSource = async (id: string) => {
    await apiClient.delete(`/sources/${id}`);
    if (selectedGroup?.id === id) {
      setSelectedGroup(null);
      setMembers([]);
    }
    loadSources();
  };

  const openFileRename = (record: SourceItem) => {
    setFileRenameTarget(record);
    fileRenameForm.setFieldsValue({ name: record.name });
    setShowFileRename(true);
  };

  const renameFile = async (values: { name: string }) => {
    if (!fileRenameTarget) return;
    await apiClient.patch(`/sources/${fileRenameTarget.id}`, values);
    setShowFileRename(false);
    fileRenameForm.resetFields();
    setFileRenameTarget(null);
    loadSources();
  };

  const openGroupDetail = (group: SourceItem) => {
    setSelectedGroup(group);
    loadMembers(group.id);
  };

  const addMember = async (childId: string) => {
    if (!selectedGroup) return;
    try {
      await apiClient.post(`/sources/${selectedGroup.id}/members`, { child_id: childId });
      message.success(t('group.addMemberSuccess'));
      setShowAddMember(false);
      loadMembers(selectedGroup.id);
      loadSources();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('group.addMemberFailed'));
    }
  };

  const removeMember = async (childId: string) => {
    if (!selectedGroup) return;
    await apiClient.delete(`/sources/${selectedGroup.id}/members/${childId}`);
    loadMembers(selectedGroup.id);
    loadSources();
  };

  const deleteNote = async (id: string) => {
    await apiClient.delete(`/notes/${id}`);
    loadNotes();
  };

  const openExtractionDrawer = (source: SourceItem) => {
    setExtractionTarget({
      sourceId: source.id,
      name: source.name,
      processingState: source.processing_state,
    });
  };

  const openShareDialog = async (source: SourceItem) => {
    setShareTarget(source);
    if (source.share) {
      setShareScope(source.share.scope);
      setShareProjectId(source.share.project_id);
      setSharePermission(source.share.permission);
    } else {
      setShareScope('all');
      setShareProjectId(null);
      setSharePermission(source.type === 'file' ? 'read' : 'read');
    }
    // Load projects for scope selector
    try {
      const r = await apiClient.get('/projects');
      setProjects(r.data);
    } catch { setProjects([]); }
    // Preview for groups
    if (source.type === 'group' && !source.share) {
      try {
        const r = await apiClient.get(`/sources/${source.id}/share-preview`);
        setSharePreviewCount(r.data.unshared_file_count);
      } catch { setSharePreviewCount(0); }
    } else {
      setSharePreviewCount(0);
    }
  };

  const handleShare = async () => {
    if (!shareTarget) return;
    try {
      if (shareTarget.share) {
        // Update existing share
        await apiClient.patch(`/sources/${shareTarget.id}/share`, {
          scope: shareScope,
          project_id: shareScope === 'project' ? shareProjectId : null,
          permission: sharePermission,
        });
        message.success(t('share.updated'));
      } else {
        // Create new share
        const res = await apiClient.post(`/sources/${shareTarget.id}/share`, {
          scope: shareScope,
          project_id: shareScope === 'project' ? shareProjectId : null,
          permission: sharePermission,
        });
        if (res.data.auto_shared_files > 0) {
          message.success(t('share.sharedWithFiles', { count: res.data.auto_shared_files }));
        } else {
          message.success(t('share.shared'));
        }
      }
      setShareTarget(null);
      loadSources();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('share.error'));
    }
  };

  const handleUnshare = async () => {
    if (!shareTarget) return;
    try {
      await apiClient.delete(`/sources/${shareTarget.id}/share`);
      message.success(t('share.unshared'));
      setShareTarget(null);
      loadSources();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('share.error'));
    }
  };

  const isOwner = (source: SourceItem) => source.owner_id === currentUserId || source.owner_id === null;
  const isLabCollection = (source: SourceItem) => source.type === 'group' && source.share?.scope === 'all';

  const refreshSource = async (sourceId: string) => {
    const r = await apiClient.get(`/sources/${sourceId}`);
    const updated = r.data as SourceItem;
    setSources((prev) => prev.map((source) => (source.id === sourceId ? updated : source)));
    setSelectedGroup((prev) => (prev?.id === sourceId ? updated : prev));
  };

  const publishGroupToLab = async (group: SourceItem) => {
    try {
      const payload = { scope: 'all', project_id: null, permission: 'readwrite' };
      if (group.share) {
        await apiClient.patch(`/sources/${group.id}/share`, payload);
      } else {
        try {
          await apiClient.post(`/sources/${group.id}/share`, payload);
        } catch (err: unknown) {
          // The list may be stale (published elsewhere); treat as an update.
          const detail = (err as { response?: { data?: { detail?: string } } })
            ?.response?.data?.detail;
          if (!detail || !detail.includes('already shared')) {
            throw err;
          }
          await apiClient.patch(`/sources/${group.id}/share`, payload);
        }
      }
      message.success(t('group.publishSuccess'));
      await refreshSource(group.id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('group.publishFailed'));
    }
  };

  const withdrawGroupFromLab = async (group: SourceItem) => {
    try {
      await apiClient.delete(`/sources/${group.id}/share`);
      message.success(t('group.withdrawSuccess'));
      await refreshSource(group.id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('group.withdrawFailed'));
    }
  };

  const displayName = (source: SourceItem) => {
    if (source.is_shared && !isOwner(source) && source.owner_name) {
      return `${source.name} (${source.owner_name})`;
    }
    return source.name;
  };

  const shareIcon = (source: SourceItem) => {
    if (!source.is_shared) return null;
    const sharerName = source.share?.shared_by_name || source.owner_name || '';
    return (
      <Tooltip title={`${t('share.sharedBy')} ${sharerName}`}>
        <ShareAltOutlined style={{ marginLeft: 6, color: token.colorSuccess, fontSize: 14 }} />
      </Tooltip>
    );
  };

  const collectionVisibilityTag = (source: SourceItem) => {
    if (isLabCollection(source)) {
      return <Tag color="blue">{t('group.labCollection')}</Tag>;
    }
    if (source.share?.scope === 'project') {
      return <Tag color="purple">{t('group.projectCollection')}</Tag>;
    }
    return <Tag>{t('group.myCollection')}</Tag>;
  };

  const { isDragOver, dropHandlers } = useFileDrop(
    (files) => { files.forEach((f) => handleUpload(f)); },
    (rejected) => {
      notification.error({
        message: t('source.unsupportedFileType'),
        description: rejected.map((f) => f.name).join(', '),
        duration: 5,
      });
    },
  );

  // Group detail view
  if (selectedGroup) {
    const memberColumns: ColumnsType<SourceMember> = [
      {
        title: t('source.name'),
        render: (_, record) => {
          const child = record.child;
          if (!child) return record.child_id;
          if (child.type === 'file') {
            return (
              <Popover
                content={
                  <SourceThumbnail sourceId={child.id} alt={t('source.preview')} />
                }
                title={child.name}
                trigger="hover"
                placement="right"
                mouseEnterDelay={0.3}
              >
                <a
                  role="link"
                  tabIndex={0}
                  onClick={() => setPdfViewerSource(child)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      setPdfViewerSource(child);
                    }
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <FilePdfOutlined style={{ marginRight: 6, color: token.colorError }} />
                  {child.name}
                </a>
              </Popover>
            );
          }
          return (
            <>
              <FolderOutlined style={{ marginRight: 6, color: token.colorPrimary }} />
              {child.name}
            </>
          );
        },
      },
      {
        title: t('source.status'),
        width: 180,
        render: (_, record) => {
          const child = record.child;
          if (!child || child.type !== 'file') return null;
          return (
            <ProcessingStatusTag
              state={child.processing_state}
              progress={child.progress}
              errorMessage={child.error_message}
            />
          );
        },
      },
      {
        title: t('source.type'),
        render: (_, record) => (
          <Tag color={record.child?.type === 'group' ? 'blue' : undefined}>
            {record.child?.type || '-'}
          </Tag>
        ),
      },
      {
        title: t('common.actions'),
        render: (_, record) => {
          if (!selectedGroup.can_edit && !isOwner(selectedGroup)) return null;
          return (
            <Popconfirm title={t('group.removeConfirm')} onConfirm={() => removeMember(record.child_id)}>
              <Button icon={<DeleteOutlined />} danger size="small">{t('group.removeMember')}</Button>
            </Popconfirm>
          );
        },
      },
    ];

    return (
      <div style={{ padding: embedded ? 0 : 24 }}>
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <Space size={8} wrap>
              <Button
                icon={<ArrowLeftOutlined />}
                onClick={() => { setSelectedGroup(null); setMembers([]); }}
              >
                {t('common.back')}
              </Button>
              <Typography.Title level={5} style={{ margin: 0 }}>
                {displayName(selectedGroup)}
                {shareIcon(selectedGroup)}
              </Typography.Title>
              {collectionVisibilityTag(selectedGroup)}
            </Space>
            <Space wrap>
              {isOwner(selectedGroup) && (
                isLabCollection(selectedGroup) ? (
                  <Popconfirm title={t('group.withdrawConfirm')} onConfirm={() => withdrawGroupFromLab(selectedGroup)}>
                    <Button>{t('group.withdrawFromLab')}</Button>
                  </Popconfirm>
                ) : (
                  <Popconfirm title={t('group.publishConfirm')} onConfirm={() => publishGroupToLab(selectedGroup)}>
                    <Button type="primary" icon={<ShareAltOutlined />}>{t('group.publishToLab')}</Button>
                  </Popconfirm>
                )
              )}
              {isOwner(selectedGroup) && (
                <Button icon={<EditOutlined />} onClick={() => { renameForm.setFieldsValue({ name: selectedGroup.name }); setShowRename(true); }}>
                  {t('group.rename')}
                </Button>
              )}
              {(selectedGroup.can_edit || isOwner(selectedGroup)) && (
                <Button icon={<PlusOutlined />} onClick={() => { loadAvailableSources(); setShowAddMember(true); }}>
                  {t('group.addMember')}
                </Button>
              )}
            </Space>
          </div>
          <Table
            dataSource={members}
            rowKey="id"
            columns={memberColumns}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: t('group.emptyMembers') }}
          />
        </Space>

        <Modal title={t('group.renameTitle')} open={showRename} onCancel={() => setShowRename(false)} onOk={() => renameForm.submit()}>
          <Form form={renameForm} onFinish={renameGroup} layout="vertical">
            <Form.Item name="name" label={t('group.name')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Form>
        </Modal>

        <Modal title={t('group.addMember')} open={showAddMember} onCancel={() => setShowAddMember(false)} footer={null}>
          <Select
            showSearch
            style={{ width: '100%' }}
            placeholder={t('group.selectSource')}
            optionFilterProp="label"
            onSelect={(value: string) => addMember(value)}
            options={availableSources}
          />
        </Modal>

        <PdfPreviewModal
          open={!!pdfViewerSource}
          sourceId={pdfViewerSource?.id ?? null}
          title={pdfViewerSource?.name}
          onClose={() => setPdfViewerSource(null)}
        />
      </div>
    );
  }

  const files = sources.filter((s) => s.type === 'file');
  const groups = sources.filter((s) => s.type === 'group');
  const normalizedFileSearch = fileSearchText.trim().toLowerCase();
  const filteredFiles = normalizedFileSearch
    ? files.filter((file) => file.name.toLowerCase().includes(normalizedFileSearch))
    : files;
  const filteredGroups = groups.filter((group) => {
    if (groupScopeFilter === 'lab') return isLabCollection(group);
    if (groupScopeFilter === 'mine') return isOwner(group) && !isLabCollection(group);
    return true;
  });

  const fileColumns: ColumnsType<SourceItem> = [
    {
      title: t('source.name'),
      dataIndex: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (_: string, record) => {
        const name = displayName(record);
        return (
          <Popover
            content={
              <SourceThumbnail sourceId={record.id} alt={t('source.preview')} />
            }
            title={name}
            trigger="hover"
            placement="right"
            mouseEnterDelay={0.3}
          >
            <a
              role="link"
              tabIndex={0}
              onClick={() => setPdfViewerSource(record)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  setPdfViewerSource(record);
                }
              }}
              style={{ cursor: 'pointer' }}
            >
              <FilePdfOutlined style={{ marginRight: 6, color: token.colorError }} />
              {name}
              {shareIcon(record)}
            </a>
          </Popover>
        );
      },
    },
    {
      title: t('source.status'),
      dataIndex: 'processing_state',
      width: 180,
      render: (_, record) => (
        <Space size={4}>
          <ProcessingStatusTag
            state={record.processing_state}
            progress={record.progress}
            errorMessage={record.error_message}
          />
          {record.processing_state === 'failed' ? (
            <Tooltip title={t('source.retry')}>
              <Button
                size="small"
                type="text"
                icon={<RedoOutlined />}
                aria-label={t('source.retry')}
                onClick={() => retrySource(record.id)}
              />
            </Tooltip>
          ) : null}
        </Space>
      ),
    },
    {
      title: t('source.createdAt'),
      dataIndex: 'created_at',
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (val: string) => formatDateTime(val, i18n.language),
    },
    {
      title: t('common.actions'),
      render: (_, record) => (
        <Space size={4} wrap>
          <Tooltip title={t('source.extraction')}>
            <Button icon={<EyeOutlined />} size="small" type="text" aria-label={t('source.extraction')} onClick={() => openExtractionDrawer(record)} />
          </Tooltip>
          {isOwner(record) && (
            <>
              <Tooltip title={t('source.renameTitle')}>
                <Button icon={<EditOutlined />} size="small" type="text" aria-label={t('source.renameTitle')} onClick={() => openFileRename(record)} />
              </Tooltip>
              <Tooltip title={record.is_shared ? t('share.manage') : t('share.share')}>
                <Button icon={<ShareAltOutlined />} size="small" type="text" aria-label={record.is_shared ? t('share.manage') : t('share.share')} onClick={() => openShareDialog(record)} />
              </Tooltip>
            </>
          )}
          <Popconfirm
            title={record.is_shared ? t('share.hideConfirm') : t('source.deleteConfirm')}
            onConfirm={() => deleteSource(record.id)}
          >
            <Button icon={<DeleteOutlined />} danger size="small" type="text" aria-label={t('common.delete')} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const groupColumns: ColumnsType<SourceItem> = [
    {
      title: t('source.name'),
      dataIndex: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
      render: (_: string, record) => {
        const name = displayName(record);
        return (
          <Popover
            content={<GroupMemberPreview groupId={record.id} />}
            title={name}
            trigger="hover"
            placement="right"
            mouseEnterDelay={0.3}
          >
            <a
              role="link"
              tabIndex={0}
              onClick={() => openGroupDetail(record)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  openGroupDetail(record);
                }
              }}
            >
              <FolderOutlined style={{ marginRight: 6, color: token.colorPrimary }} />
              {name}
              {shareIcon(record)}
            </a>
          </Popover>
        );
      },
    },
    {
      title: t('group.visibility'),
      width: 160,
      render: (_, record) => collectionVisibilityTag(record),
    },
    {
      title: t('group.memberCount'),
      dataIndex: 'member_count',
      width: 120,
      render: (_, record) => record.member_count ?? 0,
    },
    {
      title: t('source.createdAt'),
      dataIndex: 'created_at',
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      render: (val: string) => formatDateTime(val, i18n.language),
    },
    {
      title: t('common.actions'),
      render: (_, record) => (
        <Space size={4} wrap>
          <Tooltip title={t('group.manageMembers')}>
            <Button icon={<EditOutlined />} size="small" type="text" aria-label={t('group.manageMembers')} onClick={() => openGroupDetail(record)} />
          </Tooltip>
          {isOwner(record) && (
            <>
              {isLabCollection(record) ? (
                <Popconfirm title={t('group.withdrawConfirm')} onConfirm={() => withdrawGroupFromLab(record)}>
                  <Button size="small" type="text">{t('group.withdrawFromLab')}</Button>
                </Popconfirm>
              ) : (
                <Popconfirm title={t('group.publishConfirm')} onConfirm={() => publishGroupToLab(record)}>
                  <Button size="small" type="text">{t('group.publishToLab')}</Button>
                </Popconfirm>
              )}
              <Popconfirm title={t('source.deleteConfirm')} onConfirm={() => deleteSource(record.id)}>
                <Button icon={<DeleteOutlined />} danger size="small" type="text" aria-label={t('common.delete')} />
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ];

  const tabBarExtra = activeTab === 'files' ? (
    <Upload beforeUpload={handleUpload} showUploadList={false} multiple accept=".pdf,.zip">
      <Button icon={<UploadOutlined />} loading={uploading}>{t('source.upload')}</Button>
    </Upload>
  ) : activeTab === 'groups' ? (
    <Button icon={<PlusOutlined />} onClick={() => setShowCreate(true)}>{t('group.create')}</Button>
  ) : null;

  const tabItems = [
    {
      key: 'files',
      label: t('source.tabFiles'),
      children: (
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Input.Search
              allowClear
              placeholder={t('source.searchFilesPlaceholder')}
              style={{ width: 260 }}
              onSearch={setFileSearchText}
              onChange={(e) => setFileSearchText(e.target.value)}
            />
          </div>
          <div
            {...dropHandlers}
            style={{
              position: 'relative',
              border: isDragOver ? `2px dashed ${token.colorPrimary}` : '2px dashed transparent',
              borderRadius: token.borderRadius,
              background: isDragOver ? token.colorPrimaryBg : 'transparent',
              transition: 'background 0.15s, border-color 0.15s',
            }}
          >
            <Table dataSource={filteredFiles} rowKey="id" columns={fileColumns} loading={pageLoading} scroll={{ x: 'max-content' }} />
          </div>
        </Space>
      ),
    },
    {
      key: 'groups',
      label: t('source.tabGroups'),
      children: (
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Segmented
              value={groupScopeFilter}
              onChange={(value) => setGroupScopeFilter(value as GroupScopeFilter)}
              options={[
                { value: 'all', label: t('group.filterAll') },
                { value: 'lab', label: t('group.filterLab') },
                { value: 'mine', label: t('group.filterMine') },
              ]}
            />
          </div>
          <Table dataSource={filteredGroups} rowKey="id" columns={groupColumns} loading={pageLoading} scroll={{ x: 'max-content' }} />
        </Space>
      ),
    },
    {
      key: 'notes',
      label: t('nav.notes'),
      children: (
        <List
          loading={notesLoading}
          dataSource={notes}
          renderItem={(note) => (
            <List.Item
              actions={[
                <Popconfirm key="delete" title={t('common.confirm')} onConfirm={() => deleteNote(note.id)}>
                  <Button icon={<DeleteOutlined />} danger size="small" type="text" aria-label={t('common.delete')} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={formatDateTime(note.created_at, i18n.language)}
                description={note.content.slice(0, 200)}
              />
            </List.Item>
          )}
        />
      ),
    },
  ].filter((item) => visibleTabs.includes(item.key as SourceTabKey));

  const sourceTabs = (
    <Tabs
      activeKey={activeTab}
      onChange={(key) => setActiveTab(key as SourceTabKey)}
      tabBarExtraContent={tabBarExtra}
      items={tabItems}
    />
  );

  return (
    <div style={{ padding: embedded ? 0 : 24 }}>
      {embedded ? sourceTabs : (
        <Card title={t('source.manageTitle')}>
          {sourceTabs}
        </Card>
      )}

      <Modal
        title={t('source.renameTitle')}
        open={showFileRename}
        onCancel={() => { setShowFileRename(false); fileRenameForm.resetFields(); }}
        onOk={() => fileRenameForm.submit()}
        destroyOnHidden
      >
        <Form form={fileRenameForm} onFinish={renameFile} layout="vertical">
          <Form.Item name="name" label={t('source.renameLabel')} rules={[{ required: true }]}>
            <Input placeholder={t('source.renamePlaceholder')} autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('group.create')} open={showCreate} onCancel={() => setShowCreate(false)} onOk={() => createForm.submit()}>
        <Form form={createForm} onFinish={createGroup} layout="vertical">
          <Form.Item name="name" label={t('group.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <PdfPreviewModal
        open={!!pdfViewerSource}
        sourceId={pdfViewerSource?.id ?? null}
        title={pdfViewerSource?.name}
        onClose={() => setPdfViewerSource(null)}
      />

      <ExtractionDrawer
        open={!!extractionTarget}
        sourceId={extractionTarget?.sourceId ?? null}
        name={extractionTarget?.name}
        processingState={extractionTarget?.processingState}
        onClose={() => setExtractionTarget(null)}
      />

      {/* Share Dialog */}
      <Modal
        title={shareTarget?.share ? t('share.manageTitle') : t('share.shareTitle')}
        open={!!shareTarget}
        onCancel={() => setShareTarget(null)}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div>
              {shareTarget?.share && shareTarget.type !== 'file' && (
                <Popconfirm title={t('share.unshareConfirm')} onConfirm={handleUnshare}>
                  <Button danger>{t('share.unshare')}</Button>
                </Popconfirm>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button onClick={() => setShareTarget(null)}>{t('common.cancel')}</Button>
              <Popconfirm
                title={
                  shareTarget?.type === 'file' && !shareTarget?.share
                    ? t('share.fileIrreversible')
                    : shareTarget?.type === 'group' && !shareTarget?.share && sharePreviewCount > 0
                      ? t('share.groupWarning', { count: sharePreviewCount })
                      : t('share.confirmShare')
                }
                onConfirm={handleShare}
              >
                <Button type="primary">
                  {shareTarget?.share ? t('share.update') : t('share.share')}
                </Button>
              </Popconfirm>
            </div>
          </div>
        }
        destroyOnHidden
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('share.scope')}</div>
            <Radio.Group value={shareScope} onChange={(e) => setShareScope(e.target.value)}>
              <Radio value="all">{t('share.allUsers')}</Radio>
              <Radio value="project">{t('share.projectMembers')}</Radio>
            </Radio.Group>
          </div>

          {shareScope === 'project' && (
            <div>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('share.selectProject')}</div>
              <Select
                style={{ width: '100%' }}
                value={shareProjectId || undefined}
                onChange={setShareProjectId}
                placeholder={t('share.selectProject')}
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
              />
            </div>
          )}

          {shareTarget?.type !== 'file' && (
            <div>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>{t('share.permission')}</div>
              <Radio.Group value={sharePermission} onChange={(e) => setSharePermission(e.target.value)}>
                <Radio value="read">{t('share.readOnly')}</Radio>
                <Radio value="readwrite">{t('share.readWrite')}</Radio>
              </Radio.Group>
            </div>
          )}

          {shareTarget?.type === 'file' && !shareTarget?.share && (
            <Alert type="warning" showIcon message={t('share.fileWarning')} />
          )}

          {shareTarget?.type === 'group' && !shareTarget?.share && sharePreviewCount > 0 && (
            <Alert type="warning" showIcon message={t('share.groupFileWarning', { count: sharePreviewCount })} />
          )}
        </div>
      </Modal>
    </div>
  );
}
