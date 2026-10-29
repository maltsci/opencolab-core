import { BellOutlined } from '@ant-design/icons';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, Badge, Button, Divider, Drawer, Empty, Space, Spin, Typography, message, theme } from 'antd';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import apiClient from '../services/api-client';

interface NotificationItem {
  id: string;
  kind: string;
  access_request_id: string | null;
  read_at: string | null;
  created_at: string;
}

interface NotificationPage {
  items: NotificationItem[];
  unread_count: number;
  next_cursor: string | null;
}

export default function NotificationBell({ userId }: { userId: string }) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [marking, setMarking] = useState(false);
  const queryKey = ['notifications', userId];
  const inbox = useInfiniteQuery({
    queryKey,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => (await apiClient.get<NotificationPage>('/notifications', {
      params: { cursor: pageParam, limit: 20 },
    })).data,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
  const unread = inbox.data?.pages[0]?.unread_count ?? 0;
  const items = inbox.data?.pages.flatMap((page) => page.items) ?? [];

  const markRead = async (item?: NotificationItem) => {
    setMarking(true);
    try {
      await apiClient.post(item ? `/notifications/${item.id}/read` : '/notifications/read-all');
      await queryClient.invalidateQueries({ queryKey });
      return true;
    } catch {
      message.error(t('notifications.updateFailed'));
      return false;
    } finally {
      setMarking(false);
    }
  };

  const visit = async (item: NotificationItem) => {
    if (!item.read_at && !await markRead(item)) return;
    const tab = item.kind === 'access_request_pending' ? 'pending-requests' : 'my-requests';
    setOpen(false);
    navigate(`/library?tab=${tab}&request=${encodeURIComponent(item.access_request_id ?? '')}`);
  };

  return (
    <>
      <Badge count={unread} size="small">
        <Button
          type="text" icon={<BellOutlined />} aria-label={t('notifications.title')}
          style={{ color: token.colorTextLightSolid }}
          onClick={() => { setOpen(true); void inbox.refetch(); }}
        />
      </Badge>
      <Drawer title={t('notifications.title')} open={open} onClose={() => setOpen(false)} size={400}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Text>{t('notifications.unreadCount', { count: unread })}</Typography.Text>
          <Button disabled={!unread} loading={marking} onClick={() => void markRead()}>
            {t('notifications.markAllRead')}
          </Button>
        </Space>
        <Divider />
        {inbox.isError ? (
          <Alert type="error" title={t('notifications.loadFailed')} action={
            <Button onClick={() => void inbox.refetch()}>{t('common.retry')}</Button>
          } />
        ) : null}
        {inbox.isPending ? <Spin /> : items.length === 0 && !inbox.isError ? (
          <Empty description={t('notifications.empty')} />
        ) : null}
        {items.map((item) => (
          <div key={item.id} style={{ padding: '12px 0', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Badge dot={!item.read_at} offset={[4, 4]}>
              <Typography.Text strong={!item.read_at}>{t(`notifications.kind.${item.kind}`)}</Typography.Text>
            </Badge>
            <Typography.Paragraph type="secondary" style={{ margin: '8px 0' }}>
              {t(`notifications.description.${item.kind}`)}
            </Typography.Paragraph>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Typography.Text type="secondary">
                {new Date(item.created_at).toLocaleString(i18n.language)}
              </Typography.Text>
              <Button type="link" disabled={marking} onClick={() => void visit(item)}>
                {t(item.kind === 'access_request_pending' ? 'notifications.review' : 'notifications.viewResult')}
              </Button>
            </Space>
          </div>
        ))}
        {inbox.hasNextPage ? (
          <Button block loading={inbox.isFetchingNextPage} onClick={() => void inbox.fetchNextPage()} style={{ marginTop: 16 }}>
            {t('notifications.loadMore')}
          </Button>
        ) : null}
      </Drawer>
    </>
  );
}
