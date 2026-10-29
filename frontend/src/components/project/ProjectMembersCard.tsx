import { PlusOutlined, UserDeleteOutlined } from '@ant-design/icons';
import { Button, List, message, Popconfirm, Select, Spin, Tag } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import apiClient from '../../services/api-client';
import type { Project, ProjectMember, UserOption } from '../../types/project';

interface ProjectMembersCardProps {
  project: Project;
  canManage: boolean;
  onChanged?: () => void;
}

export default function ProjectMembersCard({ project, canManage, onChanged }: ProjectMembersCardProps) {
  const { t } = useTranslation();
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [allUsers, setAllUsers] = useState<UserOption[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchMembers = () =>
    apiClient.get(`/projects/${project.id}/members`).then((r) => setMembers(r.data));

  useEffect(() => {
    setLoading(true);
    fetchMembers()
      .catch(() => message.error(t('project.membersLoadFailed')))
      .finally(() => setLoading(false));
    if (canManage) {
      apiClient.get('/auth/users').then((r) => setAllUsers(r.data)).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, canManage]);

  const addMember = async () => {
    if (!selectedUserId) return;
    try {
      await apiClient.post(`/projects/${project.id}/members`, {
        researcher_id: selectedUserId,
        role: 'member',
      });
      setSelectedUserId(null);
      await fetchMembers();
      onChanged?.();
      message.success(t('project.memberAdded'));
    } catch {
      message.error(t('project.memberAddFailed'));
    }
  };

  const removeMember = async (researcherId: string) => {
    await apiClient.delete(`/projects/${project.id}/members/${researcherId}`);
    setMembers((prev) => prev.filter((m) => m.researcher_id !== researcherId));
    onChanged?.();
    message.success(t('project.memberRemoved'));
  };

  const makeProjectOwner = async (researcherId: string) => {
    await apiClient.put(`/projects/${project.id}/members/${researcherId}`, { role: 'owner' });
    await fetchMembers();
    onChanged?.();
    message.success(t('project.ownerUpdated'));
  };

  return (
    <Spin spinning={loading}>
      {canManage && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <Select
            style={{ flex: 1 }}
            placeholder={t('project.selectUser')}
            value={selectedUserId}
            onChange={setSelectedUserId}
            showSearch
            optionFilterProp="label"
            options={allUsers
              .filter((u) => !members.some((m) => m.researcher_id === u.id))
              .map((u) => ({
                value: u.id,
                label: u.display_name ? `${u.display_name} (${u.username})` : u.username,
              }))}
          />
          <Button type="primary" icon={<PlusOutlined />} disabled={!selectedUserId} onClick={addMember}>
            {t('project.addMember')}
          </Button>
        </div>
      )}
      <List
        size="small"
        dataSource={members}
        locale={{ emptyText: t('project.noMembers') }}
        renderItem={(member) => (
          <List.Item
            actions={
              member.role !== 'owner' && canManage
                ? [
                    <Popconfirm
                      key="owner"
                      title={t('project.setOwnerConfirm')}
                      onConfirm={() => makeProjectOwner(member.researcher_id)}
                    >
                      <Button type="link" size="small">{t('project.setOwner')}</Button>
                    </Popconfirm>,
                    <Popconfirm
                      key="remove"
                      title={t('project.removeMemberConfirm')}
                      onConfirm={() => removeMember(member.researcher_id)}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<UserDeleteOutlined />}
                        aria-label={t('project.removeMember', 'Remove member')}
                      />
                    </Popconfirm>,
                  ]
                : []
            }
          >
            <List.Item.Meta
              title={(
                <span>
                  {member.display_name || member.username || member.researcher_id.slice(0, 8)}
                  {member.role === 'owner' && (
                    <Tag color="blue" style={{ marginLeft: 8 }}>{t('project.owner')}</Tag>
                  )}
                </span>
              )}
              // Hide the username line when it would just repeat the display name.
              description={member.display_name && member.display_name !== member.username ? member.username : undefined}
            />
          </List.Item>
        )}
      />
    </Spin>
  );
}
