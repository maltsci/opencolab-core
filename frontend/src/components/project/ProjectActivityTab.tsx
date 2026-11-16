import {
  BulbOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FileAddOutlined,
  FileDoneOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  MessageOutlined,
  RocketOutlined,
  SaveOutlined,
  ScheduleOutlined,
  TeamOutlined,
  UserAddOutlined,
  UserDeleteOutlined,
} from '@ant-design/icons';
import { Avatar, Button, Card, Empty, List, Spin, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import SectionCard from '../ui/SectionCard';
import apiClient from '../../services/api-client';
import type { Project, ProjectActivity } from '../../types/project';

const { Text } = Typography;

const ACTION_ICONS: Record<string, ReactNode> = {
  project_created: <FileAddOutlined />,
  member_added: <UserAddOutlined />,
  member_removed: <UserDeleteOutlined />,
  session_created: <MessageOutlined />,
  asset_uploaded: <FolderAddOutlined />,
  asset_generated: <FileDoneOutlined />,
  asset_linked: <FolderOpenOutlined />,
  asset_removed: <FolderOpenOutlined />,
  memory_saved: <SaveOutlined />,
  plan_created: <ScheduleOutlined />,
  plan_assigned: <TeamOutlined />,
  plan_status_changed: <FileDoneOutlined />,
  question_defined: <BulbOutlined />,
  ticket_created: <RocketOutlined />,
  attention_requested: <ClockCircleOutlined />,
  attention_answered: <CheckCircleOutlined />,
  deliverable_ready: <FileDoneOutlined />,
  ticket_merged: <CheckCircleOutlined />,
  next_round_spawned: <ExperimentOutlined />,
  wetlab_uploaded: <ExperimentOutlined />,
  manuscript_exported: <DownloadOutlined />,
  session_precipitated: <MessageOutlined />,
};

interface ProjectActivityTabProps {
  project: Project;
  compact?: boolean;
  refreshKey?: number;
  onSelectTicket?: (ticketId: string) => void;
}

export default function ProjectActivityTab({
  project,
  compact = false,
  refreshKey = 0,
  onSelectTicket,
}: ProjectActivityTabProps) {
  const { t, i18n } = useTranslation();
  const [activities, setActivities] = useState<ProjectActivity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiClient
      .get(`/projects/${project.id}/activities`, {
        params: { limit: compact ? 30 : 100 },
      })
      .then((r) => setActivities(r.data))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [project.id, compact, refreshKey]);

  const listNode = (
    <Spin spinning={loading}>
      <List
        size={compact ? 'small' : 'default'}
        dataSource={activities}
        locale={{ emptyText: <Empty description={t('projectHome.activityEmpty')} /> }}
        renderItem={(activity) => {
          const isTicketLink =
            activity.target_type === 'research_ticket' &&
            !!activity.target_id &&
            !!onSelectTicket;
          return (
            <List.Item
              style={
                compact
                  ? { padding: '8px 0', alignItems: 'flex-start' }
                  : undefined
              }
            >
              <List.Item.Meta
                avatar={
                  <Avatar
                    size={compact ? 'small' : 'default'}
                    icon={ACTION_ICONS[activity.action] ?? <ClockCircleOutlined />}
                  />
                }
                title={(
                  <div style={{ fontSize: compact ? 13 : 14, lineHeight: 1.45, fontWeight: 500 }}>
                    {t(`activity.${activity.action}`, {
                      actor: activity.actor_name ?? t('activity.unknownActor'),
                      target: activity.target_title ?? '',
                    })}
                  </div>
                )}
                description={(
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 6,
                      marginTop: 4,
                    }}
                  >
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {new Date(activity.created_at).toLocaleString(i18n.language)}
                    </Text>
                    {isTicketLink && activity.target_id && (
                      <Button
                        type="link"
                        size="small"
                        style={{ padding: 0, height: 'auto', fontSize: 12 }}
                        onClick={() => onSelectTicket(activity.target_id!)}
                      >
                        {t('superagent.viewTicketBtn')}
                      </Button>
                    )}
                  </div>
                )}
              />
            </List.Item>
          );
        }}
      />
    </Spin>
  );

  if (compact) {
    return (
      <Card
        size="small"
        title={t('superagent.timelineTitle')}
        styles={{ body: { maxHeight: 680, overflowY: 'auto', padding: '8px 12px' } }}
      >
        {listNode}
      </Card>
    );
  }

  return <SectionCard title={t('projectHome.activityTitle')}>{listNode}</SectionCard>;
}
