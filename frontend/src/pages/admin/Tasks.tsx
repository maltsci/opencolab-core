import {
  CodeOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import apiClient from '../../services/api-client';
import type { TaskDefinition } from '../../types/task';
import type { WorkflowDefinition } from '../../types/workflow';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

interface ProjectOption {
  id: string;
  name: string;
}

interface TaskFormValues {
  id: string;
  name: string;
  description: string;
  workflow_id?: string;
  starter_prompts: string[];
  project_ids: string[];
  input_required: string[];
  project_context_policy_extra: string;
  result_presentation_extra: string;
  is_enabled: boolean;
  publish_scope: 'global' | 'selected_projects';
}

function renderJsonBlock(value: Record<string, unknown>) {
  if (Object.keys(value).length === 0) {
    return <Text type="secondary">-</Text>;
  }

  return (
    <pre
      style={{
        margin: 0,
        padding: 12,
        borderRadius: 6,
        background: '#f7f8fa',
        border: '1px solid #f0f0f0',
        overflowX: 'auto',
        fontSize: 12,
        lineHeight: 1.5,
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function getRequiredInputKeys(inputSchema: Record<string, unknown>): string[] {
  const required = inputSchema.required;
  return Array.isArray(required)
    ? required.filter((item): item is string => typeof item === 'string')
    : [];
}

function normalizeStringList(items: string[] | undefined): string[] {
  const seen = new Set<string>();
  return (items ?? []).reduce<string[]>((acc, item) => {
    const trimmed = item.trim();
    if (!trimmed || seen.has(trimmed)) {
      return acc;
    }
    seen.add(trimmed);
    acc.push(trimmed);
    return acc;
  }, []);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }

  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function extractApiErrorMessage(
  error: unknown,
  fallback: string,
): string {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return error instanceof Error ? error.message : fallback;
  }

  const detail = (error as {
    response?: { data?: { detail?: string | Array<{ msg?: string; loc?: Array<string | number> }> } };
  }).response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const location = Array.isArray(item.loc) ? item.loc.join('.') : '';
        const messageText = typeof item.msg === 'string' ? item.msg : '';
        return [location, messageText].filter(Boolean).join(': ');
      })
      .filter(Boolean)
      .join('; ') || fallback;
  }

  return error instanceof Error ? error.message : fallback;
}

function trimmedRequiredValidator(messageText: string) {
  return async (_: unknown, value: string | undefined) => {
    if (typeof value === 'string' && value.trim()) {
      return;
    }
    throw new Error(messageText);
  };
}

export default function TasksAdmin() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskDefinition[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<TaskDefinition | null>(null);
  const [tasksLoadError, setTasksLoadError] = useState<string | null>(null);
  const [updatingTaskId, setUpdatingTaskId] = useState<string | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);
  const [workflowsLoadError, setWorkflowsLoadError] = useState<string | null>(null);
  const [projectsLoadError, setProjectsLoadError] = useState<string | null>(null);
  const [form] = Form.useForm<TaskFormValues>();

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.allSettled([
      apiClient.get<TaskDefinition[]>('/admin/tasks'),
      apiClient.get<WorkflowDefinition[]>('/workflows'),
      apiClient.get<ProjectOption[]>('/projects'),
    ]).then(([tasksResult, workflowsResult, projectsResult]) => {
      if (tasksResult.status === 'fulfilled') {
        setTasks(tasksResult.value.data);
        setTasksLoadError(null);
      } else {
        setTasks([]);
        setTasksLoadError(extractApiErrorMessage(tasksResult.reason, t('admin.tasksLoadTasksFailed')));
      }

      if (workflowsResult.status === 'fulfilled') {
        setWorkflows(workflowsResult.value.data);
        setWorkflowsLoadError(null);
      } else {
        setWorkflows([]);
        setWorkflowsLoadError(extractApiErrorMessage(workflowsResult.reason, t('admin.tasksLoadWorkflowsFailed')));
      }

      if (projectsResult.status === 'fulfilled') {
        setProjects(projectsResult.value.data);
        setProjectsLoadError(null);
      } else {
        setProjects([]);
        setProjectsLoadError(extractApiErrorMessage(projectsResult.reason, t('admin.tasksLoadProjectsFailed')));
      }

      setLoading(false);
    });
  }, [t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const taskCountLabel = useMemo(
    () => t('admin.tasksCount', { count: tasks.length }),
    [tasks.length, t],
  );

  const workflowOptions = useMemo(
    () => workflows.map((workflow) => ({
      value: workflow.id,
      label: `${workflow.name} (${workflow.id})`,
    })),
    [workflows],
  );

  const projectOptions = useMemo(
    () => projects.map((project) => ({
      value: project.id,
      label: project.name,
    })),
    [projects],
  );

  const projectNameMap = useMemo(
    () => new Map(projects.map((project) => [project.id, project.name])),
    [projects],
  );

  const workflowNameMap = useMemo(
    () => new Map(workflows.map((workflow) => [workflow.id, workflow.name])),
    [workflows],
  );

  const parseJsonField = (value: string, fieldName: string) => {
    try {
      const parsed = value.trim() ? JSON.parse(value) : {};
      if (!isPlainObject(parsed)) {
        throw new Error(t('admin.tasksInvalidJsonObject', { field: fieldName }));
      }

      return parsed;
    } catch (error) {
      if (error instanceof Error && error.message === t('admin.tasksInvalidJsonObject', { field: fieldName })) {
        throw error;
      }

      throw new Error(t('admin.tasksInvalidJson', { field: fieldName }));
    }
  };

  const publishScope = Form.useWatch('publish_scope', form);

  const openCreateModal = () => {
    setEditingTask(null);
    form.setFieldsValue({
      id: '',
      name: '',
      description: '',
      workflow_id: undefined,
      starter_prompts: [],
      project_ids: [],
      input_required: [],
      project_context_policy_extra: '{}',
      result_presentation_extra: '{}',
      is_enabled: false,
      publish_scope: 'selected_projects',
    });
    setCreateOpen(true);
  };

  const openEditModal = (task: TaskDefinition) => {
    setEditingTask(task);
    form.setFieldsValue({
      id: task.id,
      name: task.name,
      description: task.description,
      workflow_id: task.workflow_id,
      starter_prompts: task.starter_prompts,
      project_ids: task.project_ids,
      input_required: getRequiredInputKeys(task.input_schema),
      project_context_policy_extra: JSON.stringify(task.project_context_policy, null, 2),
      result_presentation_extra: JSON.stringify(task.result_presentation, null, 2),
      is_enabled: task.is_enabled,
      publish_scope: task.project_ids.length === 0 ? 'global' : 'selected_projects',
    });
    setCreateOpen(true);
  };

  const handleSubmit = async (values: TaskFormValues) => {
    setCreating(true);
    try {
      const normalizedInputRequired = normalizeStringList(values.input_required);
      const normalizedStarterPrompts = normalizeStringList(values.starter_prompts);
      const projectIds = values.publish_scope === 'global'
        ? []
        : normalizeStringList(values.project_ids);
      const projectContextPolicy = parseJsonField(
        values.project_context_policy_extra,
        t('admin.tasksProjectContextPolicy'),
      );
      const resultPresentation = parseJsonField(
        values.result_presentation_extra,
        t('admin.tasksResultPresentation'),
      );
      const payload = {
        version: 1,
        name: values.name.trim(),
        description: values.description.trim(),
        workflow_id: values.workflow_id?.trim(),
        input_schema: {
          type: 'object',
          required: normalizedInputRequired,
        },
        starter_prompts: normalizedStarterPrompts,
        project_context_policy: projectContextPolicy,
        result_presentation: resultPresentation,
        is_enabled: values.is_enabled,
        project_ids: projectIds,
      };

      if (editingTask) {
        const { data } = await apiClient.patch<TaskDefinition>(`/admin/tasks/${editingTask.id}`, payload);
        setTasks((prev) => prev.map((item) => (item.id === editingTask.id ? data : item)));
        message.success(t('admin.tasksUpdateSuccess'));
      } else {
        await apiClient.post('/admin/tasks', {
          id: values.id.trim(),
          ...payload,
        });
        message.success(t('admin.tasksCreateSuccess'));
        loadData();
      }

      setCreateOpen(false);
      setEditingTask(null);
      form.resetFields();
    } catch (error) {
      message.error(extractApiErrorMessage(
        error,
        editingTask ? t('admin.tasksUpdateFailed') : t('admin.tasksCreateFailed'),
      ));
    } finally {
      setCreating(false);
    }
  };

  const updateTaskEnabled = async (task: TaskDefinition, isEnabled: boolean) => {
    setUpdatingTaskId(task.id);
    try {
      const { data } = await apiClient.patch<TaskDefinition>(`/admin/tasks/${task.id}`, {
        is_enabled: isEnabled,
      });
      setTasks((prev) => prev.map((item) => (item.id === task.id ? data : item)));
      message.success(isEnabled ? t('admin.tasksEnableSuccess') : t('admin.tasksDisableSuccess'));
    } catch (error) {
      message.error(extractApiErrorMessage(error, t('admin.tasksUpdateFailed')));
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const deleteTask = async (task: TaskDefinition) => {
    setDeletingTaskId(task.id);
    try {
      await apiClient.delete(`/admin/tasks/${task.id}`);
      setTasks((prev) => prev.filter((item) => item.id !== task.id));
      message.success(t('admin.tasksDeleteSuccess'));
    } catch (error) {
      message.error(extractApiErrorMessage(error, t('admin.tasksDeleteFailed')));
    } finally {
      setDeletingTaskId(null);
    }
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
            <Space orientation="vertical" size={4}>
              <Title level={4} style={{ margin: 0 }}>
                {t('admin.tasks')}
              </Title>
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                {t('admin.tasksDescription')}
              </Paragraph>
              <Text type="secondary">{taskCountLabel}</Text>
            </Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={openCreateModal}
              disabled={workflows.length === 0}
            >
              {t('admin.tasksCreate')}
            </Button>
          </div>
        </Card>

        <Alert
          type="info"
          showIcon
          message={t('admin.tasksStatusTitle')}
          description={t('admin.tasksStatusDescription')}
        />

        {tasksLoadError ? (
          <Alert
            type="error"
            showIcon
            message={t('admin.tasksLoadTasksFailed')}
            description={tasksLoadError}
          />
        ) : null}

        {workflowsLoadError ? (
          <Alert
            type="error"
            showIcon
            message={t('admin.tasksLoadWorkflowsFailed')}
            description={workflowsLoadError}
          />
        ) : null}

        {projectsLoadError ? (
          <Alert
            type="warning"
            showIcon
            message={t('admin.tasksLoadProjectsFailed')}
            description={t('admin.tasksLoadProjectsWarning')}
          />
        ) : null}

        {workflows.length === 0 ? (
          <Alert
            type="warning"
            showIcon
            message={t('admin.tasksNoWorkflowsTitle')}
            description={t('admin.tasksNoWorkflowsDescription')}
          />
        ) : null}

        {tasksLoadError ? null : tasks.length === 0 ? (
          <Card>
            <Empty description={t('admin.tasksEmpty')} />
          </Card>
        ) : (
          <Collapse
            items={tasks.map((task) => {
              const visibleProjects = task.project_ids
                .map((projectId) => projectNameMap.get(projectId) ?? projectId);
              const requiredInputs = getRequiredInputKeys(task.input_schema);
              const workflowName = workflowNameMap.get(task.workflow_id);

              return {
                key: task.id,
                label: (
                  <Space size={12} wrap>
                    <Text strong>{task.name}</Text>
                    <Tag>{task.id}</Tag>
                    <Tag color="blue">{t('admin.tasksVersion', { version: task.version })}</Tag>
                    <Tag color={task.is_enabled ? 'success' : 'default'}>
                      {task.is_enabled ? t('admin.tasksEnabled') : t('admin.tasksDisabled')}
                    </Tag>
                    <Tag color={task.project_ids.length === 0 ? 'purple' : 'geekblue'}>
                      {task.project_ids.length === 0
                        ? t('admin.tasksScopeGlobal')
                        : t('admin.tasksScopeProjects', { count: task.project_ids.length })}
                    </Tag>
                    <Tag color="processing">
                      {t('admin.tasksWorkflowBound')}: {workflowName ?? task.workflow_id}
                    </Tag>
                  </Space>
                ),
                children: (
                  <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                    <Space size={12} wrap>
                      <Button
                        type={task.is_enabled ? 'default' : 'primary'}
                        loading={updatingTaskId === task.id}
                        onClick={() => void updateTaskEnabled(task, !task.is_enabled)}
                      >
                        {task.is_enabled ? t('admin.tasksDisableAction') : t('admin.tasksEnableAction')}
                      </Button>
                      <Button
                        icon={<EditOutlined />}
                        onClick={() => openEditModal(task)}
                      >
                        {t('admin.tasksEditAction')}
                      </Button>
                      <Popconfirm
                        title={t('admin.tasksDeleteConfirmTitle')}
                        description={task.is_builtin
                          ? t('admin.tasksBuiltInDeleteHint')
                          : t('admin.tasksDeleteConfirmDescription')}
                        okText={t('common.delete')}
                        cancelText={t('common.cancel')}
                        disabled={task.is_builtin}
                        onConfirm={() => void deleteTask(task)}
                      >
                        <Button
                          danger
                          icon={<DeleteOutlined />}
                          loading={deletingTaskId === task.id}
                          disabled={task.is_builtin}
                        >
                          {t('admin.tasksDeleteAction')}
                        </Button>
                      </Popconfirm>
                      <Button
                        icon={<PlayCircleOutlined />}
                        disabled={!task.is_enabled}
                        onClick={() => navigate('/')}
                      >
                        {t('admin.tasksOpenLauncher')}
                      </Button>
                      {!task.is_enabled ? (
                        <Text type="secondary">{t('admin.tasksEnableToLaunchHint')}</Text>
                      ) : null}
                    </Space>
                    <Paragraph style={{ marginBottom: 0 }}>{task.description}</Paragraph>

                    <Row gutter={[16, 16]}>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksStarterPrompts')}>
                          {task.starter_prompts.length === 0 ? (
                            <Text type="secondary">{t('admin.tasksNoStarterPrompts')}</Text>
                          ) : (
                            <Space wrap>
                              {task.starter_prompts.map((prompt) => (
                                <Tag key={prompt}>{prompt}</Tag>
                              ))}
                            </Space>
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksVisibleProjects')}>
                          {visibleProjects.length === 0 ? (
                            <Text type="secondary">{t('admin.tasksScopeGlobalDescription')}</Text>
                          ) : (
                            <Space wrap>
                              {visibleProjects.map((projectName) => (
                                <Tag key={projectName} color="geekblue">
                                  {projectName}
                                </Tag>
                              ))}
                            </Space>
                          )}
                        </Card>
                      </Col>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksInputSchema')} extra={<CodeOutlined />}>
                          {renderJsonBlock(task.input_schema)}
                        </Card>
                      </Col>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksSummary')}>
                          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                            <Text>
                              <Text strong>{t('admin.tasksWorkflowIdLabel')}:</Text>{' '}
                              {workflowName ? `${workflowName} (${task.workflow_id})` : task.workflow_id}
                            </Text>
                            <Text>
                              <Text strong>{t('admin.tasksRequiredFieldsLabel')}:</Text>{' '}
                              {requiredInputs.length > 0
                                ? requiredInputs.join(', ')
                                : t('admin.tasksNoRequiredFields')}
                            </Text>
                          </Space>
                        </Card>
                      </Col>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksProjectContextPolicy')} extra={<CodeOutlined />}>
                          {renderJsonBlock(task.project_context_policy)}
                        </Card>
                      </Col>
                      <Col xs={24} md={12}>
                        <Card size="small" title={t('admin.tasksResultPresentation')} extra={<CodeOutlined />}>
                          {renderJsonBlock(task.result_presentation)}
                        </Card>
                      </Col>
                    </Row>
                  </Space>
                ),
              };
            })}
          />
        )}
      </Space>

      <Modal
        title={editingTask ? t('admin.tasksEditTitle') : t('admin.tasksCreateTitle')}
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          setEditingTask(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={creating}
        width={820}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          initialValues={{
            starter_prompts: [],
            project_ids: [],
            input_required: [],
            project_context_policy_extra: '{}',
            result_presentation_extra: '{}',
            is_enabled: false,
            publish_scope: 'selected_projects',
          }}
        >
          <Form.Item
            name="id"
            label={t('admin.tasksId')}
            rules={[{ validator: trimmedRequiredValidator(t('admin.tasksIdRequired')) }]}
          >
            <Input placeholder="literature-gap-analysis" disabled={Boolean(editingTask)} />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('admin.tasksName')}
            rules={[{ validator: trimmedRequiredValidator(t('admin.tasksNameRequired')) }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="description"
            label={t('admin.tasksDescriptionField')}
            rules={[{ validator: trimmedRequiredValidator(t('admin.tasksDescriptionRequired')) }]}
          >
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="workflow_id"
            label={t('admin.tasksWorkflow')}
            rules={[{ required: true, message: t('admin.tasksWorkflowRequired') }]}
          >
            <Select
              placeholder={t('admin.tasksWorkflowPlaceholder')}
              options={workflowOptions}
            />
          </Form.Item>
          <Form.Item name="starter_prompts" label={t('admin.tasksStarterPrompts')}>
            <Select
              mode="tags"
              placeholder={t('admin.tasksStarterPromptsPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            name="publish_scope"
            label={t('admin.tasksPublishScope')}
          >
            <Segmented
              block
              options={[
                { label: t('admin.tasksScopeSelectedProjectsOption'), value: 'selected_projects' },
                { label: t('admin.tasksScopeGlobalOption'), value: 'global' },
              ]}
            />
          </Form.Item>
          <Alert
            type={publishScope === 'global' ? 'warning' : 'info'}
            showIcon
            style={{ marginBottom: 16 }}
            message={
              publishScope === 'global'
                ? t('admin.tasksGlobalScopeTitle')
                : t('admin.tasksScopedPublishTitle')
            }
            description={
              publishScope === 'global'
                ? t('admin.tasksVisibleProjectsHint')
                : t('admin.tasksScopedPublishDescription')
            }
          />
          {publishScope === 'selected_projects' ? (
            <Form.Item
              name="project_ids"
              label={t('admin.tasksVisibleProjects')}
              extra={projectsLoadError ? t('admin.tasksVisibleProjectsUnavailableHint') : undefined}
              rules={[{
                validator: async (_, value: string[] | undefined) => {
                  if (normalizeStringList(value).length > 0) {
                    return;
                  }
                  throw new Error(t('admin.tasksVisibleProjectsRequired'));
                },
              }]}
            >
              <Select
                mode="multiple"
                allowClear
                placeholder={t('admin.tasksVisibleProjectsPlaceholder')}
                options={projectOptions}
                disabled={projectOptions.length === 0}
              />
            </Form.Item>
          ) : null}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="input_required" label={t('admin.tasksRequiredInputs')}>
                <Select mode="tags" placeholder={t('admin.tasksRequiredInputsPlaceholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="is_enabled"
                label={t('admin.tasksEnabledLabel')}
                valuePropName="checked"
                extra={t('admin.tasksEnabledHint')}
              >
                <Switch checkedChildren={t('admin.tasksEnabled')} unCheckedChildren={t('admin.tasksDisabled')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="project_context_policy_extra"
                label={t('admin.tasksProjectContextPolicy')}
                extra={t('admin.tasksProjectContextPolicyHint')}
              >
                <TextArea rows={6} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="result_presentation_extra"
                label={t('admin.tasksResultPresentation')}
                extra={t('admin.tasksResultPresentationHint')}
              >
                <TextArea rows={6} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
}
