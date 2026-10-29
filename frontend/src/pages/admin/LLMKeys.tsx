import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  AutoComplete,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';

interface LLMProfile {
  id: string;
  provider: string;
  name: string;
  api_base?: string | null;
  model: string;
  status: string;
  last_tested_at?: string | null;
  last_test_result?: string | null;
  masked_key: string;
}

interface RuntimeConfig {
  active_llm_profile_id?: string | null;
}

interface ProfileFormValues {
  provider: string;
  name: string;
  api_base?: string;
  key?: string;
  model: string;
}

const PROVIDER_OPTIONS = [
  { value: 'litellm', label: 'LiteLLM' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'ollama', label: 'Ollama' },
];

export default function LLMKeysAdmin() {
  const { t } = useTranslation();
  const [profiles, setProfiles] = useState<LLMProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editingProfile, setEditingProfile] = useState<LLMProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [form] = Form.useForm<ProfileFormValues>();

  const loadData = async () => {
    const [profileResponse, configResponse] = await Promise.all([
      apiClient.get('/admin/llm-profiles'),
      apiClient.get<RuntimeConfig>('/admin/config'),
    ]);
    setProfiles(profileResponse.data);
    setActiveProfileId(configResponse.data.active_llm_profile_id ?? null);
  };

  useEffect(() => {
    loadData().catch(() => {
      message.error(t('admin.llmProfileLoadFailed'));
    });
  }, [t]);

  const closeModal = () => {
    setShowCreate(false);
    setEditingProfile(null);
    setModelOptions([]);
    form.resetFields();
  };

  const openCreate = () => {
    setEditingProfile(null);
    setShowCreate(true);
    setModelOptions([]);
    form.resetFields();
  };

  const openEdit = (profile: LLMProfile) => {
    setEditingProfile(profile);
    setShowCreate(true);
    setModelOptions(profile.model ? [profile.model] : []);
    form.setFieldsValue({
      provider: profile.provider,
      name: profile.name,
      api_base: profile.api_base ?? undefined,
      key: undefined,
      model: profile.model,
    });
  };

  const submitProfile = async (values: ProfileFormValues) => {
    setSaving(true);
    try {
      if (editingProfile) {
        await apiClient.put(`/admin/llm-profiles/${editingProfile.id}`, values);
      } else {
        await apiClient.post('/admin/llm-profiles', values);
      }
      message.success(t('admin.llmProfileSaved'));
      closeModal();
      await loadData();
    } catch (error: unknown) {
      const apiMessage =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      message.error(apiMessage || t('admin.llmProfileSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const canProbeWithCurrentForm = (values: Partial<ProfileFormValues>) => {
    if (values.key || editingProfile) {
      return true;
    }
    message.warning(t('admin.llmProfileProbeNeedsKey'));
    return false;
  };

  const buildProbePayload = (values: Partial<ProfileFormValues>) => ({
    profile_id: editingProfile?.id,
    provider: values.provider,
    api_base: values.api_base,
    key: values.key,
  });

  const loadModels = async () => {
    const values = await form.validateFields(['provider', 'api_base']);
    const keyValue = form.getFieldValue('key') as string | undefined;
    const probeValues = { ...values, key: keyValue };
    if (!canProbeWithCurrentForm(probeValues)) {
      return;
    }
    setLoadingModels(true);
    try {
      const response = await apiClient.post(
        '/admin/llm-profiles/fetch-models',
        buildProbePayload(probeValues),
      );
      const nextModels: string[] = response.data?.models ?? [];
      setModelOptions(nextModels);
      message.success(t('admin.llmProfileModelsLoaded', { count: nextModels.length }));
    } catch (error: unknown) {
      const apiMessage =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message === 'string'
          ? (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message
          : null;
      message.error(apiMessage || t('admin.llmProfileLoadModelsFailed'));
    } finally {
      setLoadingModels(false);
    }
  };

  const testConnection = async () => {
    const values = await form.validateFields(['provider', 'api_base']);
    const keyValue = form.getFieldValue('key') as string | undefined;
    const probeValues = { ...values, key: keyValue };
    if (!canProbeWithCurrentForm(probeValues)) {
      return;
    }
    setTestingConnection(true);
    try {
      const response = await apiClient.post(
        '/admin/llm-profiles/test-connection',
        buildProbePayload(probeValues),
      );
      if (response.data?.ok) {
        message.success(response.data.message || t('admin.llmProfileConnectionTestSuccess'));
      } else {
        message.error(response.data?.message || t('admin.llmProfileConnectionTestFailed'));
      }
    } catch (error: unknown) {
      const apiMessage =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message === 'string'
          ? (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message
          : null;
      message.error(apiMessage || t('admin.llmProfileConnectionTestFailed'));
    } finally {
      setTestingConnection(false);
    }
  };

  const testModel = async () => {
    const values = await form.validateFields(['provider', 'api_base', 'model']);
    const keyValue = form.getFieldValue('key') as string | undefined;
    const probeValues = { ...values, key: keyValue };
    if (!canProbeWithCurrentForm(probeValues)) {
      return;
    }
    setTestingModel(true);
    try {
      const response = await apiClient.post('/admin/llm-profiles/test-model', {
        ...buildProbePayload(probeValues),
        model: values.model,
      });
      if (response.data?.ok) {
        message.success(response.data.message || t('admin.llmProfileModelTestSuccess'));
      } else {
        message.error(response.data?.message || t('admin.llmProfileModelTestFailed'));
      }
    } catch (error: unknown) {
      const apiMessage =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message === 'string'
          ? (error as { response?: { data?: { message?: string; detail?: string } } }).response?.data?.message
          : null;
      message.error(apiMessage || t('admin.llmProfileModelTestFailed'));
    } finally {
      setTestingModel(false);
    }
  };

  const activateProfile = async (profile: LLMProfile) => {
    try {
      await apiClient.post(`/admin/llm-profiles/${profile.id}/activate`);
      setActiveProfileId(profile.id);
      message.success(t('admin.llmProfileActivated'));
    } catch {
      message.error(t('admin.llmProfileActivateFailed'));
    }
  };

  const deleteProfile = async (id: string) => {
    try {
      await apiClient.delete(`/admin/llm-profiles/${id}`);
      if (activeProfileId === id) {
        setActiveProfileId(null);
      }
      message.success(t('admin.llmProfileDeleted'));
      await loadData();
    } catch {
      message.error(t('admin.llmProfileDeleteFailed'));
    }
  };

  const renderStatusTag = (status: string) => {
    const statusKey = `admin.llmProfileStatus.${status}`;
    const label = t(statusKey) === statusKey ? status : t(statusKey);

    if (status === 'model_ready' || status === 'connection_ok') {
      return <Tag color="green">{label}</Tag>;
    }
    if (status === 'model_unhealthy' || status === 'connection_failed') {
      return <Tag color="red">{label}</Tag>;
    }
    return <Tag>{label}</Tag>;
  };

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={t('admin.llm-profiles')}
        extra={
          <Button icon={<PlusOutlined />} onClick={openCreate}>
            {t('common.create')}
          </Button>
        }
      >
        <Table
          dataSource={profiles}
          rowKey="id"
          scroll={{ x: 'max-content' }}
          columns={[
            {
              title: t('admin.llmProfileName'),
              dataIndex: 'name',
              render: (value: string, record: LLMProfile) => (
                <Space size={8}>
                  <span>{value}</span>
                  {activeProfileId === record.id && <Tag color="green">{t('admin.llmProfileActive')}</Tag>}
                </Space>
              ),
            },
            { title: t('admin.llmKeyProvider'), dataIndex: 'provider' },
            { title: t('admin.llmModel'), dataIndex: 'model' },
            { title: t('admin.llmApiBase'), dataIndex: 'api_base' },
            { title: t('admin.llmProfileStatusLabel'), dataIndex: 'status', render: renderStatusTag },
            { title: t('admin.llmApiKey'), dataIndex: 'masked_key' },
            {
              title: t('common.actions'),
              render: (_, record: LLMProfile) => (
                <Space size={8} wrap>
                  <Button
                    size="small"
                    type={activeProfileId === record.id ? 'default' : 'primary'}
                    icon={<CheckCircleOutlined />}
                    disabled={activeProfileId === record.id}
                    onClick={() => activateProfile(record)}
                  >
                    {activeProfileId === record.id ? t('admin.llmProfileActive') : t('admin.llmProfileActivate')}
                  </Button>
                  <Button icon={<EditOutlined />} size="small" aria-label={t('common.edit')} onClick={() => openEdit(record)} />
                  <Popconfirm title={t('common.confirm')} onConfirm={() => deleteProfile(record.id)}>
                    <Button icon={<DeleteOutlined />} danger size="small" aria-label={t('common.delete')} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editingProfile ? t('admin.llmProfileEditTitle') : t('admin.llmProfileCreateTitle')}
        open={showCreate}
        onCancel={closeModal}
        onOk={() => form.submit()}
        okButtonProps={{ loading: saving }}
        width={720}
        footer={(_, { OkBtn, CancelBtn }) => (
          <>
            <Button icon={<ReloadOutlined />} onClick={loadModels} loading={loadingModels}>
              {t('admin.llmProfileLoadModels')}
            </Button>
            <Button onClick={testConnection} loading={testingConnection}>
              {t('admin.llmProfileTestConnection')}
            </Button>
            <Button onClick={testModel} loading={testingModel}>
              {t('admin.llmProfileTestModel')}
            </Button>
            <CancelBtn />
            <OkBtn />
          </>
        )}
      >
        <Form form={form} onFinish={submitProfile} layout="vertical">
          <Form.Item name="provider" label={t('admin.llmKeyProvider')} rules={[{ required: true }]}>
            <Select options={PROVIDER_OPTIONS} />
          </Form.Item>
          <Form.Item name="name" label={t('admin.llmProfileName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="api_base" label={t('admin.llmApiBase')}>
            <Input placeholder="http://localhost:4000" />
          </Form.Item>
          <Form.Item
            name="key"
            label={t('admin.llmApiKey')}
            rules={editingProfile ? [] : [{ required: true }]}
            extra={
              <Space orientation="vertical" size={4}>
                <Typography.Text type="secondary">{t('admin.llmProfileApiKeyHint')}</Typography.Text>
                <Typography.Text type="secondary">{t('admin.llmKeyLiteLLMHint')}</Typography.Text>
              </Space>
            }
          >
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="model"
            label={t('admin.llmModel')}
            rules={[{ required: true }]}
            extra={<Typography.Text type="secondary">{t('admin.llmProfileModelHint')}</Typography.Text>}
          >
            <AutoComplete
              options={modelOptions.map((model) => ({ value: model }))}
              filterOption={(inputValue, option) =>
                (option?.value ?? '').toLowerCase().includes(inputValue.toLowerCase())
              }
            >
              <Input placeholder="openai/gpt-4o-mini" />
            </AutoComplete>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
