import { ArrowLeftOutlined, DatabaseOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Result, Space, Spin, Tabs, Tag, theme } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import ProjectActivityTab from '../components/project/ProjectActivityTab';
import ProjectConfigPanel from '../components/project/ProjectConfigPanel';
import ProjectPlansTab from '../components/project/ProjectPlansTab';
import ProjectTasksTab from '../components/project/ProjectTasksTab';
import ProjectAssets from './ProjectAssets';
import { ROLES_PRIVILEGED } from '../constants/roles';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import type { Project } from '../types/project';

const VALID_TABS = ['tasks', 'activity', 'plans', 'assets'];

export default function ProjectHome() {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { user } = useAuth();
  const navigate = useNavigate();
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const tabParam = searchParams.get('tab');
  const activeTab = tabParam && VALID_TABS.includes(tabParam) ? tabParam : 'tasks';

  const fetchProject = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    apiClient
      .get<Project>(`/projects/${projectId}`)
      .then((r) => setProject(r.data))
      .catch((err: unknown) => {
        if ((err as { response?: { status?: number } })?.response?.status === 404) {
          setNotFound(true);
        }
      })
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(fetchProject, [fetchProject]);

  if (notFound) {
    return (
      <Result
        status="404"
        title={t('projectHome.notFound')}
        extra={(
          <Button type="primary" onClick={() => navigate('/')}>
            {t('common.back')}
          </Button>
        )}
      />
    );
  }

  if (loading || !project) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 120 }}>
        <Spin size="large" />
      </div>
    );
  }

  const isPrivileged = !!user && ROLES_PRIVILEGED.includes(user.role);
  const canManage = isPrivileged || project.is_owner;

  return (
    <PageContainer
      title={project.name}
      extra={(
        <Space>
          {project.archived && <Tag>{t('project.archived')}</Tag>}
          <Button
            icon={<DatabaseOutlined />}
            onClick={() => navigate(`/projects/${project.id}/memory`)}
          >
            {t('memory.projectMemory')}
          </Button>
          <Button
            icon={<RobotOutlined />}
            onClick={() => navigate(`/assistant?project=${encodeURIComponent(project.id)}`)}
          >
            {t('projectHome.openAssistant')}
          </Button>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
            {t('projectHome.backToProjects')}
          </Button>
        </Space>
      )}
    >
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '1.8 1 520px', minWidth: 0, overflow: 'hidden' }}>
          <Tabs
            activeKey={activeTab}
            onChange={(key) => setSearchParams({ tab: key }, { replace: true })}
            items={[
              {
                key: 'tasks',
                label: t('projectHome.tabSessions'),
                children: <ProjectTasksTab project={project} />,
              },
              {
                key: 'activity',
                label: t('projectHome.tabActivity'),
                children: <ProjectActivityTab project={project} />,
              },
              {
                key: 'plans',
                label: t('projectHome.tabPlans'),
                children: <ProjectPlansTab project={project} canManage={canManage} />,
              },
              {
                key: 'assets',
                label: t('projectHome.tabAssets'),
                children: <ProjectAssets embedded />,
              },
            ]}
          />
        </div>
        <div
          style={{
            flex: '1 1 320px',
            minWidth: 280,
            maxWidth: 420,
            borderLeft: `1px solid ${token.colorBorderSecondary}`,
            paddingLeft: 24,
          }}
        >
          <ProjectConfigPanel
            project={project}
            canManage={canManage}
            onProjectUpdated={setProject}
          />
        </div>
      </div>
    </PageContainer>
  );
}
