import {
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  InboxOutlined,
  MoreOutlined,
  PlusOutlined,
  ProjectOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Checkbox,
  Drawer,
  Dropdown,
  Form,
  Input,
  message,
  Modal,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  theme,
} from 'antd';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import type { MenuProps } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import EmptyState from '../components/ui/EmptyState';
import PageContainer from '../components/library/PageContainer';
import { RESEARCH_PROJECT_TEMPLATE } from '../constants/project-templates';
import { ROLES_CAN_CREATE_PROJECT, ROLES_PRIVILEGED } from '../constants/roles';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import type { Project } from '../types/project';
import type { TaskDefinition } from '../types/task';

const { Text, Paragraph } = Typography;

interface OwnerOption {
  id: string;
  username: string;
  display_name: string | null;
}

interface CreateFormValues {
  name: string;
  description?: string;
  instructions?: string;
  task_ids?: string[];
}

interface EditFormValues {
  name: string;
  description?: string;
  instructions?: string;
}

export default function Home() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { user } = useAuth();
  const navigate = useNavigate();
  const isPrivileged = user && ROLES_PRIVILEGED.includes(user.role);
  const canCreateProject = user && ROLES_CAN_CREATE_PROJECT.includes(user.role);

  const [projects, setProjects] = useState<Project[]>([]);
  const [pageLoading, setPageLoading] = useState(true);

  // Filters
  const [showArchived, setShowArchived] = useState(false);
  const [ownerFilter, setOwnerFilter] = useState<string[]>([]);
  const [scopeFilter, setScopeFilter] = useState<string>('all');
  const [owners, setOwners] = useState<OwnerOption[]>([]);

  // Create / edit drawers
  const [showNewProject, setShowNewProject] = useState(false);
  const [creating, setCreating] = useState(false);
  const [availableTasks, setAvailableTasks] = useState<TaskDefinition[]>([]);
  const [form] = Form.useForm<CreateFormValues>();
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [editForm] = Form.useForm<EditFormValues>();

  // Fetch owners list for admin/PI
  useEffect(() => {
    if (isPrivileged) {
      apiClient.get('/projects/owners').then((r) => setOwners(r.data));
    }
  }, [isPrivileged]);

  const fetchProjects = () => {
    // Home only shows projects the current user participates in.
    const scope = scopeFilter === 'own' ? 'own' : 'joined';
    if (isPrivileged && ownerFilter.length > 0) {
      const ownerParams = ownerFilter.map((id) => `owner_ids=${id}`).join('&');
      return apiClient
        .get(`/projects?scope=${scope}&${ownerParams}`, { params: { include_archived: showArchived || undefined } })
        .then((r) => setProjects(r.data));
    }
    const params: Record<string, string | boolean> = { scope };
    if (showArchived) params.include_archived = true;
    return apiClient.get('/projects', { params }).then((r) => setProjects(r.data));
  };

  useEffect(() => {
    fetchProjects().finally(() => setPageLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showArchived, ownerFilter, scopeFilter]);

  const openCreateDrawer = () => {
    setShowNewProject(true);
    if (availableTasks.length === 0) {
      apiClient
        .get<TaskDefinition[]>('/tasks')
        .then((r) => setAvailableTasks(r.data))
        .catch(() => undefined);
    }
  };

  const createProject = async (values: CreateFormValues) => {
    setCreating(true);
    try {
      const { data } = await apiClient.post<Project>('/projects', {
        name: values.name,
        description: values.description || null,
        instructions: values.instructions || null,
        task_ids: values.task_ids ?? [],
      });
      setShowNewProject(false);
      form.resetFields();
      navigate(`/projects/${data.id}`);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 403) {
        message.error(t('project.createForbidden'));
      } else {
        message.error(t('project.createFailed'));
      }
    } finally {
      setCreating(false);
    }
  };

  const updateProject = async (values: EditFormValues) => {
    if (!editingProject) return;
    await apiClient.put(`/projects/${editingProject.id}`, values);
    message.success(t('project.updateSuccess'));
    setEditingProject(null);
    fetchProjects();
  };

  const archiveProject = async (projectId: string) => {
    await apiClient.post(`/projects/${projectId}/archive`);
    message.success(t('project.archiveSuccess'));
    fetchProjects();
  };

  const unarchiveProject = async (projectId: string) => {
    await apiClient.post(`/projects/${projectId}/unarchive`);
    message.success(t('project.unarchiveSuccess'));
    fetchProjects();
  };

  const deleteProject = async (projectId: string) => {
    await apiClient.delete(`/projects/${projectId}`);
    message.success(t('project.deleteSuccess'));
    fetchProjects();
  };

  const leaveProject = async (projectId: string) => {
    await apiClient.delete(`/projects/${projectId}/leave`);
    message.success(t('project.left'));
    fetchProjects();
  };

  const canManageProject = (project: Project) => isPrivileged || project.is_owner;

  const projectMenuFor = (project: Project): MenuProps['items'] => {
    const items: MenuProps['items'] = [
      {
        key: 'memory',
        icon: <DatabaseOutlined />,
        label: t('memory.projectMemory'),
        onClick: () => navigate(`/projects/${project.id}/memory`),
      },
    ];

    if (canManageProject(project)) {
      items.push({
        key: 'edit',
        icon: <EditOutlined />,
        label: t('project.edit'),
        onClick: () => {
          setEditingProject(project);
        },
      });
      items.push({
        key: project.archived ? 'unarchive' : 'archive',
        icon: project.archived ? <UndoOutlined /> : <InboxOutlined />,
        label: project.archived ? t('project.unarchive') : t('project.archive'),
        onClick: () => {
          Modal.confirm({
            title: project.archived ? t('project.unarchiveConfirm') : t('project.archiveConfirm'),
            onOk: () => (project.archived ? unarchiveProject(project.id) : archiveProject(project.id)),
          });
        },
      });
      items.push({
        key: 'delete',
        icon: <DeleteOutlined />,
        label: t('common.delete'),
        danger: true,
        onClick: () => {
          Modal.confirm({
            title: t('project.deleteConfirm'),
            okButtonProps: { danger: true },
            onOk: () => deleteProject(project.id),
          });
        },
      });
    }

    if (!isPrivileged && !project.is_owner) {
      items.push({
        key: 'leave',
        icon: <ExportOutlined />,
        label: t('project.leave'),
        onClick: () => {
          Modal.confirm({
            title: t('project.leaveConfirm'),
            onOk: () => leaveProject(project.id),
          });
        },
      });
    }

    return items;
  };

  const visibleProjects = projects.filter((project) => {
    if (!showArchived && project.archived) return false;
    return true;
  });

  const filterBar = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
      <Segmented
        value={scopeFilter}
        onChange={(val) => setScopeFilter(val as string)}
        options={[
          { value: 'all', label: t('project.scopeAll') },
          { value: 'own', label: t('project.scopeOwn') },
        ]}
      />
      {isPrivileged && (
        <Select
          mode="multiple"
          allowClear
          style={{ minWidth: 200 }}
          placeholder={t('project.filterByOwner')}
          value={ownerFilter}
          onChange={setOwnerFilter}
          options={owners.map((o) => ({
            value: o.id,
            label: o.display_name ? `${o.display_name} (${o.username})` : o.username,
          }))}
        />
      )}
      <Checkbox checked={showArchived} onChange={(e: CheckboxChangeEvent) => setShowArchived(e.target.checked)}>
        {t('project.showArchived')}
      </Checkbox>
    </div>
  );

  const projectGrid = (
    <Spin spinning={pageLoading}>
      {visibleProjects.length > 0 ? (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 16,
          }}
        >
          {visibleProjects.map((project) => (
            <Card
              key={project.id}
              hoverable
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/projects/${project.id}`)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  navigate(`/projects/${project.id}`);
                }
              }}
              title={(
                <Space size={8}>
                  <ProjectOutlined style={{ color: token.colorPrimary }} />
                  <span style={{ color: project.archived ? token.colorTextSecondary : undefined }}>
                    {project.name}
                  </span>
                </Space>
              )}
              extra={(
                <Dropdown
                  menu={{ items: projectMenuFor(project) }}
                  trigger={['click']}
                  placement="bottomRight"
                >
                  <Button
                    type="text"
                    size="small"
                    icon={<MoreOutlined />}
                    aria-label={t('common.more')}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Dropdown>
              )}
            >
              <Paragraph
                type="secondary"
                ellipsis={{ rows: 2 }}
                style={{ minHeight: 44, marginBottom: 12 }}
              >
                {project.description || t('project.noDescription')}
              </Paragraph>
              <Space size={8} wrap>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {t('project.memberCount', { count: project.member_count })}
                </Text>
                {project.is_owner ? (
                  <Tag color="blue">{t('project.owner')}</Tag>
                ) : project.owner_name ? (
                  <Tag>{t('project.ownedBy', { name: project.owner_name })}</Tag>
                ) : null}
                {project.archived && <Tag>{t('project.archived')}</Tag>}
              </Space>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<ProjectOutlined />}
          title={t('home.emptyProjectsTitle')}
          description={t('home.emptyProjectsDescription')}
          cta={canCreateProject ? {
            label: t('home.newProjectCta'),
            icon: <PlusOutlined />,
            onClick: openCreateDrawer,
          } : undefined}
        />
      )}
    </Spin>
  );

  return (
    <PageContainer
      title={t('project.researchEnvironments')}
      extra={canCreateProject ? (
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateDrawer}>
          {t('project.new')}
        </Button>
      ) : null}
    >
      {filterBar}
      {projectGrid}

      <Drawer
        title={t('project.new')}
        open={showNewProject}
        onClose={() => setShowNewProject(false)}
        size={520}
        destroyOnHidden
      >
        <Form form={form} onFinish={createProject} layout="vertical">
          <Form.Item name="name" label={t('project.name')} rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="description" label={t('project.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="instructions"
            label={(
              <Space>
                {t('project.instructions')}
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0 }}
                  onClick={() => form.setFieldsValue({ instructions: RESEARCH_PROJECT_TEMPLATE })}
                >
                  {t('project.useTemplate')}
                </Button>
              </Space>
            )}
            extra={t('project.instructionsHint')}
          >
            <Input.TextArea rows={10} placeholder={t('project.instructionsPlaceholder')} />
          </Form.Item>
          {availableTasks.length > 0 && (
            <Form.Item name="task_ids" label={t('project.linkTasks')} extra={t('project.linkTasksHint')}>
              <Checkbox.Group
                style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
                options={availableTasks.map((task) => ({
                  value: task.id,
                  label: `${task.name} — ${task.description}`,
                }))}
              />
            </Form.Item>
          )}
          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button type="primary" loading={creating} onClick={() => form.submit()}>
                {t('common.create')}
              </Button>
              <Button onClick={() => setShowNewProject(false)}>{t('common.cancel')}</Button>
            </Space>
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={t('project.editTitle')}
        open={!!editingProject}
        onClose={() => setEditingProject(null)}
        size={520}
        destroyOnHidden
      >
        {/* initialValues re-applies on each open because destroyOnHidden remounts the Form */}
        <Form
          form={editForm}
          onFinish={updateProject}
          layout="vertical"
          initialValues={{
            name: editingProject?.name,
            description: editingProject?.description ?? '',
            instructions: editingProject?.instructions ?? '',
          }}
        >
          <Form.Item name="name" label={t('project.name')} rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="description" label={t('project.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="instructions"
            label={t('project.instructions')}
            extra={t('project.instructionsHint')}
          >
            <Input.TextArea rows={10} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button type="primary" onClick={() => editForm.submit()}>
                {t('common.save')}
              </Button>
              <Button onClick={() => setEditingProject(null)}>{t('common.cancel')}</Button>
            </Space>
          </Form.Item>
        </Form>
      </Drawer>
    </PageContainer>
  );
}
