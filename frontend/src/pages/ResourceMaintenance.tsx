import { ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Card, List, Skeleton, Space, Tag, Typography, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { formatDateTime } from '../components/library/library-utils';
import PageContainer from '../components/library/PageContainer';
import EmptyState from '../components/ui/EmptyState';
import apiClient from '../services/api-client';
import type { MemberProfileMaintenanceItem } from '../types/person';
import type { ResourceMaintenanceItem } from '../types/research-asset';
import type { DirectionMaintenanceItem } from '../types/research-direction';

export default function ResourceMaintenance() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [resourceItems, setResourceItems] = useState<ResourceMaintenanceItem[]>([]);
  const [directionItems, setDirectionItems] = useState<DirectionMaintenanceItem[]>([]);
  const [profileItems, setProfileItems] = useState<MemberProfileMaintenanceItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const [resourcesResponse, directionsResponse, profilesResponse] = await Promise.all([
        apiClient.get<ResourceMaintenanceItem[]>('/research-assets/maintenance'),
        apiClient.get<DirectionMaintenanceItem[]>('/research-directions/maintenance'),
        apiClient.get<MemberProfileMaintenanceItem[]>('/people/maintenance'),
      ]);
      setResourceItems(resourcesResponse.data);
      setDirectionItems(directionsResponse.data);
      setProfileItems(profilesResponse.data);
    } catch {
      message.error(t('resourceMaintenance.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const hasItems = resourceItems.length > 0 || directionItems.length > 0 || profileItems.length > 0;

  return (
    <PageContainer title={t('resourceMaintenance.title')} description={t('resourceMaintenance.description')}>
      {loading ? (
        <Card>
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Skeleton active paragraph={{ rows: 2 }} />
            <Skeleton active paragraph={{ rows: 2 }} />
          </Space>
        </Card>
      ) : !hasItems ? (
        <Card
          extra={(
            <Button icon={<ReloadOutlined />} onClick={() => void loadItems()}>
              {t('resourceMaintenance.refresh')}
            </Button>
          )}
        >
          <EmptyState
            icon={<ClockCircleOutlined />}
            title={t('resourceMaintenance.emptyTitle')}
            description={t('resourceMaintenance.emptyDescription')}
          />
        </Card>
      ) : (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          {profileItems.length > 0 && (
            <Card title={t('resourceMaintenance.profilePending')}>
              <List
                dataSource={profileItems}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open-profile"
                        type="link"
                        onClick={() => navigate(`/people?person=${encodeURIComponent(item.user_id)}`)}
                      >
                        {t('resourceMaintenance.openProfile')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={(
                        <Space size={8} wrap>
                          <Typography.Text strong>
                            {item.display_name || t('resourceMaintenance.myProfile')}
                          </Typography.Text>
                          <Tag color={item.issue === 'review_overdue' ? 'warning' : 'blue'}>
                            {t(`resourceMaintenance.profileIssue.${item.issue}`)}
                          </Tag>
                        </Space>
                      )}
                      description={(
                        <Space orientation="vertical" size={2}>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.lastConfirmed', {
                              time: item.last_confirmed_at
                                ? formatDateTime(item.last_confirmed_at, i18n.language)
                                : t('resourceMaintenance.notConfirmed'),
                            })}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.reviewDue', {
                              time: item.review_due_at
                                ? formatDateTime(item.review_due_at, i18n.language)
                                : t('resourceMaintenance.notScheduled'),
                            })}
                          </Typography.Text>
                        </Space>
                      )}
                    />
                  </List.Item>
                )}
              />
            </Card>
          )}
          <Card
            title={t('resourceMaintenance.resourcesPending', { count: resourceItems.length })}
            extra={(
              <Button icon={<ReloadOutlined />} onClick={() => void loadItems()}>
                {t('resourceMaintenance.refresh')}
              </Button>
            )}
          >
            {resourceItems.length === 0 ? (
              <Typography.Text type="secondary">
                {t('resourceMaintenance.resourcesEmpty')}
              </Typography.Text>
            ) : (
              <List
                dataSource={resourceItems}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open-resource"
                        type="link"
                        onClick={() => navigate(`/library?asset=${encodeURIComponent(item.asset_id)}`)}
                      >
                        {t('resourceMaintenance.openResource')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={(
                        <Space size={8} wrap>
                          <Typography.Text strong>{item.title}</Typography.Text>
                          <Tag color={item.issue === 'review_overdue' ? 'warning' : 'blue'}>
                            {t(`resourceMaintenance.issue.${item.issue}`)}
                          </Tag>
                        </Space>
                      )}
                      description={(
                        <Space orientation="vertical" size={2}>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.lastConfirmed', {
                              time: item.last_confirmed_at
                                ? formatDateTime(item.last_confirmed_at, i18n.language)
                                : t('resourceMaintenance.notConfirmed'),
                            })}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.reviewDue', {
                              time: item.review_due_at
                                ? formatDateTime(item.review_due_at, i18n.language)
                                : t('resourceMaintenance.notScheduled'),
                            })}
                          </Typography.Text>
                        </Space>
                      )}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
          <Card
            title={t('resourceMaintenance.directionsPending', { count: directionItems.length })}
          >
            {directionItems.length === 0 ? (
              <Typography.Text type="secondary">
                {t('resourceMaintenance.directionsEmpty')}
              </Typography.Text>
            ) : (
              <List
                dataSource={directionItems}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button
                        key="open-direction"
                        type="link"
                        onClick={() => navigate(`/research?direction=${encodeURIComponent(item.direction_id)}`)}
                      >
                        {t('resourceMaintenance.openDirection')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={(
                        <Space size={8} wrap>
                          <Typography.Text strong>{item.name}</Typography.Text>
                          <Tag color={item.issue === 'review_overdue' ? 'warning' : 'blue'}>
                            {t(`resourceMaintenance.directionIssue.${item.issue}`)}
                          </Tag>
                        </Space>
                      )}
                      description={(
                        <Space orientation="vertical" size={2}>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.lastConfirmed', {
                              time: item.last_confirmed_at
                                ? formatDateTime(item.last_confirmed_at, i18n.language)
                                : t('resourceMaintenance.notConfirmed'),
                            })}
                          </Typography.Text>
                          <Typography.Text type="secondary">
                            {t('resourceMaintenance.reviewDue', {
                              time: item.review_due_at
                                ? formatDateTime(item.review_due_at, i18n.language)
                                : t('resourceMaintenance.notScheduled'),
                            })}
                          </Typography.Text>
                        </Space>
                      )}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Space>
      )}
    </PageContainer>
  );
}
