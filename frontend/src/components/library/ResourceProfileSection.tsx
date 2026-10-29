import { DeleteOutlined, EditOutlined, LinkOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons';
import { Alert, Button, Descriptions, Divider, Form, Input, Select, Space, Spin, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import apiClient from '../../services/api-client';
import type { ResearchAsset, ResourceProfile } from '../../types/research-asset';
import { formatDateTime } from './library-utils';

interface DirectionOption {
  id: string;
  name: string;
}

interface ResourceProfileSectionProps {
  asset: ResearchAsset;
  onUpdated?: () => void;
  readOnly?: boolean;
}

interface ResourceProfileFormValues {
  purpose?: string;
  suitable_for?: string;
  limitations?: string;
  access_instructions?: string;
  request_url?: string;
  gpu_configuration?: string;
  gpu_login_instructions?: string;
  gpu_maintenance_note?: string;
  code_repository_url?: string;
  code_runtime_environment?: string;
  code_license?: string;
  code_entrypoint?: string;
  model_weight_source?: string;
  model_weight_version?: string;
  model_weight_framework?: string;
  model_weight_license?: string;
  model_weight_usage_instructions?: string;
  dataset_source?: string;
  dataset_version?: string;
  dataset_format?: string;
  dataset_update_frequency?: string;
  last_confirmed_at?: string;
  review_due_at?: string;
}

interface DirectionLinkFormValues {
  direction_id: string;
  purpose?: string;
}

function toLocalDateTimeValue(value: string | null): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function ResourceProfileSection({ asset, onUpdated, readOnly = false }: ResourceProfileSectionProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<ResourceProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [linking, setLinking] = useState(false);
  const [linkSaving, setLinkSaving] = useState(false);
  const [directions, setDirections] = useState<DirectionOption[]>([]);
  const [profileForm] = Form.useForm<ResourceProfileFormValues>();
  const [linkForm] = Form.useForm<DirectionLinkFormValues>();
  const canUpdate = Boolean(profile?.can_update && !readOnly);
  const canManageDirectionLinks = Boolean(profile?.can_manage_direction_links && !readOnly);

  const loadProfile = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<ResourceProfile>(
        `/research-assets/${asset.id}/resource-profile`,
      );
      setProfile(data);
    } catch {
      message.error(t('resource.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setEditing(false);
    setLinking(false);
    linkForm.resetFields();
    void loadProfile();
  }, [asset.id]);

  const openEditor = () => {
    if (!profile) return;
    profileForm.setFieldsValue({
      purpose: profile.purpose ?? undefined,
      suitable_for: profile.suitable_for ?? undefined,
      limitations: profile.limitations ?? undefined,
      access_instructions: profile.access_instructions ?? undefined,
      request_url: profile.request_url ?? undefined,
      gpu_configuration: profile.gpu_configuration ?? undefined,
      gpu_login_instructions: profile.gpu_login_instructions ?? undefined,
      gpu_maintenance_note: profile.gpu_maintenance_note ?? undefined,
      code_repository_url: profile.code_repository_url ?? undefined,
      code_runtime_environment: profile.code_runtime_environment ?? undefined,
      code_license: profile.code_license ?? undefined,
      code_entrypoint: profile.code_entrypoint ?? undefined,
      model_weight_source: profile.model_weight_source ?? undefined,
      model_weight_version: profile.model_weight_version ?? undefined,
      model_weight_framework: profile.model_weight_framework ?? undefined,
      model_weight_license: profile.model_weight_license ?? undefined,
      model_weight_usage_instructions: profile.model_weight_usage_instructions ?? undefined,
      dataset_source: profile.dataset_source ?? undefined,
      dataset_version: profile.dataset_version ?? undefined,
      dataset_format: profile.dataset_format ?? undefined,
      dataset_update_frequency: profile.dataset_update_frequency ?? undefined,
      last_confirmed_at: toLocalDateTimeValue(profile.last_confirmed_at),
      review_due_at: toLocalDateTimeValue(profile.review_due_at),
    });
    setEditing(true);
  };

  const saveProfile = async () => {
    const values = await profileForm.validateFields();
    setSaving(true);
    try {
      const payload = {
        ...values,
        last_confirmed_at: values.last_confirmed_at
          ? new Date(values.last_confirmed_at).toISOString()
          : null,
        review_due_at: values.review_due_at
          ? new Date(values.review_due_at).toISOString()
          : null,
      };
      const { data } = await apiClient.patch<ResourceProfile>(
        `/research-assets/${asset.id}/resource-profile`,
        payload,
      );
      setProfile(data);
      setEditing(false);
      onUpdated?.();
      message.success(t('resource.saveSuccess'));
    } catch {
      message.error(t('resource.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const openDirectionLinker = async () => {
    setLinking(true);
    linkForm.resetFields();
    try {
      const { data } = await apiClient.get<{ items: DirectionOption[] }>(
        '/research-directions',
        { params: { status: 'active', limit: 100 } },
      );
      setDirections(data.items);
    } catch {
      setDirections([]);
      message.error(t('resource.directionLoadFailed'));
    }
  };

  const createDirectionLink = async () => {
    const values = await linkForm.validateFields();
    setLinkSaving(true);
    try {
      await apiClient.post(`/research-assets/${asset.id}/directions`, values);
      setLinking(false);
      await loadProfile();
      onUpdated?.();
      message.success(t('resource.directionLinkSuccess'));
    } catch {
      message.error(t('resource.directionLinkFailed'));
    } finally {
      setLinkSaving(false);
    }
  };

  const deleteDirectionLink = async (linkId: string) => {
    try {
      await apiClient.delete(`/research-assets/${asset.id}/directions/${linkId}`);
      await loadProfile();
      onUpdated?.();
      message.success(t('resource.directionUnlinkSuccess'));
    } catch {
      message.error(t('resource.directionUnlinkFailed'));
    }
  };

  return (
    <>
      <Divider titlePlacement="start">{t('resource.sectionTitle')}</Divider>
      <Spin spinning={loading}>
        {profile ? (
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            <Button
              icon={<RobotOutlined />}
              onClick={() => navigate(`/assistant?context=resource&query=${encodeURIComponent(asset.title)}`)}
            >
              {t('assistant.continueExploring')}
            </Button>
            {profile.is_stale ? (
              <Alert
                type="warning"
                showIcon
                message={t(canUpdate ? 'resource.staleInfoManage' : 'resource.staleInfo')}
                action={canUpdate ? (
                  <Button type="link" size="small" onClick={openEditor}>
                    {t('resource.reviewInfo')}
                  </Button>
                ) : null}
              />
            ) : profile.review_due_at === null ? (
              <Alert
                type="info"
                showIcon
                message={t(canUpdate ? 'resource.reviewMissingManage' : 'resource.reviewMissing')}
                action={canUpdate ? (
                  <Button type="link" size="small" onClick={openEditor}>
                    {t('resource.reviewInfo')}
                  </Button>
                ) : null}
              />
            ) : null}
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('resource.steward')}>
                {profile.steward_name || t('resource.stewardMissing')}
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.purpose')}>
                {profile.purpose || t('resource.notProvided')}
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.suitableFor')}>
                {profile.suitable_for || t('resource.notProvided')}
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.limitations')}>
                {profile.limitations || t('resource.notProvided')}
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.accessPath')}>
                <Space orientation="vertical" size={2}>
                  <Typography.Text>
                    {profile.access_instructions || t('resource.accessMissing')}
                  </Typography.Text>
                  {profile.request_url ? (
                    <Typography.Link href={profile.request_url} target="_blank" rel="noreferrer">
                      {t('resource.openRequest')}
                    </Typography.Link>
                  ) : null}
                  {profile.protected_access_location ? (
                    <Typography.Text copyable={{ text: profile.protected_access_location }}>
                      {profile.protected_access_location}
                    </Typography.Text>
                  ) : null}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.lastConfirmed')}>
                {profile.last_confirmed_at
                  ? formatDateTime(profile.last_confirmed_at, i18n.language)
                  : t('resource.notConfirmed')}
              </Descriptions.Item>
              <Descriptions.Item label={t('resource.reviewDue')}>
                {profile.review_due_at
                  ? formatDateTime(profile.review_due_at, i18n.language)
                  : t('resource.notProvided')}
              </Descriptions.Item>
              {asset.asset_type === 'gpu' ? (
                <>
                  <Descriptions.Item label={t('resource.gpuConfiguration')}>
                    {profile.gpu_configuration || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.gpuLoginInstructions')}>
                    {profile.gpu_login_instructions || t('resource.accessMissing')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.gpuMaintenanceNote')}>
                    {profile.gpu_maintenance_note || t('resource.gpuManualStatus')}
                  </Descriptions.Item>
                </>
              ) : null}
              {asset.asset_type === 'code_repository' ? (
                <>
                  <Descriptions.Item label={t('resource.codeRepositoryUrl')}>
                    {profile.code_repository_url || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.codeRuntimeEnvironment')}>
                    {profile.code_runtime_environment || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.codeLicense')}>
                    {profile.code_license || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.codeEntrypoint')}>
                    {profile.code_entrypoint || t('resource.notProvided')}
                  </Descriptions.Item>
                </>
              ) : null}
              {asset.asset_type === 'model_weight' ? (
                <>
                  <Descriptions.Item label={t('resource.modelWeightSource')}>
                    {profile.model_weight_source || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.modelWeightVersion')}>
                    {profile.model_weight_version || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.modelWeightFramework')}>
                    {profile.model_weight_framework || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.modelWeightLicense')}>
                    {profile.model_weight_license || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.modelWeightUsageInstructions')}>
                    {profile.model_weight_usage_instructions || t('resource.notProvided')}
                  </Descriptions.Item>
                </>
              ) : null}
              {asset.asset_type === 'dataset' ? (
                <>
                  <Descriptions.Item label={t('resource.datasetSource')}>
                    {profile.dataset_source || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.datasetVersion')}>
                    {profile.dataset_version || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.datasetFormat')}>
                    {profile.dataset_format || t('resource.notProvided')}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('resource.datasetUpdateFrequency')}>
                    {profile.dataset_update_frequency || t('resource.notProvided')}
                  </Descriptions.Item>
                </>
              ) : null}
              <Descriptions.Item label={t('resource.directions')}>
                {profile.directions.length > 0 ? (
                  <Space size={[4, 6]} wrap>
                    {profile.directions.map((link) => (
                      <Tag
                        key={link.id}
                        closable={canManageDirectionLinks}
                        closeIcon={<DeleteOutlined />}
                        onClose={(event) => {
                          event.preventDefault();
                          void deleteDirectionLink(link.id);
                        }}
                      >
                        <Button
                          type="link"
                          size="small"
                          onClick={() => navigate(`/research?direction=${encodeURIComponent(link.direction_id)}`)}
                          style={{ height: 'auto', padding: 0 }}
                        >
                          {link.direction_name}
                        </Button>
                        {link.purpose ? ` · ${link.purpose}` : ''}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  t('resource.directionsEmpty')
                )}
              </Descriptions.Item>
            </Descriptions>
            <Space wrap>
              {canUpdate ? (
                <Button icon={<EditOutlined />} onClick={openEditor}>
                  {t('resource.editInfo')}
                </Button>
              ) : null}
              {canManageDirectionLinks ? (
                <Button icon={<LinkOutlined />} onClick={() => void openDirectionLinker()}>
                  {t('resource.linkDirection')}
                </Button>
              ) : null}
            </Space>

            {editing && canUpdate ? (
              <Form form={profileForm} layout="vertical" onFinish={() => void saveProfile()}>
                <Form.Item name="purpose" label={t('resource.purpose')}>
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.Item name="suitable_for" label={t('resource.suitableFor')}>
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.Item name="limitations" label={t('resource.limitations')}>
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Form.Item
                  name="access_instructions"
                  label={t('resource.accessPath')}
                  extra={t('resource.accessInstructionsHint')}
                >
                  <Input.TextArea rows={2} placeholder={t('resource.accessInstructionsPlaceholder')} />
                </Form.Item>
                <Form.Item
                  name="request_url"
                  label={t('resource.requestUrl')}
                  extra={t('resource.requestUrlHint')}
                >
                  <Input type="url" placeholder={t('resource.requestUrlPlaceholder')} />
                </Form.Item>
                {asset.asset_type === 'gpu' ? (
                  <>
                    <Form.Item name="gpu_configuration" label={t('resource.gpuConfiguration')}>
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item name="gpu_login_instructions" label={t('resource.gpuLoginInstructions')}>
                      <Input.TextArea rows={2} />
                    </Form.Item>
                    <Form.Item name="gpu_maintenance_note" label={t('resource.gpuMaintenanceNote')}>
                      <Input.TextArea rows={2} />
                    </Form.Item>
                  </>
                ) : null}
                {asset.asset_type === 'code_repository' ? (
                  <>
                    <Form.Item name="code_repository_url" label={t('resource.codeRepositoryUrl')}><Input /></Form.Item>
                    <Form.Item name="code_runtime_environment" label={t('resource.codeRuntimeEnvironment')}><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="code_license" label={t('resource.codeLicense')}><Input /></Form.Item>
                    <Form.Item name="code_entrypoint" label={t('resource.codeEntrypoint')}><Input /></Form.Item>
                  </>
                ) : null}
                {asset.asset_type === 'model_weight' ? (
                  <>
                    <Form.Item name="model_weight_source" label={t('resource.modelWeightSource')}><Input /></Form.Item>
                    <Form.Item name="model_weight_version" label={t('resource.modelWeightVersion')}><Input /></Form.Item>
                    <Form.Item name="model_weight_framework" label={t('resource.modelWeightFramework')}><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="model_weight_license" label={t('resource.modelWeightLicense')}><Input /></Form.Item>
                    <Form.Item name="model_weight_usage_instructions" label={t('resource.modelWeightUsageInstructions')}><Input.TextArea rows={2} /></Form.Item>
                  </>
                ) : null}
                {asset.asset_type === 'dataset' ? (
                  <>
                    <Form.Item name="dataset_source" label={t('resource.datasetSource')}><Input.TextArea rows={2} /></Form.Item>
                    <Form.Item name="dataset_version" label={t('resource.datasetVersion')}><Input /></Form.Item>
                    <Form.Item name="dataset_format" label={t('resource.datasetFormat')}><Input /></Form.Item>
                    <Form.Item name="dataset_update_frequency" label={t('resource.datasetUpdateFrequency')}><Input /></Form.Item>
                  </>
                ) : null}
                <Form.Item name="last_confirmed_at" label={t('resource.lastConfirmed')}>
                  <Input type="datetime-local" />
                </Form.Item>
                <Form.Item name="review_due_at" label={t('resource.reviewDue')}>
                  <Input type="datetime-local" />
                </Form.Item>
                <Space>
                  <Button type="primary" loading={saving} onClick={() => profileForm.submit()}>
                    {t('common.save')}
                  </Button>
                  <Button onClick={() => setEditing(false)}>{t('common.cancel')}</Button>
                </Space>
              </Form>
            ) : null}

            {linking && canManageDirectionLinks ? (
              <Form form={linkForm} layout="vertical" onFinish={() => void createDirectionLink()}>
                <Form.Item
                  name="direction_id"
                  label={t('resource.direction')}
                  rules={[{ required: true, message: t('resource.directionRequired') }]}
                >
                  <Select
                    showSearch
                    optionFilterProp="label"
                    options={directions.map((direction) => ({
                      value: direction.id,
                      label: direction.name,
                    }))}
                  />
                </Form.Item>
                <Form.Item name="purpose" label={t('resource.directionPurpose')}>
                  <Input.TextArea rows={2} />
                </Form.Item>
                <Space>
                  <Button type="primary" icon={<PlusOutlined />} loading={linkSaving} onClick={() => linkForm.submit()}>
                    {t('resource.linkDirection')}
                  </Button>
                  <Button onClick={() => setLinking(false)}>{t('common.cancel')}</Button>
                </Space>
              </Form>
            ) : null}
          </Space>
        ) : null}
      </Spin>
    </>
  );
}
