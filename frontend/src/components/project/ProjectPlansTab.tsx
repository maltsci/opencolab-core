import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons';
import {
  Button,
  DatePicker,
  Empty,
  Form,
  Input,
  List,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import dayjs from 'dayjs';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import SectionCard from '../ui/SectionCard';
import { useAuth } from '../../hooks/useAuth';
import { ROLES_PRIVILEGED } from '../../constants/roles';
import apiClient from '../../services/api-client';
import type {
  PlanPriority,
  PlanStatus,
  Project,
  ProjectMember,
  ProjectPlan,
} from '../../types/project';

const { Text } = Typography;

const PRIORITY_COLORS: Record<PlanPriority, string> = {
  low: 'default',
  medium: 'blue',
  high: 'red',
};

const STATUS_COLORS: Record<PlanStatus, string> = {
  todo: 'default',
  in_progress: 'processing',
  done: 'success',
};

interface PlanFormValues {
  title: string;
  content?: string;
  start_date?: dayjs.Dayjs | null;
  due_date?: dayjs.Dayjs | null;
  priority: PlanPriority;
  tags?: string[];
  assignee_id?: string | null;
}

interface ProjectPlansTabProps {
  project: Project;
  canManage: boolean;
}

export default function ProjectPlansTab({ project, canManage }: ProjectPlansTabProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isPrivileged = !!user && ROLES_PRIVILEGED.includes(user.role);
  const [plans, setPlans] = useState<ProjectPlan[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingPlan, setEditingPlan] = useState<ProjectPlan | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<PlanFormValues>();

  const fetchPlans = () => {
    setLoading(true);
    apiClient
      .get(`/projects/${project.id}/plans`)
      .then((r) => setPlans(r.data))
      .catch(() => message.error(t('plan.loadFailed')))
      .finally(() => setLoading(false));
  };

  useEffect(fetchPlans, [project.id]);

  useEffect(() => {
    apiClient
      .get(`/projects/${project.id}/members`)
      .then((r) => setMembers(r.data))
      .catch(() => undefined);
  }, [project.id]);

  const canEditPlan = (plan: ProjectPlan) =>
    isPrivileged || canManage || plan.created_by === user?.id;

  const canChangeStatus = (plan: ProjectPlan) =>
    canEditPlan(plan) || plan.assignee_id === user?.id;

  const openCreate = () => {
    setEditingPlan(null);
    form.resetFields();
    form.setFieldsValue({ priority: 'medium' });
    setModalOpen(true);
  };

  const openEdit = (plan: ProjectPlan) => {
    setEditingPlan(plan);
    form.setFieldsValue({
      title: plan.title,
      content: plan.content ?? '',
      start_date: plan.start_date ? dayjs(plan.start_date) : null,
      due_date: plan.due_date ? dayjs(plan.due_date) : null,
      priority: plan.priority,
      tags: plan.tags,
      assignee_id: plan.assignee_id,
    });
    setModalOpen(true);
  };

  const submitForm = async (values: PlanFormValues) => {
    const payload = {
      title: values.title,
      content: values.content || null,
      start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
      due_date: values.due_date ? values.due_date.format('YYYY-MM-DD') : null,
      priority: values.priority,
      tags: values.tags ?? [],
      assignee_id: values.assignee_id ?? null,
    };
    try {
      if (editingPlan) {
        await apiClient.put(`/projects/${project.id}/plans/${editingPlan.id}`, payload);
      } else {
        await apiClient.post(`/projects/${project.id}/plans`, payload);
      }
      setModalOpen(false);
      fetchPlans();
      message.success(t(editingPlan ? 'plan.updateSuccess' : 'plan.createSuccess'));
    } catch {
      message.error(t('plan.saveFailed'));
    }
  };

  const changeStatus = async (plan: ProjectPlan, status: PlanStatus) => {
    try {
      await apiClient.put(`/projects/${project.id}/plans/${plan.id}`, { status });
      setPlans((prev) => prev.map((p) => (p.id === plan.id ? { ...p, status } : p)));
    } catch {
      message.error(t('plan.saveFailed'));
    }
  };

  const deletePlan = async (plan: ProjectPlan) => {
    try {
      await apiClient.delete(`/projects/${project.id}/plans/${plan.id}`);
      setPlans((prev) => prev.filter((p) => p.id !== plan.id));
      message.success(t('plan.deleteSuccess'));
    } catch {
      message.error(t('plan.saveFailed'));
    }
  };

  const memberOptions = members.map((m) => ({
    value: m.researcher_id,
    label: m.display_name || m.username || m.researcher_id.slice(0, 8),
  }));

  const formatRange = (plan: ProjectPlan) => {
    if (!plan.start_date && !plan.due_date) return null;
    return `${plan.start_date ?? '…'} → ${plan.due_date ?? '…'}`;
  };

  return (
    <SectionCard
      title={t('projectHome.plansTitle')}
      extra={(
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          {t('plan.new')}
        </Button>
      )}
    >
      <Spin spinning={loading}>
        <List
          dataSource={plans}
          locale={{ emptyText: <Empty description={t('plan.empty')} /> }}
          renderItem={(plan) => (
            <List.Item
              actions={[
                <Select
                  key="status"
                  size="small"
                  value={plan.status}
                  disabled={!canChangeStatus(plan)}
                  style={{ width: 120 }}
                  onChange={(value) => changeStatus(plan, value as PlanStatus)}
                  options={(['todo', 'in_progress', 'done'] as PlanStatus[]).map((s) => ({
                    value: s,
                    label: t(`plan.status.${s}`),
                  }))}
                />,
                ...(canEditPlan(plan)
                  ? [
                      <Button
                        key="edit"
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        aria-label={t('common.edit')}
                        onClick={() => openEdit(plan)}
                      />,
                      <Popconfirm
                        key="delete"
                        title={t('plan.deleteConfirm')}
                        onConfirm={() => deletePlan(plan)}
                      >
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label={t('common.delete')} />
                      </Popconfirm>,
                    ]
                  : []),
              ]}
            >
              <List.Item.Meta
                title={(
                  <Space size={8} wrap>
                    <span>{plan.title}</span>
                    <Tag color={PRIORITY_COLORS[plan.priority]}>{t(`plan.priority.${plan.priority}`)}</Tag>
                    <Tag color={STATUS_COLORS[plan.status]}>{t(`plan.status.${plan.status}`)}</Tag>
                    {plan.tags.map((tag) => (
                      <Tag key={tag}>{tag}</Tag>
                    ))}
                  </Space>
                )}
                description={(
                  <Space orientation="vertical" size={2}>
                    {plan.content ? <Text type="secondary">{plan.content}</Text> : null}
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {[
                        formatRange(plan),
                        plan.assignee_name
                          ? t('plan.assigneeLabel', { name: plan.assignee_name })
                          : null,
                        plan.creator_name
                          ? t('plan.creatorLabel', { name: plan.creator_name })
                          : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </Text>
                  </Space>
                )}
              />
            </List.Item>
          )}
        />
      </Spin>

      <Modal
        title={t(editingPlan ? 'plan.editTitle' : 'plan.new')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={submitForm}>
          <Form.Item name="title" label={t('plan.title')} rules={[{ required: true }]}>
            <Input maxLength={200} autoFocus />
          </Form.Item>
          <Form.Item name="content" label={t('plan.content')}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Space size={16} style={{ display: 'flex' }}>
            <Form.Item name="start_date" label={t('plan.startDate')} style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="due_date" label={t('plan.dueDate')} style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Space size={16} style={{ display: 'flex' }}>
            <Form.Item name="priority" label={t('plan.priorityLabel')} style={{ flex: 1 }}>
              <Select
                options={(['low', 'medium', 'high'] as PlanPriority[]).map((p) => ({
                  value: p,
                  label: t(`plan.priority.${p}`),
                }))}
              />
            </Form.Item>
            <Form.Item name="assignee_id" label={t('plan.assignee')} style={{ flex: 1 }}>
              <Select allowClear showSearch optionFilterProp="label" options={memberOptions} />
            </Form.Item>
          </Space>
          <Form.Item name="tags" label={t('plan.tags')}>
            <Select mode="tags" open={false} placeholder={t('plan.tagsPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </SectionCard>
  );
}
