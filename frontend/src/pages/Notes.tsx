import { DeleteOutlined } from '@ant-design/icons';
import { Button, Card, List, Popconfirm } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../services/api-client';

interface Note {
  id: string;
  content: string;
  created_at: string;
}

export default function Notes() {
  const { t } = useTranslation();
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadNotes = () => {
    setLoading(true);
    apiClient.get('/notes')
      .then((r) => setNotes(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(loadNotes, []);

  const deleteNote = async (id: string) => {
    setDeletingId(id);
    try {
      await apiClient.delete(`/notes/${id}`);
      loadNotes();
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card title={t('nav.notes')}>
        <List
          loading={loading}
          dataSource={notes}
          renderItem={(note) => (
            <List.Item
              actions={[
                <Popconfirm
                  key="delete"
                  title={t('common.confirm')}
                  onConfirm={() => deleteNote(note.id)}
                >
                  <Button
                    icon={<DeleteOutlined />}
                    danger
                    size="small"
                    loading={deletingId === note.id}
                    aria-label={t('common.delete')}
                  />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                description={note.content.slice(0, 200)}
                title={new Date(note.created_at).toLocaleString()}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
