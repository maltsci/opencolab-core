import { BellOutlined, ClockCircleOutlined, DashboardOutlined, EditOutlined, HomeOutlined, FolderOutlined, SettingOutlined, LogoutOutlined, GlobalOutlined, KeyOutlined, CheckSquareOutlined, MenuOutlined, UserOutlined, ReadOutlined, RobotOutlined, TeamOutlined, ExperimentOutlined } from '@ant-design/icons';
import { Alert, Badge, Button, ConfigProvider, Drawer, Dropdown, Form, Grid, Input, Layout, Menu, Modal, Select, Spin, message, theme } from 'antd';
import enUS from 'antd/locale/en_US';
import zhCN from 'antd/locale/zh_CN';
import { useEffect, useState } from 'react';
import { Navigate, Route, BrowserRouter as Router, Routes, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ROLE_ADMIN, ROLE_PI } from './constants/roles';
import { KNOWLEDGE_INBOX_UPDATED_EVENT } from './constants/knowledge-inbox';
import { useAuth } from './hooks/useAuth';
import apiClient from './services/api-client';
import { themeConfig } from './theme';
import NotificationBell from './components/NotificationBell';
import type { KnowledgeInbox as KnowledgeInboxResponse } from './types/knowledge-suggestion';
import Home from './pages/Home';
import Library from './pages/Library';
import Login from './pages/Login';
import KnowledgeAssistant from './pages/KnowledgeAssistant';
import KnowledgeGovernance from './pages/KnowledgeGovernance';
import KnowledgeHealth from './pages/KnowledgeHealth';
import ResourceMaintenance from './pages/ResourceMaintenance';
import Research from './pages/Research';
import ProjectAssets from './pages/ProjectAssets';
import ProjectHome from './pages/ProjectHome';
import ProjectMemory from './pages/ProjectMemory';
import People from './pages/People';
import ResourcePreview from './pages/ResourcePreview';
import SessionPage from './pages/Session';
import TaskWorkspace from './pages/TaskWorkspace';
import TrainingHome from './pages/TrainingHome';
import TrainingCourses from './pages/TrainingCourses';
import TrainingLearningPath from './pages/TrainingLearningPath';
import TrainingModuleLearning from './pages/TrainingModuleLearning';
import TrainingReport from './pages/TrainingReport';
import LLMKeysAdmin from './pages/admin/LLMKeys';
import SettingsAdmin from './pages/admin/Settings';
import SkillPacksAdmin from './pages/admin/SkillPacks';
import TasksAdmin from './pages/admin/Tasks';
import UsersAdmin from './pages/admin/Users';

const { Header, Content } = Layout;

interface KnowledgeReviewCapability {
  can_review: boolean;
}

