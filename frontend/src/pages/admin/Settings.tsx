import { SaveOutlined } from '@ant-design/icons';
import { Button, Card, Collapse, Form, Input, InputNumber, Select, Spin, Switch, message } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';

interface ConfigValues {
  active_llm_profile_id: string | null;
  llm_model_override: string | null;
  embedding_model: string | null;
  upload_dir: string | null;
  max_file_size_mb: string | null;
  chunk_size: string | null;
  chunk_overlap: string | null;
  rag_top_k: string | null;
  bibliographic_lookup_enabled: string | null;
  bibliographic_auto_apply_enabled: string | null;
  bibliographic_lookup_contact_email: string | null;
}

interface LLMProfileOption {
  id: string;
  provider: string;
  name: string;
  model: string;
}

export default function SettingsAdmin() {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [llmProfiles, setLlmProfiles] = useState<LLMProfileOption[]>([]);

  useEffect(() => {
    Promise.all([
      apiClient.get('/admin/config'),
      apiClient.get('/admin/llm-profiles'),
    ]).then(([configResponse, profileResponse]) => {
      form.setFieldsValue(configResponse.data);
      setLlmProfiles(profileResponse.data);
      setLoading(false);
    });
  }, [form]);

  const handleSave = async (values: ConfigValues) => {
    setSaving(true);
    try {
      await apiClient.put('/admin/config', { values });
      message.success(t('admin.configSaved'));
    } catch {
      message.error(t('admin.configSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div style={{ padding: 24, maxWidth: 720 }}>
      <Form form={form} onFinish={handleSave} layout="vertical">
        <Card title={t('admin.llmConfig')} style={{ marginBottom: 24 }}>
          <Form.Item
            name="active_llm_profile_id"
            label={t('admin.llmActiveProfile')}
            tooltip={t('admin.llmActiveProfileHint')}
          >
            <Select
              allowClear
              placeholder={t('admin.llmActiveProfilePlaceholder')}
              options={llmProfiles.map((profile) => ({
                value: profile.id,
                label: `${profile.name} (${profile.provider}) · ${profile.model}`,
              }))}
            />
          </Form.Item>
          <Collapse
            items={[
              {
                key: 'advanced',
                label: t('admin.llmAdvancedSettings'),
                children: (
                  <Form.Item
                    name="llm_model_override"
                    label={t('admin.llmModelOverride')}
                    tooltip={t('admin.llmModelOverrideHint')}
                    style={{ marginBottom: 0 }}
                  >
                    <Input placeholder="openai/gpt-4o-mini" />
                  </Form.Item>
                ),
              },
            ]}
          />
        </Card>

        <Card title={t('admin.embeddingConfig')} style={{ marginBottom: 24 }}>
          <Form.Item name="embedding_model" label={t('admin.embeddingModel')}>
            <Select
              options={[
                { value: 'BAAI/bge-m3', label: 'BAAI/bge-m3' },
                { value: 'BAAI/bge-large-en-v1.5', label: 'BAAI/bge-large-en-v1.5' },
                { value: 'sentence-transformers/all-MiniLM-L6-v2', label: 'all-MiniLM-L6-v2' },
              ]}
              allowClear
              showSearch
            />
          </Form.Item>
        </Card>

        <Card title={t('admin.ragConfig')} style={{ marginBottom: 24 }}>
          <Form.Item name="chunk_size" label={t('admin.chunkSize')}>
            <InputNumber min={128} max={4096} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="chunk_overlap" label={t('admin.chunkOverlap')}>
            <InputNumber min={0} max={512} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="rag_top_k" label={t('admin.ragTopK')}>
            <InputNumber min={1} max={20} style={{ width: '100%' }} />
          </Form.Item>
        </Card>

        <Card title={t('admin.storageConfig')} style={{ marginBottom: 24 }}>
          <Form.Item name="upload_dir" label={t('admin.uploadDir')}>
            <Input />
          </Form.Item>
          <Form.Item name="max_file_size_mb" label={t('admin.maxFileSize')}>
            <InputNumber min={1} max={1024} style={{ width: '100%' }} addonAfter="MB" />
          </Form.Item>
        </Card>

        <Card title={t('admin.bibliographicConfig')} style={{ marginBottom: 24 }}>
          <Form.Item
            name="bibliographic_lookup_enabled"
            label={t('admin.bibliographicLookupEnabled')}
            tooltip={t('admin.bibliographicLookupEnabledHint')}
            getValueProps={(value) => ({ checked: value === 'true' })}
            getValueFromEvent={(checked: boolean) => String(checked)}
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="bibliographic_auto_apply_enabled"
            label={t('admin.bibliographicAutoApplyEnabled')}
            tooltip={t('admin.bibliographicAutoApplyEnabledHint')}
            getValueProps={(value) => ({ checked: value === 'true' })}
            getValueFromEvent={(checked: boolean) => String(checked)}
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="bibliographic_lookup_contact_email"
            label={t('admin.bibliographicContactEmail')}
            tooltip={t('admin.bibliographicContactEmailHint')}
            rules={[{ type: 'email' }]}
          >
            <Input type="email" placeholder="metadata@example.org" />
          </Form.Item>
        </Card>

        <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving} block>
          {t('common.save')}
        </Button>
      </Form>
    </div>
  );
}
