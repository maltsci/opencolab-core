import {
  DeleteOutlined,
  EditOutlined,
  MessageOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Empty, Input, List, message, Modal, Popconfirm, Spin, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import SectionCard from '../ui/SectionCard';
import TaskCard from '../tasks/TaskCard';
import { useAuth } from '../../hooks/useAuth';
import apiClient from '../../services/api-client';
import type { Project, ProjectSession } from '../../types/project';
import type { TaskDefinition } from '../../types/task';

const { Text } = Typography;

const TASK_DRAFT_STORAGE_PREFIX = 'task-draft:';

interface ProjectTasksTabProps {
  project: Project;
}

export default function ProjectTasksTab({ project }: ProjectTasksTabProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [availableTasks, setAvailableTasks] = useState<TaskDefinition[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [renamingSession, setRenamingSession] = useState<ProjectSession | null>(null);
  const [renameValue, setRenameValue] = useState('');

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
        title: task.name,
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
            locale={{ emptyText: <Empty description={t('home.noProjectSessions')} /> }}
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
                actions={isOwn ? [
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
                ] : []}
              >
                <List.Item.Meta
                  avatar={<MessageOutlined />}
                  title={session.title || `Session ${session.id.slice(0, 8)}`}
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
                  task={task}
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
          ) : (
            <Text type="secondary">{t('task.emptyLinked')}</Text>
          )}
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
    </div>
  );
}
