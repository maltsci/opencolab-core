import { Button, Form, Input, message, Select, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import SectionCard from '../ui/SectionCard';
import apiClient from '../../services/api-client';
import type { Project } from '../../types/project';
import type { TaskDefinition } from '../../types/task';
import ProjectMembersCard from './ProjectMembersCard';

interface ProjectConfigPanelProps {
  project: Project;
  canManage: boolean;
  onProjectUpdated: (project: Project) => void;
}

interface ConfigFormValues {
  name: string;
  description?: string;
  instructions?: string;
  task_ids?: string[];
}

export default function ProjectConfigPanel({
  project,
  canManage,
  onProjectUpdated,
}: ProjectConfigPanelProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm<ConfigFormValues>();
  const [availableTasks, setAvailableTasks] = useState<TaskDefinition[]>([]);
  const [groupName, setGroupName] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setGroupName(null);
    if (project.research_group_id) {
      apiClient.get<{ name: string }>(`/research-groups/${project.research_group_id}`)
        .then(({ data }) => { if (active) setGroupName(data.name); })
        .catch(() => { if (active) setGroupName(null); });
    }
    return () => { active = false; };
  }, [project.research_group_id]);

  useEffect(() => {
    form.setFieldsValue({
      name: project.name,
      description: project.description ?? '',
      instructions: project.instructions ?? '',
      task_ids: project.task_ids ?? [],
    });
  }, [form, project]);

  useEffect(() => {
    // Options cover global tasks and tasks scoped to this project.
    apiClient
      .get<TaskDefinition[]>('/tasks', { params: { project_id: project.id } })
      .then((r) => setAvailableTasks(r.data))
      .catch(() => setAvailableTasks([]));
  }, [project.id]);

  const saveConfig = async (values: ConfigFormValues) => {
    try {
      const { data } = await apiClient.put<Project>(`/projects/${project.id}`, {
        name: values.name,
        description: values.description || null,
        instructions: values.instructions || null,
        task_ids: values.task_ids ?? [],
      });
      onProjectUpdated(data);
      message.success(t('project.updateSuccess'));
    } catch {
      message.error(t('project.updateFailed'));
    }
  };

  const refreshProject = async () => {
    const { data } = await apiClient.get<Project>(`/projects/${project.id}`);
    onProjectUpdated(data);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard title={t('projectHome.configTitle')}>
        <Form form={form} layout="vertical" onFinish={saveConfig} disabled={!canManage}>
          <Form.Item label={t('project.researchGroup')} extra={t('project.researchGroupHint')}>
            <Typography.Text>{groupName || t('resource.notProvided')}</Typography.Text>
          </Form.Item>
          <Form.Item name="name" label={t('project.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label={t('project.description')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="instructions"
            label={t('project.instructions')}
            extra={t('project.instructionsHint')}
          >
            <Input.TextArea rows={8} />
          </Form.Item>
          <Form.Item
            name="task_ids"
            label={t('projectHome.linkedTasksTitle')}
            extra={t('project.linkTasksHint')}
          >
            <Select
              mode="multiple"
              showSearch
              optionFilterProp="label"
              placeholder={t('projectHome.linkedTasksEmpty')}
              options={availableTasks.map((task) => ({
                value: task.id,
                label: task.name,
              }))}
            />
          </Form.Item>
          {canManage && (
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" onClick={() => form.submit()}>
                {t('common.save')}
              </Button>
            </Form.Item>
          )}
        </Form>
      </SectionCard>
      <SectionCard title={t('projectHome.membersTitle', { count: project.member_count })}>
        <ProjectMembersCard
          project={project}
          canManage={canManage}
          onChanged={() => { void refreshProject(); }}
        />
      </SectionCard>
    </div>
  );
}
