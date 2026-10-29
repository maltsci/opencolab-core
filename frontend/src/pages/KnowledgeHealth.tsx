import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Card, List, Skeleton, Space, Statistic, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import apiClient from '../services/api-client';
import type { KnowledgeHealth as KnowledgeHealthResponse } from '../types/knowledge-health';

interface HealthRow {
  key: keyof KnowledgeHealthResponse;
  action: 'openPeople' | 'openOwnMaintenance' | 'openReview';
  path: string;
}

const healthRows: HealthRow[] = [
  { key: 'member_profile_review_count', action: 'openPeople', path: '/people' },
  { key: 'direction_review_count', action: 'openOwnMaintenance', path: '/maintenance' },
  { key: 'resource_review_count', action: 'openOwnMaintenance', path: '/maintenance' },
  { key: 'pending_suggestion_count', action: 'openReview', path: '/knowledge-review' },
];

export default function KnowledgeHealth() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [health, setHealth] = useState<KnowledgeHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<KnowledgeHealthResponse>('/knowledge-governance/health');
      setHealth(data);
    } catch {
      message.error(t('knowledgeHealth.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  return (
    <PageContainer
      title={t('knowledgeHealth.title')}
      description={t('knowledgeHealth.description')}
      extra={(
        <Button icon={<ReloadOutlined />} onClick={() => void loadHealth()}>
          {t('knowledgeHealth.refresh')}
        </Button>
      )}
    >
      <Alert
        type="info"
        showIcon
        message={t('knowledgeHealth.scopeTitle')}
        description={t('knowledgeHealth.scopeDescription')}
        style={{ marginBottom: 16 }}
      />
      <Card>
        {loading ? (
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Skeleton active paragraph={{ rows: 2 }} />
            <Skeleton active paragraph={{ rows: 2 }} />
          </Space>
        ) : health ? (
          <List
            dataSource={healthRows}
            renderItem={(row) => (
              <List.Item
                actions={[
                  <Button key={row.action} type="link" onClick={() => navigate(row.path)}>
                    {t(`knowledgeHealth.${row.action}`)}
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={<Typography.Text strong>{t(`knowledgeHealth.item.${row.key}`)}</Typography.Text>}
                  description={t(`knowledgeHealth.itemDescription.${row.key}`)}
                />
                <Statistic value={health[row.key]} valueStyle={{ fontSize: 24, minWidth: 44, textAlign: 'right' }} />
              </List.Item>
            )}
          />
        ) : null}
      </Card>
    </PageContainer>
  );
}
