import { DeleteOutlined, UploadOutlined } from '@ant-design/icons';
import { Button, Popconfirm, Switch, Table, Tag, Typography, Upload, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import PageContainer from '../../components/library/PageContainer';
import { formatDateTime } from '../../components/library/library-utils';
import apiClient from '../../services/api-client';

interface SkillPack {
  id: string;
  version: number;
  name: string;
  description: string;
  is_enabled: boolean;
  task_id: string;
  updated_at: string | null;
}

export default function SkillPacksAdmin() {
  const { t, i18n } = useTranslation();
  const [packs, setPacks] = useState<SkillPack[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const loadPacks = () => {
    setLoading(true);
    apiClient.get('/admin/skill-packs')
      .then((response) => setPacks(response.data))
      .catch(() => message.error(t('admin.skillPacks.loadFailed')))
      .finally(() => setLoading(false));
  };

  useEffect(loadPacks, []);

  const uploadPack = async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      await apiClient.post('/admin/skill-packs', formData, { timeout: 60000 });
      message.success(t('admin.skillPacks.uploadSuccess'));
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.uploadFailed'));
    } finally {
      setUploading(false);
    }
    return false;
  };

  const toggleEnabled = async (pack: SkillPack, enabled: boolean) => {
    try {
      await apiClient.patch(`/admin/skill-packs/${pack.id}`, { is_enabled: enabled });
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.updateFailed'));
    }
  };

  const deletePack = async (pack: SkillPack) => {
    try {
      await apiClient.delete(`/admin/skill-packs/${pack.id}`);
      message.success(t('admin.skillPacks.deleteSuccess'));
      loadPacks();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('admin.skillPacks.deleteFailed'));
    }
  };

  const columns: ColumnsType<SkillPack> = [
    {
      title: t('admin.skillPacks.name'),
      dataIndex: 'name',
      render: (value: string, record) => (
        <div>
          <Typography.Text strong>{value}</Typography.Text>
          <Typography.Text type="secondary" style={{ display: 'block', fontSize: 12 }}>
            {record.id}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: t('admin.skillPacks.description'),
      dataIndex: 'description',
      ellipsis: true,
    },
    {
      title: t('admin.skillPacks.version'),
      dataIndex: 'version',
      width: 90,
      render: (value: number) => <Tag>{`v${value}`}</Tag>,
    },
    {
      title: t('admin.skillPacks.task'),
      dataIndex: 'task_id',
      width: 220,
      render: (value: string) => <Typography.Text code>{value}</Typography.Text>,
    },
    {
      title: t('admin.skillPacks.enabled'),
      dataIndex: 'is_enabled',
      width: 100,
      render: (value: boolean, record) => (
        <Switch checked={value} onChange={(checked) => toggleEnabled(record, checked)} />
      ),
    },
    {
      title: t('admin.skillPacks.updatedAt'),
      dataIndex: 'updated_at',
      width: 170,
      render: (value: string | null) => (value ? formatDateTime(value, i18n.language) : '-'),
    },
    {
      title: t('common.actions'),
      width: 90,
      render: (_, record) => (
        <Popconfirm
          title={t('admin.skillPacks.deleteConfirm')}
          okButtonProps={{ danger: true }}
          onConfirm={() => deletePack(record)}
        >
          <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label={t('common.delete')} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <PageContainer
      title={t('admin.skillPacks')}
      extra={(
        <Upload beforeUpload={uploadPack} showUploadList={false} accept=".zip">
          <Button type="primary" icon={<UploadOutlined />} loading={uploading}>
            {t('admin.skillPacks.upload')}
          </Button>
        </Upload>
      )}
    >
      <Typography.Paragraph type="secondary">
        {t('admin.skillPacks.zipHint')}
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={packs}
        columns={columns}
        loading={loading}
        size="middle"
        scroll={{ x: 'max-content' }}
        pagination={{ pageSize: 10, hideOnSinglePage: true, showSizeChanger: false }}
        locale={{ emptyText: t('admin.skillPacks.empty') }}
      />
    </PageContainer>
  );
}
