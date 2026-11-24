import {
  DeleteOutlined,
  EditOutlined,
  MessageOutlined,
  PlusOutlined,
  PushpinOutlined,
} from '@ant-design/icons';
import {
  Button,
  Empty,
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
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import SectionCard from '../ui/SectionCard';
import TaskCard from '../tasks/TaskCard';
import { useAuth } from '../../hooks/useAuth';
import apiClient from '../../services/api-client';
import type { Project, ProjectSession } from '../../types/project';
import type { TaskDefinition } from '../../types/task';
import { localizeTask } from '../../utils/localize-task';

const { Text } = Typography;

const TASK_DRAFT_STORAGE_PREFIX = 'task-draft:';

interface TicketOption {
  id: string;
  short_key: string;
  title: string;
  stage_category: string;
}

interface ProjectTasksTabProps {
  project: Project;
  onOpenTicket?: (ticketId: string) => void;
  onPrecipitated?: () => void;
}

export default function ProjectTasksTab({
  project,
  onOpenTicket,
  onPrecipitated,
}: ProjectTasksTabProps) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [availableTasks, setAvailableTasks] = useState<TaskDefinition[]>([]);
  const [tasksLoading, setTasksLoading] = useState(true);
  const [creatingSession, setCreatingSession] = useState(false);
  const [renamingSession, setRenamingSession] = useState<ProjectSession | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [precipitatingSession, setPrecipitatingSession] = useState<ProjectSession | null>(null);
  const [ticketOptions, setTicketOptions] = useState<TicketOption[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | undefined>(undefined);
  const [precipitateSummary, setPrecipitateSummary] = useState('');
  const [precipitating, setPrecipitating] = useState(false);

  const fetchSessions = () => {
    setSessionsLoading(true);
    apiClient
      .get('/sessions', { params: { project_id: project.id, include_empty: true } })
      .then((r) => setSessions(r.data))
      .finally(() => setSessionsLoading(false));
  };

  useEffect(fetchSessions, [project.id]);

  useEffect(() => {
    let cancelled = false;
    setTasksLoading(true);
    apiClient
      .get<TaskDefinition[]>('/tasks', { params: { project_id: project.id } })
      .then((r) => {
        if (!cancelled) setAvailableTasks(r.data);
      })
      .catch(() => {
        if (!cancelled) message.error(t('task.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setTasksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [project.id, t]);

  // Recommended tasks are driven by the project's linked task selection
  // (project.task_ids), editable in the settings panel. Unknown or disabled
  // ids are skipped; selection order is preserved.
  const recommendedTasks = (project.task_ids ?? [])
    .map((taskId) => availableTasks.find((task) => task.id === taskId))
    .filter((task): task is TaskDefinition => task !== undefined);

  const createSession = async () => {
    setCreatingSession(true);
    try {
      const { data } = await apiClient.post('/sessions', { project_id: project.id });
      navigate(`/sessions/${data.id}`);
    } finally {
      setCreatingSession(false);
    }
  };

  const startTask = async (taskId: string) => {
    const task = recommendedTasks.find((item) => item.id === taskId);
    if (!task) {
      message.warning(t('task.noAvailableTasksHint'));
      return;
    }
    const draftStorageKey = `${TASK_DRAFT_STORAGE_PREFIX}${project.id}:${taskId}`;
    sessionStorage.removeItem(draftStorageKey);
    try {
      const { data: session } = await apiClient.post<ProjectSession>('/sessions', {
        project_id: project.id,
        task_id: taskId,
        title: localizeTask(task, i18n).name,
      });
      navigate(`/sessions/${session.id}`, {
        state: { draftStorageKey, hasDraft: false },
      });
    } catch {
      message.error(t('task.workspaceRunFailed'));
    }
  };

  const renameSession = async () => {
    if (!renamingSession || !renameValue.trim()) return;
    await apiClient.put(`/sessions/${renamingSession.id}`, { title: renameValue.trim() });
    setSessions((prev) =>
      prev.map((s) => (s.id === renamingSession.id ? { ...s, title: renameValue.trim() } : s))
    );
    setRenamingSession(null);
  };

  const deleteSession = async (sessionId: string) => {
    try {
      await apiClient.delete(`/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      message.success(t('session.deleted'));
    } catch {
      message.error(t('session.deleteFailed'));
    }
  };

  const openPrecipitateModal = async (session: ProjectSession) => {
    setPrecipitatingSession(session);
    setSelectedTicketId(session.ticket_id ?? undefined);
    setPrecipitateSummary('');
    try {
      const res = await apiClient.get<TicketOption[]>(
        `/projects/${project.id}/tickets`
      );
      const list = Array.isArray(res.data) ? res.data : [];
      setTicketOptions(list);
      if (!session.ticket_id && list.length > 0) {
        setSelectedTicketId(list[0].id);
      }
    } catch {
      message.error(t('superagent.loadFailed'));
    }
  };

  const submitPrecipitate = async () => {
    if (!precipitatingSession || !selectedTicketId) return;
    setPrecipitating(true);
    try {
      await apiClient.post(
        `/projects/${project.id}/tickets/${selectedTicketId}/precipitate-session`,
        {
          session_id: precipitatingSession.id,
          summary: precipitateSummary.trim() || null,
          create_research_object: true,
        }
      );
      message.success(t('superagent.precipitateSuccess'));
      setPrecipitatingSession(null);
      onPrecipitated?.();
    } catch {
      message.error(t('superagent.actionFailed'));
    } finally {
      setPrecipitating(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <SectionCard
        title={t('session.title')}
        extra={(
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={creatingSession}
            onClick={createSession}
          >
            {t('session.new')}
          </Button>
        )}
      >
        <Spin spinning={sessionsLoading}>
          <List
            dataSource={sessions}
            locale={{ emptyText: sessionsLoading ? null : <Empty description={t('home.noProjectSessions')} /> }}
            renderItem={(session) => {
              // owner_id is null on older payloads; treat unknown as own.
              const isOwn = !session.owner_id || session.owner_id === user?.id;
              return (
              <List.Item
                style={{ cursor: 'pointer' }}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/sessions/${session.id}`)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    navigate(`/sessions/${session.id}`);
                  }
                }}
                actions={[
                  <Button
                    key="precipitate"
                    type="text"
                    size="small"
                    icon={<PushpinOutlined />}
                    onClick={(e) => {
                      e.stopPropagation();
                      void openPrecipitateModal(session);
                    }}
                  >
                    {t('superagent.precipitateToTicketBtn')}
                  </Button>,
                  ...(isOwn ? [
                    <Button
                      key="rename"
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      aria-label={t('session.rename')}
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingSession(session);
                        setRenameValue(session.title || '');
                      }}
                    />,
                    <Popconfirm
                      key="delete"
                      title={t('session.deleteConfirm')}
                      description={t('session.deleteMemoryPreserved')}
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        return deleteSession(session.id);
                      }}
                      onCancel={(e) => e?.stopPropagation()}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        aria-label={t('common.delete')}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ] : []),
                ]}
              >
                <List.Item.Meta
                  avatar={<MessageOutlined />}
                  title={(
                    <Space size={8} wrap>
                      <span style={{ fontSize: 14, fontWeight: 500 }}>
                        {session.title || `Session ${session.id.slice(0, 8)}`}
                      </span>
                      {session.stage_category && (
                        <Tag bordered={false}>{t(`superagent.stages.${session.stage_category}`)}</Tag>
                      )}
                      {session.ticket_id && onOpenTicket && (
                        <Button
                          type="link"
                          size="small"
                          style={{ padding: 0, height: 'auto', fontSize: 12 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenTicket(session.ticket_id!);
                          }}
                        >
                          {t('superagent.viewTicketBtn')}
                        </Button>
                      )}
                    </Space>
                  )}
                  description={[
                    t('session.messageCount', { count: session.message_count }),
                    !isOwn && session.owner_name
                      ? t('session.createdBy', { name: session.owner_name })
                      : null,
                  ].filter(Boolean).join(' · ')}
                />
              </List.Item>
              );
            }}
          />
        </Spin>
      </SectionCard>

      <SectionCard title={t('task.recommendedTitle')}>
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          {t('task.recommendedDescriptionLinked', { project: project.name })}
        </Typography.Paragraph>
        <Spin spinning={tasksLoading}>
          {recommendedTasks.length > 0 ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: 12,
              }}
            >
              {recommendedTasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={localizeTask(task, i18n)}
                  onStart={(item) => { void startTask(item.id); }}
                  startLabel={t('task.useTask')}
                  globalLabel={t('task.scopeGlobal')}
                  projectLabel={t('task.scopeProject')}
                  materialsLabel={t('task.cardProjectMaterials')}
                  memoryLabel={t('task.cardResearchMemory')}
                  saveLabel={t('task.cardStructuredResult')}
                  platformRuntimeLabel={t('task.modeWorkflow')}
                  codexRuntimeLabel={t('task.modeCodex')}
                />
              ))}
            </div>
          ) : !tasksLoading ? (
            <Text type="secondary">{t('task.emptyLinked')}</Text>
          ) : null}
        </Spin>
      </SectionCard>

      <Modal
        title={t('session.renameTitle')}
        open={!!renamingSession}
        onCancel={() => setRenamingSession(null)}
        onOk={renameSession}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={renameSession}
          maxLength={500}
        />
      </Modal>

      <Modal
        title={t('superagent.precipitateModalTitle')}
        open={!!precipitatingSession}
        onCancel={() => setPrecipitatingSession(null)}
        onOk={submitPrecipitate}
        confirmLoading={precipitating}
        okButtonProps={{ disabled: !selectedTicketId }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <div>
            <Text strong style={{ display: 'block', marginBottom: 6 }}>
              {t('superagent.precipitateSelectTicket')}
            </Text>
            <Select
              style={{ width: '100%' }}
              value={selectedTicketId}
              onChange={(val) => setSelectedTicketId(val)}
              options={ticketOptions.map((tk) => ({
                value: tk.id,
                label: `${tk.short_key} — ${tk.title}`,
              }))}
            />
          </div>
          <Input.TextArea
            rows={4}
            value={precipitateSummary}
            onChange={(e) => setPrecipitateSummary(e.target.value)}
            placeholder={t('superagent.precipitateSummaryPlaceholder')}
          />
        </Space>
      </Modal>
    </div>
  );
}
