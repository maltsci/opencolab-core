import {
  ClockCircleOutlined,
  FileAddOutlined,
  FileDoneOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  MessageOutlined,
  SaveOutlined,
  ScheduleOutlined,
  TeamOutlined,
  UserAddOutlined,
  UserDeleteOutlined,
} from '@ant-design/icons';
import { Avatar, Empty, List, Spin, Typography } from 'antd';
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
};

interface ProjectActivityTabProps {
  project: Project;
}

export default function ProjectActivityTab({ project }: ProjectActivityTabProps) {
  const { t, i18n } = useTranslation();
  const [activities, setActivities] = useState<ProjectActivity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiClient
      .get(`/projects/${project.id}/activities`, { params: { limit: 100 } })
      .then((r) => setActivities(r.data))
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [project.id]);

  return (
    <SectionCard title={t('projectHome.activityTitle')}>
      <Spin spinning={loading}>
        <List
          dataSource={activities}
          locale={{ emptyText: <Empty description={t('projectHome.activityEmpty')} /> }}
          renderItem={(activity) => (
            <List.Item>
              <List.Item.Meta
                avatar={<Avatar icon={ACTION_ICONS[activity.action] ?? <ClockCircleOutlined />} />}
                title={t(`activity.${activity.action}`, {
                  actor: activity.actor_name ?? t('activity.unknownActor'),
                  target: activity.target_title ?? '',
                })}
                description={(
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(activity.created_at).toLocaleString(i18n.language)}
                  </Text>
                )}
              />
            </List.Item>
          )}
        />
      </Spin>
    </SectionCard>
  );
}