function AppLayout() {
  const { t, i18n } = useTranslation();
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [needsSetup, setNeedsSetup] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [showDisplayName, setShowDisplayName] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [canReviewKnowledge, setCanReviewKnowledge] = useState<boolean | null>(null);
  const [pendingKnowledgeReviewCount, setPendingKnowledgeReviewCount] = useState(0);
  const [pwForm] = Form.useForm();
  const [dnForm] = Form.useForm();
  const screens = Grid.useBreakpoint();
  const { token } = theme.useToken();
  const isMobile = !screens.md;
  const hasAdministrativeReviewAccess = user?.role === ROLE_ADMIN || user?.role === ROLE_PI;

  useEffect(() => {
    if (user?.role === ROLE_ADMIN) {
      apiClient.get('/admin/config/setup-status').then((r) => {
        if (!r.data.setup_complete) {
          setNeedsSetup(true);
        }
      }).catch(() => {});
    }
  }, [user]);

  useEffect(() => {
    let active = true;

    if (!user) {
      setCanReviewKnowledge(null);
      return () => {
        active = false;
      };
    }

    if (hasAdministrativeReviewAccess) {
      setCanReviewKnowledge(true);
      return () => {
        active = false;
      };
    }

    apiClient.get<KnowledgeReviewCapability>('/knowledge-governance/review-capability')
      .then((response) => {
        if (active) setCanReviewKnowledge(response.data.can_review);
      })
      .catch(() => {
        if (active) setCanReviewKnowledge(false);
      });

    return () => {
      active = false;
    };
  }, [hasAdministrativeReviewAccess, user]);

  useEffect(() => {
    let active = true;

    if (!user) {
      setPendingKnowledgeReviewCount(0);
      return () => {
        active = false;
      };
    }

    const loadKnowledgeInboxCount = () => {
      apiClient.get<KnowledgeInboxResponse>('/knowledge-governance/inbox')
        .then((response) => {
          if (active) {
            setPendingKnowledgeReviewCount(
              response.data.review_items.length + response.data.unread_decision_count,
            );
          }
        })
        .catch(() => {
          if (active) setPendingKnowledgeReviewCount(0);
        });
    };

    loadKnowledgeInboxCount();
    window.addEventListener(KNOWLEDGE_INBOX_UPDATED_EVENT, loadKnowledgeInboxCount);

    return () => {
      active = false;
      window.removeEventListener(KNOWLEDGE_INBOX_UPDATED_EVENT, loadKnowledgeInboxCount);
    };
  }, [location.pathname, user]);

  if (isLoading) {
    return <Spin size="large" style={{ display: 'block', margin: '200px auto' }} />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const menuItems = [
    { key: '/', icon: <HomeOutlined />, label: t('nav.home') },
    { key: '/assistant', icon: <RobotOutlined />, label: t('nav.assistant') },
    { key: '/people', icon: <TeamOutlined />, label: t('nav.people') },
    { key: '/research', icon: <ReadOutlined />, label: t('nav.research') },
    { key: '/library', icon: <FolderOutlined />, label: t('nav.library') },
    { key: '/maintenance', icon: <ClockCircleOutlined />, label: t('nav.maintenance') },
    {
      key: '/knowledge-governance',
      icon: <BellOutlined />,
      label: (
        <Badge count={pendingKnowledgeReviewCount} size="small" offset={[8, 0]}>
          <span style={{ color: token.colorTextLightSolid }}>{t('nav.knowledgeGovernance')}</span>
        </Badge>
      ),
    },
    { key: '/training', icon: <ExperimentOutlined />, label: t('nav.training') },
    ...(user?.role === ROLE_ADMIN || user?.role === ROLE_PI
      ? [{
          key: 'admin',
          icon: <SettingOutlined />,
          label: t('nav.admin'),
          children: [
            { key: '/admin/users', label: t('admin.users') },
            { key: '/knowledge-health', icon: <DashboardOutlined />, label: t('nav.knowledgeHealth') },
            ...(user?.role === ROLE_ADMIN ? [
              { key: '/admin/skill-packs', label: t('admin.skillPacks') },
              { key: '/admin/tasks', icon: <CheckSquareOutlined />, label: t('admin.tasks') },
              { key: '/admin/llm-keys', label: t('admin.llm-profiles') },
              { key: '/admin/settings', label: t('admin.settings') },
            ] : []),
          ],
        }]
      : []),
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 24, padding: isMobile ? '0 16px' : undefined }}>
        {isMobile && (
          <Button
            type="text"
            icon={<MenuOutlined />}
            aria-label={t('nav.menu')}
            onClick={() => setNavOpen(true)}
            style={{ color: token.colorTextLightSolid }}
          />
        )}
        <Button
          type="text"
          onClick={() => navigate('/')}
          style={{ color: token.colorTextLightSolid, fontSize: 18, fontWeight: 'bold', whiteSpace: 'nowrap' }}
        >
          {t('app.title')}
        </Button>
        {isMobile ? (
          <div style={{ flex: 1, minWidth: 0 }} />
        ) : (
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ flex: 1, minWidth: 0 }}
          />
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, whiteSpace: 'nowrap' }}>
          {user ? <NotificationBell key={user.id} userId={user.id} /> : null}
          <Select
            size="small"
            value={i18n.language}
            onChange={(lang) => {
              i18n.changeLanguage(lang);
              localStorage.setItem('lang', lang);
            }}
            options={[
              { value: 'en-US', label: 'EN' },
              { value: 'zh-CN', label: 'CN' },
            ]}
            style={{ width: 70 }}
            suffixIcon={<GlobalOutlined style={{ color: token.colorTextLightSolid }} />}
          />
          <Dropdown
            menu={{
              items: [
                {
                  key: 'my-profile',
                  icon: <TeamOutlined />,
                  label: t('people.openMyProfile'),
                  onClick: () => {
                    if (user?.id) navigate(`/people?person=${encodeURIComponent(user.id)}`);
                  },
                },
                {
                  key: 'display-name',
                  icon: <EditOutlined />,
                  label: t('auth.displayName'),
                  onClick: () => {
                    dnForm.setFieldsValue({ display_name: user?.display_name || '' });
                    setShowDisplayName(true);
                  },
                },
                {
                  key: 'change-password',
                  icon: <KeyOutlined />,
                  label: t('auth.change-password'),
                  onClick: () => {
                    pwForm.resetFields();
                    setShowChangePassword(true);
                  },
                },
              ],
            }}
            trigger={['click']}
          >
            <Button
              type="text"
              aria-label={user?.display_name || user?.username}
              style={{ color: token.colorTextLightSolid }}
            >
              {isMobile ? <UserOutlined /> : (user?.display_name || user?.username)}
            </Button>
          </Dropdown>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            aria-label={t('auth.logout')}
            onClick={async () => {
              await logout();
              navigate('/login');
            }}
            style={{ color: token.colorTextLightSolid }}
          />
        </div>
      </Header>

      <Drawer
        placement="left"
        size={260}
        open={navOpen}
        onClose={() => setNavOpen(false)}
        title={t('app.title')}
      >
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => {
            setNavOpen(false);
            navigate(key);
          }}
          style={{ borderInlineEnd: 'none' }}
        />
      </Drawer>

      <Content>
        {needsSetup && location.pathname !== '/admin/settings' && (
          <Alert
            message={t('admin.setupTitle')}
            description={t('admin.setupRequired')}
            type="warning"
            showIcon
            closable
            banner
            action={
              <Button type="link" onClick={() => navigate('/admin/settings')} style={{ whiteSpace: 'nowrap' }}>
                {t('admin.settings')}
              </Button>
            }
            style={{ marginBottom: 0 }}
          />
        )}
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/assistant" element={<KnowledgeAssistant />} />
          <Route path="/people" element={<People />} />
          <Route path="/research" element={<Research />} />
          <Route path="/library" element={<Library />} />
          <Route path="/resources/:assetId" element={<ResourcePreview />} />
    <Route path="/maintenance" element={<ResourceMaintenance />} />
          <Route path="/knowledge-governance" element={
            canReviewKnowledge === null
              ? <Spin size="large" style={{ display: 'block', margin: '200px auto' }} />
              : <KnowledgeGovernance canReview={canReviewKnowledge} />
          } />
          <Route path="/knowledge-inbox" element={<Navigate to="/knowledge-governance?tab=inbox" replace />} />
          <Route path="/knowledge-health" element={
            hasAdministrativeReviewAccess ? <KnowledgeHealth /> : <Navigate to="/" replace />
          } />
          <Route path="/knowledge-suggestions" element={<Navigate to="/knowledge-governance?tab=suggestions" replace />} />
          <Route path="/knowledge-review" element={<Navigate to="/knowledge-governance?tab=review" replace />} />
    <Route path="/training" element={<TrainingHome />} />
          <Route path="/training/courses" element={user?.role === ROLE_ADMIN || user?.role === ROLE_PI ? <TrainingCourses /> : <Navigate to="/training" replace />} />
          <Route path="/training/reports/:traineeId" element={user?.role === ROLE_ADMIN || user?.role === ROLE_PI ? <TrainingReport /> : <Navigate to="/training" replace />} />
    <Route path="/training/assignments/:assignmentId" element={<TrainingLearningPath />} />
    <Route path="/training/module-assignments/:assignmentId" element={<TrainingModuleLearning />} />
          <Route path="/projects/:projectId" element={<ProjectHome />} />
          <Route path="/projects/:projectId/assets" element={<ProjectAssets />} />
          <Route path="/projects/:projectId/memory" element={<ProjectMemory />} />
          <Route path="/projects/:projectId/tasks/:taskId" element={<TaskWorkspace />} />
          <Route path="/sessions/:sessionId" element={<SessionPage />} />
          <Route path="/sources" element={<Navigate to="/library" replace />} />
          <Route path="/admin/users" element={<UsersAdmin />} />
          <Route path="/admin/skill-packs" element={<SkillPacksAdmin />} />
          <Route path="/admin/tasks" element={<TasksAdmin />} />
          <Route path="/admin/llm-keys" element={<LLMKeysAdmin />} />
          <Route path="/admin/settings" element={<SettingsAdmin />} />
        </Routes>
      </Content>

      <Modal
        title={t('auth.change-password')}
        open={showChangePassword}
        onCancel={() => setShowChangePassword(false)}
        onOk={() => pwForm.submit()}
      >
        <Form
          form={pwForm}
          layout="vertical"
          onFinish={async (values: { current_password: string; new_password: string }) => {
            try {
              await apiClient.put('/auth/me/password', values);
              message.success(t('auth.change-password-success'));
              setShowChangePassword(false);
            } catch {
              message.error(t('auth.password-incorrect'));
            }
          }}
        >
          <Form.Item name="current_password" label={t('auth.current-password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="new_password" label={t('admin.new-password')} rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label={t('auth.confirm-password')}
            dependencies={['new_password']}
            rules={[
              { required: true },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                  return Promise.reject(new Error(t('auth.password-mismatch')));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('auth.displayName')}
        open={showDisplayName}
        onCancel={() => setShowDisplayName(false)}
        onOk={() => dnForm.submit()}
        destroyOnHidden
      >
        <Form
          form={dnForm}
          layout="vertical"
          onFinish={async (values: { display_name: string }) => {
            try {
              await apiClient.patch('/auth/me', { display_name: values.display_name });
              message.success(t('common.save'));
              setShowDisplayName(false);
              // Refresh user data
              window.location.reload();
            } catch {
              message.error(t('share.error'));
            }
          }}
        >
          <Form.Item name="display_name" label={t('auth.displayName')}>
            <Input placeholder={t('auth.displayNamePlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  );
}

export default function App() {
  const { i18n } = useTranslation();
  return (
    <ConfigProvider theme={themeConfig} locale={i18n.language.startsWith('zh') ? zhCN : enUS}>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<AppLayout />} />
        </Routes>
      </Router>
    </ConfigProvider>
  );
}
