import { EditOutlined, RobotOutlined, SearchOutlined, StopOutlined, TeamOutlined, UserAddOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Descriptions, Divider, Drawer, Form, Input, List, Popconfirm, Select, Skeleton, Space, Spin, Switch, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import { formatDateTime } from '../components/library/library-utils';
import EmptyState from '../components/ui/EmptyState';
import { ROLE_ADMIN, ROLE_PI } from '../constants/roles';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import type {
  MemberProfileUpdateInput,
  PersonDetail,
  PersonDirectoryEntry,
  PersonRecentWorkResponse,
  PersonResponsibility,
  ResearchDirectionOption,
} from '../types/person';

interface ProfileFormValues {
  bio?: string;
  consultation_topics?: string[];
  show_recent_activity?: boolean;
  last_confirmed_at?: string;
  review_due_at?: string;
}

interface DirectionFormValues {
  direction_id: string;
  role: 'lead' | 'contributor' | 'advisor';
}

interface ResearchGroupOption {
  id: string;
  name: string;
}

function toLocalDateTimeValue(value: string | null): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function People() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedPersonId = searchParams.get('person');
  const directorySearch = searchParams.get('search')?.trim() || '';
  const { user } = useAuth();
  const [people, setPeople] = useState<PersonDirectoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState(directorySearch);
  const [researchGroups, setResearchGroups] = useState<ResearchGroupOption[]>([]);
  const [groupId, setGroupId] = useState<string>();
  const [includeArchived, setIncludeArchived] = useState(false);
  const [roleFilter, setRoleFilter] = useState<string>();
  const [directionId, setDirectionId] = useState<string>();
  const [consultationTopic, setConsultationTopic] = useState<string>();
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<PersonDetail | null>(null);
  const [recentWork, setRecentWork] = useState<PersonRecentWorkResponse | null>(null);
  const [recentWorkLoading, setRecentWorkLoading] = useState(false);
  const [responsibilities, setResponsibilities] = useState<PersonResponsibility[] | null>(null);
  const [responsibilitiesLoading, setResponsibilitiesLoading] = useState(false);
  const [representativeResources, setRepresentativeResources] = useState<PersonResponsibility[] | null>(null);
  const [representativeResourcesLoading, setRepresentativeResourcesLoading] = useState(false);
  const [representativeResourceOptions, setRepresentativeResourceOptions] = useState<PersonResponsibility[]>([]);
  const [editingRepresentativeResources, setEditingRepresentativeResources] = useState(false);
  const [representativeResourceIds, setRepresentativeResourceIds] = useState<string[]>([]);
  const [savingRepresentativeResources, setSavingRepresentativeResources] = useState(false);
  const [editingProfile, setEditingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [assigningDirection, setAssigningDirection] = useState(false);
  const [savingDirection, setSavingDirection] = useState(false);
  const [endingDirectionId, setEndingDirectionId] = useState<string | null>(null);
  const [updatingArchive, setUpdatingArchive] = useState(false);
  const [directions, setDirections] = useState<ResearchDirectionOption[]>([]);
  const [profileForm] = Form.useForm<ProfileFormValues>();
  const [directionForm] = Form.useForm<DirectionFormValues>();
  const canManageDirections = user?.role === ROLE_ADMIN || user?.role === ROLE_PI;

  const loadPeople = async (
    selectedGroupId = groupId,
    showArchived = includeArchived,
  ) => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<PersonDirectoryEntry[]>('/people', {
        params: {
          group_id: selectedGroupId,
          include_archived: showArchived || undefined,
        },
      });
      setPeople(data);
    } catch {
      message.error(t('people.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPeople(groupId, includeArchived);
  }, [includeArchived]);

  useEffect(() => {
    setQuery(directorySearch);
  }, [directorySearch]);

  useEffect(() => {
    apiClient.get<ResearchGroupOption[]>('/research-groups')
      .then((response) => setResearchGroups(response.data))
      .catch(() => setResearchGroups([]));
  }, []);

  useEffect(() => {
    apiClient.get<{ items: ResearchDirectionOption[] }>('/research-directions', {
      params: { status: 'active', limit: 100 },
    })
      .then((response) => setDirections(response.data.items))
      .catch(() => setDirections([]));
  }, []);

  const loadRecentWork = async (personId: string) => {
    setRecentWorkLoading(true);
    try {
      const { data } = await apiClient.get<PersonRecentWorkResponse>(`/people/${personId}/activities`);
      setRecentWork(data);
    } catch {
      setRecentWork(null);
    } finally {
      setRecentWorkLoading(false);
    }
  };

  const loadResponsibilities = async (personId: string) => {
    setResponsibilitiesLoading(true);
    try {
      const { data } = await apiClient.get<PersonResponsibility[]>(`/people/${personId}/resources`);
      setResponsibilities(data);
    } catch {
      setResponsibilities(null);
    } finally {
      setResponsibilitiesLoading(false);
    }
  };

  const loadRepresentativeResources = async (personId: string) => {
    setRepresentativeResourcesLoading(true);
    try {
      const { data } = await apiClient.get<PersonResponsibility[]>(`/people/${personId}/representative-resources`);
      setRepresentativeResources(data);
    } catch {
      setRepresentativeResources(null);
    } finally {
      setRepresentativeResourcesLoading(false);
    }
  };

  const filteredPeople = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return people.filter((person) => {
      const matchesQuery = [
        person.display_name,
        person.username,
        person.bio,
        ...person.consultation_topics,
        ...person.current_directions.map((direction) => direction.name),
      ].some((value) => !normalizedQuery || value?.toLocaleLowerCase().includes(normalizedQuery));
      const matchesRole = !roleFilter || person.role === roleFilter;
      const matchesDirection = !directionId || person.current_directions.some(
        (direction) => direction.id === directionId,
      );
      const matchesConsultationTopic = !consultationTopic
        || person.consultation_topics.includes(consultationTopic);
      return matchesQuery && matchesRole && matchesDirection && matchesConsultationTopic;
    });
  }, [consultationTopic, directionId, people, query, roleFilter]);

  const directionOptions = useMemo(() => {
    const directionsById = new Map<string, string>();
    people.forEach((person) => person.current_directions.forEach((direction) => {
      directionsById.set(direction.id, direction.name);
    }));
    return [...directionsById].map(([id, name]) => ({ value: id, label: name }));
  }, [people]);

  const consultationTopicOptions = useMemo(() => (
    [...new Set(people.flatMap((person) => person.consultation_topics))]
      .map((topic) => ({ value: topic, label: topic }))
  ), [people]);

  const hasDirectoryFilters = Boolean(
    query.trim() || groupId || roleFilter || directionId || consultationTopic,
  );

  const clearDirectoryFilters = () => {
    setQuery('');
    setGroupId(undefined);
    setRoleFilter(undefined);
    setDirectionId(undefined);
    setConsultationTopic(undefined);
    void loadPeople(undefined, includeArchived);
  };

  const openPerson = async (person: PersonDirectoryEntry) => {
    setDetailOpen(true);
    setDetail(null);
    setRecentWork(null);
    setResponsibilities(null);
    setRepresentativeResources(null);
    setEditingRepresentativeResources(false);
    setEditingProfile(false);
    setAssigningDirection(false);
    setDetailLoading(true);
    void loadRecentWork(person.id);
    void loadResponsibilities(person.id);
    void loadRepresentativeResources(person.id);
    try {
      const { data } = await apiClient.get<PersonDetail>(`/people/${person.id}`, {
        params: { include_archived: includeArchived || undefined },
      });
      setDetail(data);
    } catch {
      message.error(t('people.detailLoadFailed'));
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedPersonId) return;
    setDetailOpen(true);
    setDetail(null);
    setRecentWork(null);
    setResponsibilities(null);
    setRepresentativeResources(null);
    setEditingRepresentativeResources(false);
    setDetailLoading(true);
    void loadRecentWork(selectedPersonId);
    void loadResponsibilities(selectedPersonId);
    void loadRepresentativeResources(selectedPersonId);
    apiClient.get<PersonDetail>(`/people/${selectedPersonId}`, {
      params: { include_archived: includeArchived || undefined },
    })
      .then((response) => setDetail(response.data))
      .catch(() => {
        message.error(t('people.detailLoadFailed'));
        setDetailOpen(false);
      })
      .finally(() => setDetailLoading(false));
  }, [includeArchived, selectedPersonId]);

  const canEditProfile = detail?.id === user?.id;

  const openProfileEditor = () => {
    if (!detail) return;
    profileForm.setFieldsValue({
      bio: detail.bio || undefined,
      consultation_topics: detail.consultation_topics,
      show_recent_activity: detail.show_recent_activity,
      last_confirmed_at: toLocalDateTimeValue(detail.last_confirmed_at),
      review_due_at: toLocalDateTimeValue(detail.review_due_at),
    });
    setEditingProfile(true);
  };

  const saveProfile = async () => {
    const values = await profileForm.validateFields();
    const payload: MemberProfileUpdateInput = {
      bio: values.bio?.trim() || null,
      consultation_topics: values.consultation_topics || [],
      show_recent_activity: values.show_recent_activity ?? true,
      last_confirmed_at: values.last_confirmed_at
        ? new Date(values.last_confirmed_at).toISOString()
        : null,
      review_due_at: values.review_due_at
        ? new Date(values.review_due_at).toISOString()
        : null,
    };
    setSavingProfile(true);
    try {
      const { data } = await apiClient.patch('/people/me/profile', payload);
      setDetail((current) => current ? { ...current, ...data } : current);
      if (detail) {
        void loadRecentWork(detail.id);
      }
      setEditingProfile(false);
      await loadPeople();
      message.success(t('people.profileSaveSuccess'));
    } catch {
      message.error(t('people.profileSaveFailed'));
    } finally {
      setSavingProfile(false);
    }
  };

  const openDirectionAssignment = async () => {
    directionForm.setFieldsValue({ role: 'contributor', direction_id: undefined });
    setAssigningDirection(true);
    try {
      const { data } = await apiClient.get<{ items: ResearchDirectionOption[] }>('/research-directions', {
        params: { status: 'active', limit: 100 },
      });
      setDirections(data.items);
    } catch {
      setDirections([]);
      message.error(t('people.directionsLoadFailed'));
    }
  };

  const openRepresentativeResourcesEditor = async () => {
    if (!detail) return;
    try {
      const { data } = await apiClient.get<PersonResponsibility[]>(
        `/people/${detail.id}/representative-resource-options`,
      );
      setRepresentativeResourceOptions(data);
      setRepresentativeResourceIds(representativeResources?.map((resource) => resource.asset_id) || []);
      setEditingRepresentativeResources(true);
    } catch {
      setRepresentativeResourceOptions([]);
      message.error(t('people.representativeResourcesLoadFailed'));
    }
  };

  const saveRepresentativeResources = async () => {
    if (!detail) return;
    setSavingRepresentativeResources(true);
    try {
      const { data } = await apiClient.put<PersonResponsibility[]>(
        `/people/${detail.id}/representative-resources`,
        { asset_ids: representativeResourceIds },
      );
      setRepresentativeResources(data);
      setEditingRepresentativeResources(false);
      message.success(t('people.representativeResourcesSaveSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('people.representativeResourcesSaveFailed'));
    } finally {
      setSavingRepresentativeResources(false);
    }
  };

  const assignDirection = async () => {
    if (!detail) return;
    const values = await directionForm.validateFields();
    setSavingDirection(true);
    try {
      await apiClient.post(`/people/${detail.id}/directions`, values);
      const { data } = await apiClient.get<PersonDetail>(`/people/${detail.id}`);
      setDetail(data);
      setAssigningDirection(false);
      await loadPeople();
      message.success(t('people.directionAssignSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('people.directionAssignFailed'));
    } finally {
      setSavingDirection(false);
    }
  };

  const endDirection = async (memberDirectionId: string) => {
    if (!detail) return;
    setEndingDirectionId(memberDirectionId);
    try {
      const { data } = await apiClient.post(
        `/people/${detail.id}/directions/${memberDirectionId}/end`,
      );
      setDetail((current) => current ? {
        ...current,
        current_directions: current.current_directions.filter((direction) => (
          !current.direction_history.some((history) => (
            history.member_direction_id === memberDirectionId && history.id === direction.id
          ))
        )),
        direction_history: current.direction_history.map((history) => (
          history.member_direction_id === memberDirectionId ? { ...history, valid_until: data.valid_until } : history
        )),
      } : current);
      await loadPeople();
      message.success(t('people.directionEndSuccess'));
    } catch {
      message.error(t('people.directionEndFailed'));
    } finally {
      setEndingDirectionId(null);
    }
  };

  const updateArchiveStatus = async (action: 'archive' | 'restore') => {
    if (!detail) return;
    setUpdatingArchive(true);
    try {
      await apiClient.post(`/people/${detail.id}/${action}`);
      setDetailOpen(false);
      await loadPeople(groupId, includeArchived);
      message.success(t(action === 'archive' ? 'people.archiveSuccess' : 'people.restoreSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t(action === 'archive' ? 'people.archiveFailed' : 'people.restoreFailed'));
    } finally {
      setUpdatingArchive(false);
    }
  };

  const availableDirections = directions.filter((direction) => !detail?.current_directions.some(
    (current) => current.id === direction.id,
  ));

  return (
    <PageContainer title={t('people.title')} description={t('people.description')}>
      <Card styles={{ body: { padding: 16 } }}>
        <Input
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          prefix={<SearchOutlined />}
          placeholder={t('people.searchPlaceholder')}
          aria-label={t('people.searchPlaceholder')}
        />
        <Space wrap size={[8, 8]} style={{ marginTop: 12 }}>
          <Typography.Text type="secondary">{t('people.filters')}</Typography.Text>
          <Select
            allowClear
            value={groupId}
            onChange={(value) => {
              const nextGroupId = value || undefined;
              setGroupId(nextGroupId);
              void loadPeople(nextGroupId);
            }}
            placeholder={t('people.filterGroup')}
            options={researchGroups.map((group) => ({ value: group.id, label: group.name }))}
            style={{ minWidth: 160 }}
          />
          {canManageDirections ? (
            <Space size={4}>
              <Typography.Text type="secondary">{t('people.includeArchived')}</Typography.Text>
              <Switch
                checked={includeArchived}
                onChange={setIncludeArchived}
                aria-label={t('people.includeArchived')}
              />
            </Space>
          ) : null}
          <Select
            allowClear
            value={roleFilter}
            onChange={setRoleFilter}
            placeholder={t('people.filterRole')}
            options={[
              { value: 'admin', label: t('people.role.admin') },
              { value: 'pi', label: t('people.role.pi') },
              { value: 'researcher', label: t('people.role.researcher') },
            ]}
            style={{ minWidth: 130 }}
          />
          <Select
            allowClear
            value={directionId}
            onChange={setDirectionId}
            placeholder={t('people.filterDirection')}
            options={directionOptions}
            style={{ minWidth: 160 }}
          />
          <Select
            allowClear
            value={consultationTopic}
            onChange={setConsultationTopic}
            placeholder={t('people.filterConsultationTopic')}
            options={consultationTopicOptions}
            style={{ minWidth: 180 }}
          />
          {hasDirectoryFilters ? (
            <Button type="link" onClick={clearDirectoryFilters}>{t('people.clearFilters')}</Button>
          ) : null}
        </Space>
      </Card>

      <Card style={{ marginTop: 16 }} styles={{ body: { padding: loading || filteredPeople.length === 0 ? 32 : 0 } }}>
        {loading ? (
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Skeleton active paragraph={{ rows: 2 }} />
            <Skeleton active paragraph={{ rows: 2 }} />
          </Space>
        ) : filteredPeople.length === 0 ? (
          <EmptyState
            icon={<TeamOutlined />}
            title={hasDirectoryFilters ? t('people.searchEmptyTitle') : t('people.emptyTitle')}
            description={hasDirectoryFilters ? t('people.searchEmptyDescription') : t('people.emptyDescription')}
          />
        ) : (
          <List
            dataSource={filteredPeople}
            renderItem={(person) => (
              <List.Item style={{ padding: '18px 20px' }}>
                <List.Item.Meta
                  title={(
                    <Space size={8} wrap>
                      <Typography.Link onClick={() => void openPerson(person)}>
                        {person.display_name || person.username}
                      </Typography.Link>
                      <Tag>{t(`people.role.${person.role}`)}</Tag>
                      {person.archived_at ? <Tag color="default">{t('people.archived')}</Tag> : null}
                    </Space>
                  )}
                  description={(
                    <Space orientation="vertical" size={4}>
                      <Typography.Text type="secondary">{person.bio || t('people.bioEmpty')}</Typography.Text>
                      {person.current_directions.length > 0 ? (
                        <Space size={[4, 4]} wrap>
                          {person.current_directions.map((direction) => (
                            <Tag color="blue" key={direction.id}>
                              <Button
                                type="link"
                                size="small"
                                onClick={() => navigate(`/research?direction=${encodeURIComponent(direction.id)}`)}
                                style={{ height: 'auto', padding: 0 }}
                              >
                                {direction.name}
                              </Button>
                            </Tag>
                          ))}
                        </Space>
                      ) : null}
                    </Space>
                  )}
                />
                <Button type="link" onClick={() => void openPerson(person)}>{t('people.viewProfile')}</Button>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Drawer
        title={detail ? (detail.display_name || detail.username) : t('people.profileTitle')}
        width={600}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        extra={detail ? (
          <Space>
            <Button
              icon={<RobotOutlined />}
              onClick={() => navigate(`/assistant?context=person&query=${encodeURIComponent(detail.display_name || detail.username)}`)}
            >
              {t('assistant.continueExploring')}
            </Button>
            {canEditProfile ? (
              <Button icon={<EditOutlined />} onClick={openProfileEditor}>{t('people.editProfile')}</Button>
            ) : null}
            {canManageDirections && detail.id !== user?.id ? (
              detail.archived_at ? (
                <Popconfirm
                  title={t('people.restoreConfirm')}
                  description={t('people.restoreConfirmDescription')}
                  onConfirm={() => void updateArchiveStatus('restore')}
                >
                  <Button loading={updatingArchive}>{t('people.restore')}</Button>
                </Popconfirm>
              ) : (
                <Popconfirm
                  title={t('people.archiveConfirm')}
                  description={t('people.archiveConfirmDescription')}
                  onConfirm={() => void updateArchiveStatus('archive')}
                >
                  <Button danger loading={updatingArchive}>{t('people.archive')}</Button>
                </Popconfirm>
              )
            ) : null}
          </Space>
        ) : null}
      >
        <Skeleton active loading={detailLoading} paragraph={{ rows: 6 }}>
          {detail ? (
            <>
              {detail.is_stale ? (
                <Alert
                  type="warning"
                  showIcon
                  message={t(canEditProfile ? 'people.staleProfileManage' : 'people.staleProfile')}
                  action={canEditProfile ? (
                    <Button type="link" size="small" onClick={openProfileEditor}>
                      {t('people.reviewProfile')}
                    </Button>
                  ) : null}
                  style={{ marginBottom: 16 }}
                />
              ) : detail.review_due_at === null ? (
                <Alert
                  type="info"
                  showIcon
                  message={t(canEditProfile ? 'people.reviewMissingManage' : 'people.reviewMissing')}
                  action={canEditProfile ? (
                    <Button type="link" size="small" onClick={openProfileEditor}>
                      {t('people.reviewProfile')}
                    </Button>
                  ) : null}
                  style={{ marginBottom: 16 }}
                />
              ) : null}
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label={t('people.roleLabel')}>{t(`people.role.${detail.role}`)}</Descriptions.Item>
                <Descriptions.Item label={t('people.bio')}>{detail.bio || t('people.bioEmpty')}</Descriptions.Item>
                <Descriptions.Item label={t('people.consultationTopics')}>
                  {detail.consultation_topics.length > 0 ? (
                    <Space size={[4, 4]} wrap>{detail.consultation_topics.map((topic) => <Tag key={topic}>{topic}</Tag>)}</Space>
                  ) : t('people.consultationEmpty')}
                </Descriptions.Item>
                <Descriptions.Item label={t('people.lastConfirmed')}>
                  {detail.last_confirmed_at
                    ? formatDateTime(detail.last_confirmed_at, i18n.language)
                    : t('people.notConfirmed')}
                </Descriptions.Item>
                <Descriptions.Item label={t('people.reviewDue')}>
                  {detail.review_due_at
                    ? formatDateTime(detail.review_due_at, i18n.language)
                    : t('people.notScheduled')}
                </Descriptions.Item>
              </Descriptions>

              <Divider titlePlacement="start">{t('people.currentDirections')}</Divider>
              {detail.current_directions.length > 0 ? (
                <Space size={[4, 4]} wrap>
                  {detail.current_directions.map((direction) => {
                    const memberDirection = detail.direction_history.find((history) => (
                      history.id === direction.id && history.valid_until === null
                    ));
                    return (
                      <Space size={2} key={direction.id}>
                    <Tag color="blue">
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/research?direction=${encodeURIComponent(direction.id)}`)}
                        style={{ height: 'auto', padding: 0 }}
                      >
                        {direction.name} · {t(`people.directionRole.${direction.role}`)}
                      </Button>
                    </Tag>
                        {canManageDirections && memberDirection ? (
                          <Popconfirm
                            title={t('people.directionEndConfirm')}
                            onConfirm={() => void endDirection(memberDirection.member_direction_id)}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<StopOutlined />}
                              loading={endingDirectionId === memberDirection.member_direction_id}
                              aria-label={t('people.directionEnd')}
                            />
                          </Popconfirm>
                        ) : null}
                      </Space>
                    );
                  })}
                </Space>
              ) : <Typography.Text type="secondary">{t('people.currentDirectionsEmpty')}</Typography.Text>}

              <Divider titlePlacement="start">{t('people.representativeResources')}</Divider>
              {representativeResourcesLoading ? (
                <Spin size="small" />
              ) : representativeResources === null ? (
                <Alert type="warning" showIcon message={t('people.representativeResourcesLoadFailed')} />
              ) : representativeResources.length === 0 && !editingRepresentativeResources ? (
                <Typography.Text type="secondary">{t('people.representativeResourcesEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={representativeResources}
                  renderItem={(resource) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-representative-resource"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/resources/${encodeURIComponent(resource.asset_id)}`)}
                        >
                          {t('people.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={resource.title}
                        description={resource.description || t('people.resourceDescriptionEmpty')}
                      />
                    </List.Item>
                  )}
                />
              )}

              {canManageDirections ? (
                <div style={{ marginTop: 12 }}>
                  {editingRepresentativeResources ? (
                    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                      <Typography.Text type="secondary">{t('people.representativeResourcesHint')}</Typography.Text>
                      <Select
                        mode="multiple"
                        value={representativeResourceIds}
                        onChange={setRepresentativeResourceIds}
                        placeholder={t('people.representativeResourcesPlaceholder')}
                        options={representativeResourceOptions.map((resource) => ({
                          value: resource.asset_id,
                          label: resource.title,
                        }))}
                        notFoundContent={t('people.representativeResourcesOptionsEmpty')}
                        style={{ width: '100%' }}
                      />
                      <Space>
                        <Button type="primary" loading={savingRepresentativeResources} onClick={() => void saveRepresentativeResources()}>{t('common.save')}</Button>
                        <Button onClick={() => setEditingRepresentativeResources(false)}>{t('common.cancel')}</Button>
                      </Space>
                    </Space>
                  ) : (
                    <Button onClick={() => void openRepresentativeResourcesEditor()}>{t('people.representativeResourcesManage')}</Button>
                  )}
                </div>
              ) : null}

              <Divider titlePlacement="start">{t('people.responsibilities')}</Divider>
              {responsibilitiesLoading ? (
                <Spin size="small" />
              ) : responsibilities === null ? (
                <Alert type="warning" showIcon message={t('people.responsibilitiesLoadFailed')} />
              ) : responsibilities.length === 0 ? (
                <Typography.Text type="secondary">{t('people.responsibilitiesEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={responsibilities}
                  renderItem={(resource) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-resource"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/resources/${encodeURIComponent(resource.asset_id)}`)}
                        >
                          {t('people.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={resource.title}
                        description={resource.description || t('people.resourceDescriptionEmpty')}
                      />
                    </List.Item>
                  )}
                />
              )}

              {canManageDirections ? (
                <div style={{ marginTop: 16 }}>
                  {assigningDirection ? (
                    <Form form={directionForm} layout="vertical" onFinish={() => void assignDirection()}>
                      <Form.Item name="direction_id" label={t('people.direction')} rules={[{ required: true, message: t('people.directionRequired') }]}>
                        <Select
                          showSearch
                          optionFilterProp="label"
                          options={availableDirections.map((direction) => ({ value: direction.id, label: direction.name }))}
                          placeholder={t('people.directionPlaceholder')}
                          notFoundContent={t('people.directionOptionsEmpty')}
                        />
                      </Form.Item>
                      <Form.Item name="role" label={t('people.directionRoleLabel')} rules={[{ required: true }]}>
                        <Select options={[
                          { value: 'lead', label: t('people.directionRole.lead') },
                          { value: 'contributor', label: t('people.directionRole.contributor') },
                          { value: 'advisor', label: t('people.directionRole.advisor') },
                        ]} />
                      </Form.Item>
                      <Space>
                        <Button type="primary" loading={savingDirection} onClick={() => void assignDirection()}>{t('people.directionAssign')}</Button>
                        <Button onClick={() => setAssigningDirection(false)}>{t('common.cancel')}</Button>
                      </Space>
                    </Form>
                  ) : (
                    <Button icon={<UserAddOutlined />} onClick={() => void openDirectionAssignment()}>{t('people.directionAssign')}</Button>
                  )}
                </div>
              ) : null}

              <Divider titlePlacement="start">{t('people.directionHistory')}</Divider>
              {detail.direction_history.length > 0 ? (
                <List
                  size="small"
                  dataSource={detail.direction_history}
                  renderItem={(direction) => (
                    <List.Item>
                      <List.Item.Meta
                        title={(
                          <Button
                            type="link"
                            size="small"
                            onClick={() => navigate(`/research?direction=${encodeURIComponent(direction.id)}`)}
                            style={{ height: 'auto', padding: 0 }}
                          >
                            {direction.name}
                          </Button>
                        )}
                        description={`${formatDateTime(direction.valid_from, i18n.language)} · ${direction.valid_until ? formatDateTime(direction.valid_until, i18n.language) : t('people.directionCurrent')}`}
                      />
                      <Tag color={direction.valid_until ? 'default' : 'blue'}>{t(`people.directionRole.${direction.role}`)}</Tag>
                    </List.Item>
                  )}
                />
              ) : <Typography.Text type="secondary">{t('people.directionHistoryEmpty')}</Typography.Text>}

              <Divider titlePlacement="start">{t('people.recentWork')}</Divider>
              {recentWorkLoading ? (
                <Spin size="small" />
              ) : recentWork === null ? (
                <Alert type="warning" showIcon message={t('people.recentWorkLoadFailed')} />
              ) : !recentWork.visible ? (
                <Alert type="info" showIcon message={t('people.recentWorkHidden')} />
              ) : recentWork.items.length === 0 ? (
                <Typography.Text type="secondary">{t('people.recentWorkEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={recentWork.items}
                  renderItem={(activity) => (
                    <List.Item>
                      <List.Item.Meta
                        title={t('people.recentWorkInProject', {
                          action: t(`people.recentWorkAction.${activity.action}`, {
                            defaultValue: t('people.recentWorkAction.other'),
                          }),
                          project: activity.project_name,
                        })}
                        description={formatDateTime(activity.created_at, i18n.language)}
                      />
                    </List.Item>
                  )}
                />
              )}
            </>
          ) : null}
        </Skeleton>
      </Drawer>

      <Drawer
        title={t('people.editProfile')}
        width={560}
        open={editingProfile}
        onClose={() => setEditingProfile(false)}
        extra={(
          <Space>
            <Button onClick={() => setEditingProfile(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={savingProfile} onClick={() => void saveProfile()}>{t('common.save')}</Button>
          </Space>
        )}
      >
        <Form form={profileForm} layout="vertical" onFinish={() => void saveProfile()}>
          <Form.Item name="bio" label={t('people.bio')}>
            <Input.TextArea rows={5} maxLength={4000} showCount placeholder={t('people.bioPlaceholder')} />
          </Form.Item>
          <Form.Item name="consultation_topics" label={t('people.consultationTopics')}>
            <Select
              mode="tags"
              showSearch
              optionFilterProp="label"
              tokenSeparators={[',']}
              placeholder={t('people.consultationPlaceholder')}
              options={directions.map((direction) => ({ value: direction.name, label: direction.name }))}
            />
          </Form.Item>
          <Typography.Paragraph type="secondary">{t('people.consultationGuidance')}</Typography.Paragraph>
          <Form.Item name="show_recent_activity" label={t('people.showRecentActivity')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Typography.Paragraph type="secondary">{t('people.showRecentActivityHint')}</Typography.Paragraph>
          <Form.Item name="last_confirmed_at" label={t('people.lastConfirmed')}>
            <Input type="datetime-local" />
          </Form.Item>
          <Form.Item name="review_due_at" label={t('people.reviewDue')}>
            <Input type="datetime-local" />
          </Form.Item>
        </Form>
      </Drawer>
    </PageContainer>
  );
}
