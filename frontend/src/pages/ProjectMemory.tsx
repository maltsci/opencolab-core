import {
  ArrowLeftOutlined,
  DatabaseOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { formatDateTime } from '../components/library/library-utils';
import PageContainer from '../components/library/PageContainer';
import type { SessionResearchObject } from '../components/research/types';
import apiClient from '../services/api-client';

const { Paragraph, Text, Title } = Typography;

interface ProjectInfo {
  id: string;
  name: string;
  description: string | null;
}

function getMemoryPreview(item: SessionResearchObject): string {
  const content = item.content?.trim();
  if (content) {
    return content;
  }

  const raw = item.content_json?.raw_synthesis;
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim();
  }

  const overview = item.content_json?.overview;
  if (typeof overview === 'string' && overview.trim()) {
    return overview.trim();
  }

  return '';
}

export default function ProjectMemory() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [items, setItems] = useState<SessionResearchObject[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    if (!projectId) {
      setLoadError(true);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setLoadError(false);

    Promise.all([
      apiClient.get<ProjectInfo>(`/projects/${projectId}`),
      apiClient.get<SessionResearchObject[]>(`/research-objects/projects/${projectId}`),
    ])
      .then(([projectResponse, memoryResponse]) => {
        if (cancelled) return;
        setProject(projectResponse.data);
        setItems(memoryResponse.data);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadError(true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const groupedItems = useMemo(() => {
    const hypotheses = items.filter((item) => item.type === 'hypothesis');
    const discussions = items.filter((item) => item.type !== 'hypothesis');
    return { hypotheses, discussions };
  }, [items]);

  const formatTime = (value: string) => formatDateTime(value, i18n.language);

  const renderMemoryCard = (item: SessionResearchObject) => {
    const sourceSessionDeleted = item.content_json?.source_session_deleted === true;
    const preview = getMemoryPreview(item);

    return (
      <Card key={item.id} size="small" style={{ borderRadius: 8 }}>
        <Space orientation="vertical" size={8} style={{ width: '100%' }}>
          <Space size={8} wrap>
            <Tag color={item.type === 'hypothesis' ? 'purple' : 'blue'}>
              {item.type === 'hypothesis' ? t('memory.typeHypothesis') : t('memory.typeDiscussion')}
            </Tag>
            <Text type="secondary">{formatTime(item.created_at)}</Text>
            {sourceSessionDeleted ? (
              <Tag>{t('memory.sourceSessionDeleted')}</Tag>
            ) : item.session_id ? (
              <Button
                type="link"
                size="small"
                icon={<MessageOutlined />}
                onClick={() => navigate(`/sessions/${item.session_id}`)}
                style={{ padding: 0, height: 'auto' }}
              >
                {t('memory.openSourceSession')}
              </Button>
            ) : null}
          </Space>
          <Title level={5} style={{ margin: 0 }}>
            {item.title || t('memory.untitled')}
          </Title>
          {preview ? (
            <Paragraph
              style={{ margin: 0, whiteSpace: 'pre-wrap' }}
              ellipsis={{ rows: 4, expandable: true, symbol: t('common.expand') }}
            >
              {preview}
            </Paragraph>
          ) : (
            <Text type="secondary">{t('memory.emptyContent')}</Text>
          )}
        </Space>
      </Card>
    );
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '120px auto' }} />;
  }

  if (loadError || !project) {
    return (
      <div style={{ padding: 24 }}>
        <Alert
          type="error"
          showIcon
          message={t('memory.projectLoadFailed')}
          action={(
            <Button onClick={() => navigate('/')}>
              {t('common.back')}
            </Button>
          )}
        />
      </div>
    );
  }

  return (
    <PageContainer
      title={t('memory.projectMemory')}
      extra={(
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          {t('common.back')}
        </Button>
      )}
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Card>
          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
            <Space size={8} wrap>
              <Tag icon={<DatabaseOutlined />} color="blue">
                {t('memory.projectMemory')}
              </Tag>
              <Tag>{t('memory.totalCount', { count: items.length })}</Tag>
            </Space>
            <Title level={3} style={{ margin: 0 }}>{project.name}</Title>
            <Paragraph type="secondary" style={{ margin: 0 }}>
              {project.description || t('memory.projectMemoryDescription')}
            </Paragraph>
          </Space>
        </Card>

        {items.length === 0 ? (
          <Card>
            <Empty description={t('memory.projectEmpty')} />
          </Card>
        ) : (
          <div style={{ display: 'grid', gap: 16 }}>
            {groupedItems.hypotheses.length > 0 ? (
              <Card title={t('memory.hypothesesTitle')}>
                <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                  {groupedItems.hypotheses.map(renderMemoryCard)}
                </Space>
              </Card>
            ) : null}

            {groupedItems.discussions.length > 0 ? (
              <Card title={t('memory.discussionsTitle')}>
                <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                  {groupedItems.discussions.map(renderMemoryCard)}
                </Space>
              </Card>
            ) : null}
          </div>
        )}
      </Space>
    </PageContainer>
  );
}
