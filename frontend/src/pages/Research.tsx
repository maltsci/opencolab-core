import { BookOutlined, BranchesOutlined, ClockCircleOutlined, DeleteOutlined, DownOutlined, EditOutlined, EyeInvisibleOutlined, LinkOutlined, PlusOutlined, PushpinOutlined, RobotOutlined, SearchOutlined, StopOutlined, UpOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Descriptions, Divider, Drawer, Form, Input, List, Modal, Popconfirm, Select, Skeleton, Space, Spin, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';

import PageContainer from '../components/library/PageContainer';
import EmptyState from '../components/ui/EmptyState';
import { ROLE_ADMIN, ROLE_PI } from '../constants/roles';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../services/api-client';
import type { Project, UserOption } from '../types/project';
import type { PersonDirectoryEntry } from '../types/person';
import type {
  DirectionActivity,
  ResearchDirection,
  ResearchDirectionCreateInput,
  DirectionMember,
  DirectionResource,
  DirectionLearningResource,
  DirectionResearchObject,
  DirectionProject,
  DirectionSteward,
  ResearchDirectionMergeInput,
  ResearchDirectionPage,
  ResearchDirectionRelation,
  ResearchDirectionUpdateInput,
} from '../types/research-direction';
import { formatDateTime } from '../components/library/library-utils';

interface DirectionFormValues {
  name: string;
  summary?: string;
  background?: string;
  scope?: string;
  owner_id?: string;
}

interface DirectionRelationFormValues {
  target_direction_id: string;
  reason: string;
}

interface DirectionProjectFormValues {
  project_id: string;
  reason?: string;
}

interface DirectionEditFormValues extends DirectionFormValues {
  last_confirmed_at?: string;
  review_due_at?: string;
}

interface DirectionMergeFormValues {
  target_direction_id: string;
  reason: string;
}

interface StewardFormValues {
  user_id: string;
}

interface DirectionCapabilities {
  can_maintain: boolean;
}

interface ResearchGroupOption {
  id: string;
  name: string;
}

interface DirectoryFilterOverrides {
  query?: string;
  memberId?: string;
  groupId?: string;
  resourceType?: string;
  directionStatus?: string;
}

const DIRECTORY_ASSET_TYPES = [
  'uploaded_file',
  'generated_doc',
  'research_memory',
  'report',
  'dataset',
  'protocol',
  'external_reference',
  'collection',
];

function isStale(direction: ResearchDirection): boolean {
  if (!direction.review_due_at) return false;
  const dueAt = new Date(direction.review_due_at).getTime();
  return !Number.isNaN(dueAt) && dueAt < Date.now();
}

function asOptionalValue(value: string | undefined): string | undefined {
  const trimmedValue = value?.trim();
  return trimmedValue || undefined;
}

function toLocalDateTimeValue(value: string | null): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function Research() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const selectedDirectionId = searchParams.get('direction');
  const { user } = useAuth();
  const [directions, setDirections] = useState<ResearchDirection[]>([]);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [directoryPeople, setDirectoryPeople] = useState<PersonDirectoryEntry[]>([]);
  const [researchGroups, setResearchGroups] = useState<ResearchGroupOption[]>([]);
  const [memberId, setMemberId] = useState<string>();
  const [groupId, setGroupId] = useState<string>();
  const [resourceType, setResourceType] = useState<string>();
  const [directionStatus, setDirectionStatus] = useState('active');
  const [detail, setDetail] = useState<ResearchDirection | null>(null);
  const [canMaintainDetail, setCanMaintainDetail] = useState(false);
  const [relations, setRelations] = useState<ResearchDirectionRelation[]>([]);
  const [relationsLoading, setRelationsLoading] = useState(false);
  const [resources, setResources] = useState<DirectionResource[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(false);
  const [representativeResources, setRepresentativeResources] = useState<DirectionResource[]>([]);
  const [representativeResourcesLoading, setRepresentativeResourcesLoading] = useState(false);
  const [editingRepresentativeResources, setEditingRepresentativeResources] = useState(false);
  const [representativeResourceIds, setRepresentativeResourceIds] = useState<string[]>([]);
  const [savingRepresentativeResources, setSavingRepresentativeResources] = useState(false);
  const [learningResources, setLearningResources] = useState<DirectionLearningResource[]>([]);
  const [learningResourcesLoading, setLearningResourcesLoading] = useState(false);
  const [editingLearningResources, setEditingLearningResources] = useState(false);
  const [learningResourceIds, setLearningResourceIds] = useState<string[]>([]);
  const [savingLearningResources, setSavingLearningResources] = useState(false);
  const [researchObjects, setResearchObjects] = useState<DirectionResearchObject[]>([]);
  const [researchObjectsLoading, setResearchObjectsLoading] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [directionProjects, setDirectionProjects] = useState<DirectionProject[]>([]);
  const [directionProjectsLoading, setDirectionProjectsLoading] = useState(false);
  const [activities, setActivities] = useState<DirectionActivity[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  const [updatingActivityId, setUpdatingActivityId] = useState<string | null>(null);
  const [members, setMembers] = useState<DirectionMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [stewards, setStewards] = useState<DirectionSteward[]>([]);
  const [stewardsLoading, setStewardsLoading] = useState(false);
  const [delegatingSteward, setDelegatingSteward] = useState(false);
  const [savingSteward, setSavingSteward] = useState(false);
  const [revokingStewardId, setRevokingStewardId] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);
  const [linkingSaving, setLinkingSaving] = useState(false);
  const [linkingProject, setLinkingProject] = useState(false);
  const [linkingProjectSaving, setLinkingProjectSaving] = useState(false);
  const [removingProjectId, setRemovingProjectId] = useState<string | null>(null);
  const [archiving, setArchiving] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [merging, setMerging] = useState(false);
  const [form] = Form.useForm<DirectionFormValues>();
  const [editForm] = Form.useForm<DirectionEditFormValues>();
  const [mergeForm] = Form.useForm<DirectionMergeFormValues>();
  const [relationForm] = Form.useForm<DirectionRelationFormValues>();
  const [projectLinkForm] = Form.useForm<DirectionProjectFormValues>();
  const [stewardForm] = Form.useForm<StewardFormValues>();
  const canCreate = user?.role === ROLE_ADMIN || user?.role === ROLE_PI;

  const loadDirections = async (overrides: DirectoryFilterOverrides = {}) => {
    const filters = {
      query,
      memberId,
      groupId,
      resourceType,
      directionStatus,
      ...overrides,
    };
    setLoading(true);
    try {
      const { data } = await apiClient.get<ResearchDirectionPage>('/research-directions', {
        params: {
          status: filters.directionStatus,
          limit: 100,
          query: filters.query.trim(),
          member_id: filters.memberId,
          group_id: filters.groupId,
          resource_type: filters.resourceType,
        },
      });
      setDirections(data.items);
    } catch {
      message.error(t('research.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDirections();
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiClient.get<PersonDirectoryEntry[]>('/people'),
      apiClient.get<ResearchGroupOption[]>('/research-groups'),
    ])
      .then(([peopleResponse, groupsResponse]) => {
        if (!active) return;
        setDirectoryPeople(peopleResponse.data);
        setResearchGroups(groupsResponse.data);
      })
      .catch(() => {
        if (!active) return;
        setDirectoryPeople([]);
        setResearchGroups([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedDirectionId) return;
    apiClient.get<ResearchDirection>(`/research-directions/${selectedDirectionId}`)
      .then((response) => setDetail(response.data))
      .catch(() => message.error(t('research.detailLoadFailed')));
  }, [selectedDirectionId]);

  useEffect(() => {
    let active = true;

    if (!detail) {
      setCanMaintainDetail(false);
      return () => {
        active = false;
      };
    }

    if (canCreate) {
      setCanMaintainDetail(true);
      return () => {
        active = false;
      };
    }

    setCanMaintainDetail(false);
    apiClient.get<DirectionCapabilities>(`/research-directions/${detail.id}/capabilities`)
      .then((response) => {
        if (active) setCanMaintainDetail(response.data.can_maintain);
      })
      .catch(() => {
        if (active) setCanMaintainDetail(false);
      });

    return () => {
      active = false;
    };
  }, [canCreate, detail?.id]);

  useEffect(() => {
    if (!detail) {
      setRelations([]);
      setLinking(false);
      return;
    }

    setRelationsLoading(true);
    apiClient.get<ResearchDirectionRelation[]>(`/research-directions/${detail.id}/relations`, {
      params: { limit: 100 },
    })
      .then((response) => setRelations(response.data))
      .catch(() => {
        setRelations([]);
        message.error(t('research.relationsLoadFailed'));
      })
      .finally(() => setRelationsLoading(false));
  }, [detail?.id]);

  useEffect(() => {
    if (!detail) {
      setRepresentativeResources([]);
      setEditingRepresentativeResources(false);
      return;
    }

    setRepresentativeResourcesLoading(true);
    apiClient.get<DirectionResource[]>(`/research-directions/${detail.id}/representative-resources`, {
      params: { limit: 20 },
    })
      .then((response) => setRepresentativeResources(response.data))
      .catch(() => {
        setRepresentativeResources([]);
        message.error(t('research.representativeResourcesLoadFailed'));
      })
      .finally(() => setRepresentativeResourcesLoading(false));
  }, [detail?.id, t]);

  useEffect(() => {
    if (!detail) {
      setLearningResources([]);
      setEditingLearningResources(false);
      return;
    }

    setLearningResourcesLoading(true);
    apiClient.get<DirectionLearningResource[]>(`/research-directions/${detail.id}/learning-resources`, {
      params: { limit: 20 },
    })
      .then((response) => setLearningResources(response.data))
      .catch(() => {
        setLearningResources([]);
        message.error(t('research.learningResourcesLoadFailed'));
      })
      .finally(() => setLearningResourcesLoading(false));
  }, [detail?.id, t]);

  useEffect(() => {
    if (!detail || !canCreate) {
      setStewards([]);
      setDelegatingSteward(false);
      return;
    }

    setStewardsLoading(true);
    Promise.all([
      apiClient.get<DirectionSteward[]>(`/knowledge-governance/directions/${detail.id}/stewards`),
      apiClient.get<UserOption[]>('/auth/users'),
    ])
      .then(([stewardsResponse, usersResponse]) => {
        setStewards(stewardsResponse.data);
        setUsers(usersResponse.data);
      })
      .catch(() => {
        setStewards([]);
        message.error(t('research.stewardsLoadFailed'));
      })
      .finally(() => setStewardsLoading(false));
  }, [detail?.id, canCreate]);

  useEffect(() => {
    if (!detail) {
      setMembers([]);
      return;
    }

    setMembersLoading(true);
    apiClient.get<DirectionMember[]>(`/research-directions/${detail.id}/members`)
      .then((response) => setMembers(response.data))
      .catch(() => {
        setMembers([]);
        message.error(t('research.membersLoadFailed'));
      })
      .finally(() => setMembersLoading(false));
  }, [detail?.id]);

  useEffect(() => {
    if (!detail) {
      setResources([]);
      return;
    }

    setResourcesLoading(true);
    apiClient.get<DirectionResource[]>(`/research-directions/${detail.id}/resources`, {
      params: { limit: 20 },
    })
      .then((response) => setResources(response.data))
      .catch(() => {
        setResources([]);
        message.error(t('research.resourcesLoadFailed'));
      })
      .finally(() => setResourcesLoading(false));
  }, [detail?.id]);

  useEffect(() => {
    if (!detail) {
      setResearchObjects([]);
      return;
    }

    setResearchObjectsLoading(true);
    apiClient.get<DirectionResearchObject[]>(`/research-directions/${detail.id}/research-objects`, {
      params: { limit: 20 },
    })
      .then((response) => setResearchObjects(response.data))
      .catch(() => {
        setResearchObjects([]);
        message.error(t('research.researchObjectsLoadFailed'));
      })
      .finally(() => setResearchObjectsLoading(false));
  }, [detail?.id, t]);

  useEffect(() => {
    if (!detail) {
      setDirectionProjects([]);
      return;
    }

    setDirectionProjectsLoading(true);
    apiClient.get<DirectionProject[]>(`/research-directions/${detail.id}/projects`, {
      params: { limit: 20 },
    })
      .then((response) => setDirectionProjects(response.data))
      .catch(() => {
        setDirectionProjects([]);
        message.error(t('research.projectsLoadFailed'));
      })
      .finally(() => setDirectionProjectsLoading(false));
  }, [detail?.id, t]);

  useEffect(() => {
    if (!detail) {
      setActivities([]);
      return;
    }

    setActivitiesLoading(true);
    apiClient.get<DirectionActivity[]>(`/research-directions/${detail.id}/activities`, {
      params: { limit: 20 },
    })
      .then((response) => setActivities(response.data))
      .catch(() => {
        setActivities([]);
        message.error(t('research.activitiesLoadFailed'));
      })
      .finally(() => setActivitiesLoading(false));
  }, [detail?.id, t]);

  useEffect(() => {
    if (!detail || !canMaintainDetail) {
      setProjects([]);
      return;
    }

    const params = canCreate ? undefined : { scope: 'own' };
    apiClient.get<Project[]>('/projects', { params })
      .then((response) => setProjects(response.data))
      .catch(() => setProjects([]));
  }, [canCreate, canMaintainDetail, detail?.id]);

  const directionOwners = useMemo(
    () => users.map((candidate) => ({
      value: candidate.id,
      label: candidate.display_name
        ? `${candidate.display_name} (${candidate.username})`
        : candidate.username,
    })),
    [users],
  );

  const loadUsers = async () => {
    if (users.length > 0) return;
    try {
      const { data } = await apiClient.get<UserOption[]>('/auth/users');
      setUsers(data);
    } catch {
      setUsers([]);
    }
  };

  const openCreate = async () => {
    form.resetFields();
    setCreateOpen(true);
    await loadUsers();
  };

  const createDirection = async () => {
    const values = await form.validateFields();
    const payload: ResearchDirectionCreateInput = {
      name: values.name.trim(),
      summary: asOptionalValue(values.summary),
      background: asOptionalValue(values.background),
      scope: asOptionalValue(values.scope),
      owner_id: values.owner_id || undefined,
    };
    setCreating(true);
    try {
      const { data } = await apiClient.post<ResearchDirection>('/research-directions', payload);
      setCreateOpen(false);
      setDetail(data);
      await loadDirections();
      message.success(t('research.createSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.createFailed'));
    } finally {
      setCreating(false);
    }
  };

  const submitSearch = () => {
    void loadDirections();
  };

  const clearDirectoryFilters = () => {
    setQuery('');
    setMemberId(undefined);
    setGroupId(undefined);
    setResourceType(undefined);
    setDirectionStatus('active');
    void loadDirections({
      query: '',
      memberId: undefined,
      groupId: undefined,
      resourceType: undefined,
      directionStatus: 'active',
    });
  };

  const updateActivityPresentation = async (
    activity: DirectionActivity,
    presentation: 'normal' | 'pinned' | 'hidden',
  ) => {
    if (!detail) return;
    setUpdatingActivityId(activity.id);
    try {
      await apiClient.put(
        `/research-directions/${detail.id}/activities/${activity.id}/presentation`,
        { presentation },
      );
      setActivities((current) => presentation === 'hidden'
        ? current.filter((candidate) => candidate.id !== activity.id)
        : current.map((candidate) => candidate.id === activity.id
          ? { ...candidate, is_pinned: presentation === 'pinned' }
          : candidate));
      message.success(t('research.activityPresentationSaved'));
    } catch {
      message.error(t('research.activityPresentationSaveFailed'));
    } finally {
      setUpdatingActivityId(null);
    }
  };

  const openEdit = async () => {
    if (!detail) return;
    editForm.setFieldsValue({
      name: detail.name,
      summary: detail.summary || undefined,
      background: detail.background || undefined,
      scope: detail.scope || undefined,
      owner_id: canCreate ? detail.owner_id || undefined : undefined,
      last_confirmed_at: toLocalDateTimeValue(detail.last_confirmed_at),
      review_due_at: toLocalDateTimeValue(detail.review_due_at),
    });
    setEditOpen(true);
    if (canCreate) await loadUsers();
  };

  const updateDirection = async () => {
    if (!detail) return;
    const values = await editForm.validateFields();
    const payload: ResearchDirectionUpdateInput = {
      name: values.name.trim(),
      summary: values.summary?.trim() || null,
      background: values.background?.trim() || null,
      scope: values.scope?.trim() || null,
      last_confirmed_at: values.last_confirmed_at ? new Date(values.last_confirmed_at).toISOString() : null,
      review_due_at: values.review_due_at ? new Date(values.review_due_at).toISOString() : null,
    };
    if (canCreate) payload.owner_id = values.owner_id || null;
    setUpdating(true);
    try {
      const { data } = await apiClient.patch<ResearchDirection>(`/research-directions/${detail.id}`, payload);
      setDetail(data);
      setEditOpen(false);
      await loadDirections();
      message.success(t('research.updateSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.updateFailed'));
    } finally {
      setUpdating(false);
    }
  };

  const openMerge = () => {
    mergeForm.resetFields();
    setMergeOpen(true);
  };

  const mergeDirection = async (values: DirectionMergeFormValues) => {
    if (!detail) return;
    const payload: ResearchDirectionMergeInput = {
      target_direction_id: values.target_direction_id,
      reason: values.reason.trim(),
    };
    setMerging(true);
    try {
      await apiClient.post(`/research-directions/${detail.id}/merge`, payload);
      setMergeOpen(false);
      setDetail(null);
      await loadDirections();
      message.success(t('research.mergeSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.mergeFailed'));
    } finally {
      setMerging(false);
    }
  };

  const confirmMerge = async () => {
    const values = await mergeForm.validateFields();
    Modal.confirm({
      title: t('research.mergeConfirmTitle'),
      content: t('research.mergeConfirmDescription'),
      okText: t('research.merge'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: () => mergeDirection(values),
    });
  };

  const relatedDirectionIds = useMemo(() => {
    if (!detail) return new Set<string>();
    return new Set(relations.map((relation) => (
      relation.direction_a_id === detail.id ? relation.direction_b_id : relation.direction_a_id
    )));
  }, [detail, relations]);

  const relationOptions = useMemo(() => directions
    .filter((direction) => direction.id !== detail?.id && !relatedDirectionIds.has(direction.id))
    .map((direction) => ({ value: direction.id, label: direction.name })), [detail?.id, directions, relatedDirectionIds]);

  const openRelationForm = () => {
    relationForm.resetFields();
    setLinking(true);
  };

  const learningResourceOptions = useMemo(() => {
    const selectedIds = new Set(learningResourceIds);
    return resources
      .filter((resource) => !selectedIds.has(resource.asset_id))
      .map((resource) => ({ value: resource.asset_id, label: resource.title }));
  }, [learningResourceIds, resources]);

  const startEditingLearningResources = () => {
    setLearningResourceIds(learningResources.map((resource) => resource.asset_id));
    setEditingLearningResources(true);
  };

  const startEditingRepresentativeResources = () => {
    setRepresentativeResourceIds(representativeResources.map((resource) => resource.asset_id));
    setEditingRepresentativeResources(true);
  };

  const saveRepresentativeResources = async () => {
    if (!detail) return;
    setSavingRepresentativeResources(true);
    try {
      const { data } = await apiClient.put<DirectionResource[]>(
        `/research-directions/${detail.id}/representative-resources`,
        { asset_ids: representativeResourceIds },
      );
      setRepresentativeResources(data);
      setEditingRepresentativeResources(false);
      message.success(t('research.representativeResourcesSaveSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.representativeResourcesSaveFailed'));
    } finally {
      setSavingRepresentativeResources(false);
    }
  };

  const moveLearningResource = (index: number, direction: -1 | 1) => {
    setLearningResourceIds((current) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= current.length) return current;
      const next = [...current];
      [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
      return next;
    });
  };

  const saveLearningResources = async () => {
    if (!detail) return;
    setSavingLearningResources(true);
    try {
      const { data } = await apiClient.put<DirectionLearningResource[]>(
        `/research-directions/${detail.id}/learning-resources`,
        { asset_ids: learningResourceIds },
      );
      setLearningResources(data);
      setEditingLearningResources(false);
      message.success(t('research.learningResourcesSaveSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.learningResourcesSaveFailed'));
    } finally {
      setSavingLearningResources(false);
    }
  };

  const projectOptions = useMemo(() => {
    const linkedProjectIds = new Set(directionProjects.map((project) => project.project_id));
    return projects
      .filter((project) => !project.archived && !linkedProjectIds.has(project.id))
      .map((project) => ({ value: project.id, label: project.name }));
  }, [directionProjects, projects]);

  const openProjectLinkForm = () => {
    projectLinkForm.resetFields();
    setLinkingProject(true);
  };

  const createProjectLink = async () => {
    if (!detail) return;
    const values = await projectLinkForm.validateFields();
    setLinkingProjectSaving(true);
    try {
      const { data } = await apiClient.post<DirectionProject>(
        `/research-directions/${detail.id}/projects`,
        { project_id: values.project_id, reason: asOptionalValue(values.reason) },
      );
      setDirectionProjects((current) => [data, ...current]);
      setLinkingProject(false);
      message.success(t('research.projectLinkSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.projectLinkFailed'));
    } finally {
      setLinkingProjectSaving(false);
    }
  };

  const removeProjectLink = async (projectId: string) => {
    if (!detail) return;
    setRemovingProjectId(projectId);
    try {
      await apiClient.delete(`/research-directions/${detail.id}/projects/${projectId}`);
      setDirectionProjects((current) => current.filter((project) => project.project_id !== projectId));
      setActivities((current) => current.filter((activity) => activity.project_id !== projectId));
      message.success(t('research.projectUnlinkSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.projectUnlinkFailed'));
    } finally {
      setRemovingProjectId(null);
    }
  };

  const stewardOptions = useMemo(() => {
    const stewardIds = new Set(stewards.map((steward) => steward.user_id));
    return directionOwners.filter((candidate) => !stewardIds.has(candidate.value));
  }, [directionOwners, stewards]);

  const openStewardForm = () => {
    stewardForm.resetFields();
    setDelegatingSteward(true);
  };

  const assignSteward = async () => {
    if (!detail) return;
    const values = await stewardForm.validateFields();
    setSavingSteward(true);
    try {
      const { data } = await apiClient.post<DirectionSteward>(
        `/knowledge-governance/directions/${detail.id}/stewards`,
        values,
      );
      setStewards((current) => [...current, data]);
      setDelegatingSteward(false);
      message.success(t('research.stewardAssignSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.stewardAssignFailed'));
    } finally {
      setSavingSteward(false);
    }
  };

  const revokeSteward = async (userId: string) => {
    if (!detail) return;
    setRevokingStewardId(userId);
    try {
      await apiClient.delete(`/knowledge-governance/directions/${detail.id}/stewards/${userId}`);
      setStewards((current) => current.filter((steward) => steward.user_id !== userId));
      message.success(t('research.stewardRevokeSuccess'));
    } catch {
      message.error(t('research.stewardRevokeFailed'));
    } finally {
      setRevokingStewardId(null);
    }
  };

  const createRelation = async () => {
    if (!detail) return;
    const values = await relationForm.validateFields();
    setLinkingSaving(true);
    try {
      const { data } = await apiClient.post<ResearchDirectionRelation>(
        `/research-directions/${detail.id}/relations`,
        { target_direction_id: values.target_direction_id, reason: values.reason.trim() },
      );
      setRelations((current) => [data, ...current]);
      setLinking(false);
      message.success(t('research.relationCreateSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.relationCreateFailed'));
    } finally {
      setLinkingSaving(false);
    }
  };

  const removeRelation = async (relationId: string) => {
    try {
      await apiClient.delete(`/research-direction-relations/${relationId}`);
      setRelations((current) => current.filter((relation) => relation.id !== relationId));
      message.success(t('research.relationRemoveSuccess'));
    } catch {
      message.error(t('research.relationRemoveFailed'));
    }
  };

  const archiveDirection = async () => {
    if (!detail) return;
    setArchiving(true);
    try {
      await apiClient.post(`/research-directions/${detail.id}/archive`);
      setDetail(null);
      await loadDirections();
      message.success(t('research.archiveSuccess'));
    } catch (error: unknown) {
      const detailMessage = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detailMessage || t('research.archiveFailed'));
    } finally {
      setArchiving(false);
    }
  };

  const emptyDescription = canCreate
    ? t('research.emptyDescriptionManager')
    : t('research.emptyDescriptionMember');
  const hasDirectoryFilters = Boolean(
    query.trim() || memberId || groupId || resourceType || directionStatus !== 'active',
  );

  return (
    <PageContainer
      title={t('research.title')}
      description={t('research.description')}
      extra={canCreate ? (
        <Button type="primary" icon={<PlusOutlined />} onClick={() => void openCreate()}>
          {t('research.create')}
        </Button>
      ) : null}
    >
      <Card styles={{ body: { padding: 16 } }}>
        <Input
          allowClear
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onPressEnter={submitSearch}
          placeholder={t('research.searchPlaceholder')}
          prefix={<SearchOutlined />}
          suffix={<Button type="link" size="small" onClick={submitSearch}>{t('research.search')}</Button>}
          aria-label={t('research.searchPlaceholder')}
        />
        <Space wrap size={[8, 8]} style={{ marginTop: 12 }}>
          <Typography.Text type="secondary">{t('research.filters')}</Typography.Text>
          <Select
            allowClear
            value={memberId}
            onChange={setMemberId}
            placeholder={t('research.filterMember')}
            options={directoryPeople.map((person) => ({
              value: person.id,
              label: person.display_name
                ? `${person.display_name} (${person.username})`
                : person.username,
            }))}
            style={{ minWidth: 160 }}
          />
          <Select
            allowClear
            value={groupId}
            onChange={setGroupId}
            placeholder={t('research.filterGroup')}
            options={researchGroups.map((group) => ({ value: group.id, label: group.name }))}
            style={{ minWidth: 160 }}
          />
          <Select
            allowClear
            value={resourceType}
            onChange={setResourceType}
            placeholder={t('research.filterResourceType')}
            options={DIRECTORY_ASSET_TYPES.map((assetType) => ({
              value: assetType,
              label: t(`library.assetType.${assetType}`, assetType),
            }))}
            style={{ minWidth: 160 }}
          />
          <Select
            value={directionStatus}
            onChange={setDirectionStatus}
            aria-label={t('research.filterStatus')}
            options={[
              { value: 'active', label: t('research.filterStatusActive') },
              { value: 'all', label: t('research.filterStatusAll') },
              { value: 'archived', label: t('research.filterStatusArchived') },
              { value: 'merged', label: t('research.filterStatusMerged') },
            ]}
            style={{ minWidth: 130 }}
          />
          <Button onClick={submitSearch}>{t('research.applyFilters')}</Button>
          {hasDirectoryFilters ? (
            <Button type="link" onClick={clearDirectoryFilters}>{t('research.clearFilters')}</Button>
          ) : null}
        </Space>
      </Card>

      <Card style={{ marginTop: 16 }} styles={{ body: { padding: loading || directions.length === 0 ? 32 : 0 } }}>
        {loading ? (
          <Space orientation="vertical" size="large" style={{ width: '100%' }}>
            <Skeleton active paragraph={{ rows: 2 }} />
            <Skeleton active paragraph={{ rows: 2 }} />
          </Space>
        ) : directions.length === 0 ? (
          <EmptyState
            icon={<BookOutlined />}
            title={hasDirectoryFilters ? t('research.searchEmptyTitle') : t('research.emptyTitle')}
            description={hasDirectoryFilters ? t('research.searchEmptyDescription') : emptyDescription}
            cta={canCreate && !hasDirectoryFilters ? {
              label: t('research.create'),
              icon: <PlusOutlined />,
              onClick: () => void openCreate(),
            } : undefined}
          />
        ) : (
          <List
            dataSource={directions}
            renderItem={(direction) => (
              <List.Item style={{ padding: '18px 20px' }}>
                <List.Item.Meta
                  title={(
                    <Space size={8} wrap>
                      <Typography.Link onClick={() => setDetail(direction)}>
                        {direction.name}
                      </Typography.Link>
                      {isStale(direction) ? <Tag color="warning">{t('research.stale')}</Tag> : null}
                    </Space>
                  )}
                  description={direction.summary || t('research.summaryEmpty')}
                />
                <Button type="link" onClick={() => setDetail(direction)}>{t('research.viewDetail')}</Button>
              </List.Item>
            )}
          />
        )}
      </Card>

      <Drawer
        title={detail?.name}
        width={560}
        open={detail !== null}
        onClose={() => setDetail(null)}
        extra={detail ? (
          <Space>
            <Button
              icon={<RobotOutlined />}
              onClick={() => navigate(`/assistant?context=direction&query=${encodeURIComponent(detail.name)}`)}
            >
              {t('assistant.continueExploring')}
            </Button>
            {canMaintainDetail ? (
              <Button icon={<EditOutlined />} onClick={() => void openEdit()}>{t('common.edit')}</Button>
            ) : null}
            {canMaintainDetail && canCreate ? (
              <>
                <Button icon={<BranchesOutlined />} onClick={openMerge}>{t('research.merge')}</Button>
                <Popconfirm
                  title={t('research.archiveConfirm')}
                  description={t('research.archiveConfirmDescription')}
                  okText={t('research.archive')}
                  cancelText={t('common.cancel')}
                  onConfirm={() => void archiveDirection()}
                >
                  <Button danger icon={<StopOutlined />} loading={archiving}>{t('research.archive')}</Button>
                </Popconfirm>
              </>
            ) : null}
          </Space>
        ) : null}
      >
        {detail ? (
          <>
            {isStale(detail) ? (
              <Alert
                type="warning"
                showIcon
                message={t(canMaintainDetail ? 'research.staleInfoManage' : 'research.staleInfo')}
                action={canMaintainDetail ? (
                  <Button type="link" size="small" onClick={() => void openEdit()}>
                    {t('research.reviewDirection')}
                  </Button>
                ) : null}
                style={{ marginBottom: 16 }}
              />
            ) : detail.review_due_at === null ? (
              <Alert
                type="info"
                showIcon
                message={t(canMaintainDetail ? 'research.reviewMissingManage' : 'research.reviewMissing')}
                action={canMaintainDetail ? (
                  <Button type="link" size="small" onClick={() => void openEdit()}>
                    {t('research.reviewDirection')}
                  </Button>
                ) : null}
                style={{ marginBottom: 16 }}
              />
            ) : null}
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label={t('research.summary')}>
                {detail.summary || t('research.summaryEmpty')}
              </Descriptions.Item>
              <Descriptions.Item label={t('research.background')}>
                {detail.background || t('research.backgroundEmpty')}
              </Descriptions.Item>
              <Descriptions.Item label={t('research.scope')}>
                {detail.scope || t('research.scopeEmpty')}
              </Descriptions.Item>
              <Descriptions.Item label={t('research.lastConfirmed')}>
                {detail.last_confirmed_at
                  ? formatDateTime(detail.last_confirmed_at, i18n.language)
                  : t('research.notConfirmed')}
              </Descriptions.Item>
              <Descriptions.Item label={t('research.reviewDue')}>
                {detail.review_due_at
                  ? formatDateTime(detail.review_due_at, i18n.language)
                  : t('research.notScheduled')}
              </Descriptions.Item>
              <Descriptions.Item label={t('research.updatedAt')}>
                {formatDateTime(detail.updated_at, i18n.language)}
              </Descriptions.Item>
            </Descriptions>

            {canCreate ? (
              <>
                <Divider titlePlacement="start">{t('research.stewards')}</Divider>
                <Spin spinning={stewardsLoading}>
                  {stewards.length === 0 ? (
                    <Typography.Text type="secondary">{t('research.stewardsEmpty')}</Typography.Text>
                  ) : (
                    <List
                      size="small"
                      dataSource={stewards}
                      renderItem={(steward) => {
                        const stewardUser = users.find((candidate) => candidate.id === steward.user_id);
                        return (
                          <List.Item
                            actions={detail.status === 'active' ? [
                              <Popconfirm
                                key="revoke"
                                title={t('research.stewardRevokeConfirm')}
                                onConfirm={() => void revokeSteward(steward.user_id)}
                              >
                                <Button
                                  type="text"
                                  danger
                                  size="small"
                                  loading={revokingStewardId === steward.user_id}
                                >
                                  {t('research.stewardRevoke')}
                                </Button>
                              </Popconfirm>,
                            ] : []}
                          >
                            <List.Item.Meta
                              title={stewardUser?.display_name || stewardUser?.username || steward.user_id}
                              description={t('research.stewardMaintains')}
                            />
                          </List.Item>
                        );
                      }}
                    />
                  )}
                </Spin>

                {detail.status === 'active' ? (
                  <div style={{ marginTop: 16 }}>
                    {delegatingSteward ? (
                      <Form form={stewardForm} layout="vertical" onFinish={() => void assignSteward()}>
                        <Form.Item
                          name="user_id"
                          label={t('research.steward')}
                          rules={[{ required: true, message: t('research.stewardRequired') }]}
                        >
                          <Select
                            showSearch
                            optionFilterProp="label"
                            options={stewardOptions}
                            placeholder={t('research.stewardPlaceholder')}
                            notFoundContent={t('research.stewardOptionsEmpty')}
                          />
                        </Form.Item>
                        <Space>
                          <Button type="primary" loading={savingSteward} onClick={() => void assignSteward()}>
                            {t('research.stewardAssign')}
                          </Button>
                          <Button onClick={() => setDelegatingSteward(false)}>{t('common.cancel')}</Button>
                        </Space>
                      </Form>
                    ) : (
                      <Button onClick={openStewardForm} disabled={stewardOptions.length === 0}>
                        {t('research.stewardAssign')}
                      </Button>
                    )}
                  </div>
                ) : null}
              </>
            ) : null}

            <Divider titlePlacement="start">{t('research.members')}</Divider>
            <Spin spinning={membersLoading}>
              {members.length === 0 ? (
                <Typography.Text type="secondary">{t('research.membersEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={members}
                  renderItem={(member) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-member"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/people?person=${encodeURIComponent(member.id)}`)}
                        >
                          {t('research.openMember')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={member.display_name || member.username}
                        description={t(`people.directionRole.${member.direction_role}`)}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            <Divider titlePlacement="start">{t('research.resources')}</Divider>
            <Spin spinning={resourcesLoading}>
              {resources.length === 0 ? (
                <Typography.Text type="secondary">{t('research.resourcesEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={resources}
                  renderItem={(resource) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-resource"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/resources/${encodeURIComponent(resource.asset_id)}`)}
                        >
                          {t('research.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={resource.title}
                        description={(
                          <Space orientation="vertical" size={2}>
                            <Typography.Text type="secondary">
                              {resource.purpose || resource.description || t('research.resourceDescriptionEmpty')}
                            </Typography.Text>
                            <Typography.Text type="secondary">
                              {t('research.resourceMeta', {
                                type: resource.asset_type,
                                steward: resource.steward_name || t('research.resourceStewardEmpty'),
                              })}
                            </Typography.Text>
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            <Divider titlePlacement="start">{t('research.representativeResources')}</Divider>
            <Spin spinning={representativeResourcesLoading}>
              {representativeResources.length === 0 && !editingRepresentativeResources ? (
                <Typography.Text type="secondary">{t('research.representativeResourcesEmpty')}</Typography.Text>
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
                          {t('research.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={(
                          <Space size={8} wrap>
                            <Typography.Text>{resource.title}</Typography.Text>
                            <Tag>{resource.asset_type}</Tag>
                          </Space>
                        )}
                        description={resource.purpose || resource.description || t('research.resourceDescriptionEmpty')}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            {canCreate ? (
              <div style={{ marginTop: 16 }}>
                {editingRepresentativeResources ? (
                  <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                    <Typography.Text type="secondary">{t('research.representativeResourcesHint')}</Typography.Text>
                    <Select
                      mode="multiple"
                      showSearch
                      optionFilterProp="label"
                      value={representativeResourceIds}
                      options={resources.map((resource) => ({ value: resource.asset_id, label: resource.title }))}
                      placeholder={t('research.representativeResourcesPlaceholder')}
                      notFoundContent={t('research.representativeResourcesOptionsEmpty')}
                      onChange={(assetIds) => setRepresentativeResourceIds(assetIds)}
                    />
                    <Space>
                      <Button type="primary" loading={savingRepresentativeResources} onClick={() => void saveRepresentativeResources()}>
                        {t('common.save')}
                      </Button>
                      <Button onClick={() => setEditingRepresentativeResources(false)}>{t('common.cancel')}</Button>
                    </Space>
                  </Space>
                ) : (
                  <Button icon={<EditOutlined />} onClick={startEditingRepresentativeResources}>
                    {t('research.representativeResourcesManage')}
                  </Button>
                )}
              </div>
            ) : null}

            <Divider titlePlacement="start">{t('research.learningResources')}</Divider>
            <Spin spinning={learningResourcesLoading}>
              {learningResources.length === 0 && !editingLearningResources ? (
                <Typography.Text type="secondary">{t('research.learningResourcesEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={learningResources}
                  renderItem={(resource) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-learning-resource"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/resources/${encodeURIComponent(resource.asset_id)}`)}
                        >
                          {t('research.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={(
                          <Space size={8} wrap>
                            <Tag color="blue">{resource.learning_order}</Tag>
                            <Typography.Text>{resource.title}</Typography.Text>
                          </Space>
                        )}
                        description={resource.purpose || resource.description || t('research.resourceDescriptionEmpty')}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            {canCreate ? (
              <div style={{ marginTop: 16 }}>
                {editingLearningResources ? (
                  <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
                    <Typography.Text type="secondary">{t('research.learningResourcesHint')}</Typography.Text>
                    {learningResourceIds.length > 0 ? (
                      <List
                        size="small"
                        bordered
                        dataSource={learningResourceIds}
                        renderItem={(assetId, index) => {
                          const resource = resources.find((candidate) => candidate.asset_id === assetId);
                          return (
                            <List.Item
                              actions={[
                                <Button
                                  key="up"
                                  type="text"
                                  size="small"
                                  icon={<UpOutlined />}
                                  disabled={index === 0}
                                  aria-label={t('research.learningResourcesMoveUp')}
                                  onClick={() => moveLearningResource(index, -1)}
                                />,
                                <Button
                                  key="down"
                                  type="text"
                                  size="small"
                                  icon={<DownOutlined />}
                                  disabled={index === learningResourceIds.length - 1}
                                  aria-label={t('research.learningResourcesMoveDown')}
                                  onClick={() => moveLearningResource(index, 1)}
                                />,
                                <Button
                                  key="remove"
                                  type="text"
                                  danger
                                  size="small"
                                  icon={<DeleteOutlined />}
                                  aria-label={t('common.delete')}
                                  onClick={() => setLearningResourceIds((current) => current.filter((id) => id !== assetId))}
                                />,
                              ]}
                            >
                              <List.Item.Meta
                                title={`${index + 1}. ${resource?.title || t('research.learningResourcesUnavailable')}`}
                              />
                            </List.Item>
                          );
                        }}
                      />
                    ) : (
                      <Typography.Text type="secondary">{t('research.learningResourcesSelectionEmpty')}</Typography.Text>
                    )}
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={learningResourceOptions}
                      placeholder={t('research.learningResourcesAddPlaceholder')}
                      notFoundContent={t('research.learningResourcesOptionsEmpty')}
                      onSelect={(assetId) => {
                        if (!assetId) return;
                        setLearningResourceIds((current) => [...current, assetId]);
                      }}
                      value={undefined}
                    />
                    <Space>
                      <Button type="primary" loading={savingLearningResources} onClick={() => void saveLearningResources()}>
                        {t('common.save')}
                      </Button>
                      <Button onClick={() => setEditingLearningResources(false)}>{t('common.cancel')}</Button>
                    </Space>
                  </Space>
                ) : (
                  <Button icon={<EditOutlined />} onClick={startEditingLearningResources}>
                    {t('research.learningResourcesManage')}
                  </Button>
                )}
              </div>
            ) : null}

            <Divider titlePlacement="start">{t('research.researchObjects')}</Divider>
            <Spin spinning={researchObjectsLoading}>
              {researchObjects.length === 0 ? (
                <Typography.Text type="secondary">{t('research.researchObjectsEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={researchObjects}
                  renderItem={(researchObject) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-research-object"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/resources/${encodeURIComponent(researchObject.asset_id)}`)}
                        >
                          {t('research.openResource')}
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={(
                          <Space size={8} wrap>
                            <Typography.Text>{researchObject.title || t('research.researchObjectUntitled')}</Typography.Text>
                            <Tag>{t(`research.objectType.${researchObject.object_type}`, { defaultValue: researchObject.object_type })}</Tag>
                          </Space>
                        )}
                        description={(
                          <Space orientation="vertical" size={2}>
                            <Typography.Text type="secondary">
                              {t(`research.objectRelation.${researchObject.relation_type}`, { defaultValue: researchObject.relation_type })}
                            </Typography.Text>
                            {researchObject.reason ? (
                              <Typography.Text type="secondary">{researchObject.reason}</Typography.Text>
                            ) : null}
                          </Space>
                        )}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            <Divider titlePlacement="start">{t('research.projects')}</Divider>
            <Spin spinning={directionProjectsLoading}>
              {directionProjects.length === 0 ? (
                <Typography.Text type="secondary">{t('research.projectsEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={directionProjects}
                  renderItem={(project) => (
                    <List.Item
                      actions={[
                        <Button
                          key="open-project"
                          type="link"
                          size="small"
                          onClick={() => navigate(`/projects/${project.project_id}`)}
                        >
                          {t('research.openProject')}
                        </Button>,
                        ...(canMaintainDetail ? [
                          <Popconfirm
                            key="remove-project"
                            title={t('research.projectUnlinkConfirm')}
                            onConfirm={() => void removeProjectLink(project.project_id)}
                          >
                            <Button
                              type="text"
                              danger
                              size="small"
                              icon={<DeleteOutlined />}
                              loading={removingProjectId === project.project_id}
                              aria-label={t('common.delete')}
                            />
                          </Popconfirm>,
                        ] : []),
                      ]}
                    >
                      <List.Item.Meta
                        title={project.name}
                        description={project.reason || project.description || t('research.projectDescriptionEmpty')}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            {canMaintainDetail ? (
              <div style={{ marginTop: 16 }}>
                {linkingProject ? (
                  <Form form={projectLinkForm} layout="vertical" onFinish={() => void createProjectLink()}>
                    <Form.Item
                      name="project_id"
                      label={t('research.project')}
                      rules={[{ required: true, message: t('research.projectRequired') }]}
                    >
                      <Select
                        showSearch
                        optionFilterProp="label"
                        options={projectOptions}
                        placeholder={t('research.projectPlaceholder')}
                        notFoundContent={t('research.projectOptionsEmpty')}
                      />
                    </Form.Item>
                    <Form.Item name="reason" label={t('research.projectReason')}>
                      <Input.TextArea rows={2} placeholder={t('research.projectReasonPlaceholder')} />
                    </Form.Item>
                    <Space>
                      <Button type="primary" loading={linkingProjectSaving} onClick={() => void createProjectLink()}>
                        {t('research.projectLink')}
                      </Button>
                      <Button onClick={() => setLinkingProject(false)}>{t('common.cancel')}</Button>
                    </Space>
                  </Form>
                ) : (
                  <Button icon={<LinkOutlined />} onClick={openProjectLinkForm} disabled={projectOptions.length === 0}>
                    {t('research.projectLink')}
                  </Button>
                )}
              </div>
            ) : null}

            <Divider titlePlacement="start">{t('research.activities')}</Divider>
            <Spin spinning={activitiesLoading}>
              {activities.length === 0 ? (
                <Typography.Text type="secondary">{t('research.activitiesEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={activities}
                  renderItem={(activity) => (
                    <List.Item
                      actions={canCreate ? [
                        <Button
                          key="pin"
                          type="text"
                          size="small"
                          icon={<PushpinOutlined />}
                          loading={updatingActivityId === activity.id}
                          onClick={() => void updateActivityPresentation(
                            activity,
                            activity.is_pinned ? 'normal' : 'pinned',
                          )}
                        >
                          {t(activity.is_pinned ? 'research.activityUnpin' : 'research.activityPin')}
                        </Button>,
                        <Popconfirm
                          key="hide"
                          title={t('research.activityHideConfirm')}
                          onConfirm={() => void updateActivityPresentation(activity, 'hidden')}
                        >
                          <Button
                            type="text"
                            danger
                            size="small"
                            icon={<EyeInvisibleOutlined />}
                            loading={updatingActivityId === activity.id}
                          >
                            {t('research.activityHide')}
                          </Button>
                        </Popconfirm>,
                      ] : []}
                    >
                      <List.Item.Meta
                        avatar={<ClockCircleOutlined />}
                        title={(
                          <Space size={6}>
                            {activity.is_pinned ? <Tag color="blue">{t('research.activityPinned')}</Tag> : null}
                            <span>{t(`research.activity.${activity.action}`, { defaultValue: activity.action })}</span>
                          </Space>
                        )}
                        description={(
                          <Typography.Text type="secondary">
                            {activity.project_name} · {formatDateTime(activity.created_at, i18n.language)}
                          </Typography.Text>
                        )}
                      />
                    </List.Item>
                  )}
                />
              )}
            </Spin>

            <Divider titlePlacement="start">{t('research.relations')}</Divider>
            <Spin spinning={relationsLoading}>
              {relations.length === 0 ? (
                <Typography.Text type="secondary">{t('research.relationsEmpty')}</Typography.Text>
              ) : (
                <List
                  size="small"
                  dataSource={relations}
                  renderItem={(relation) => {
                    const relatedId = relation.direction_a_id === detail.id
                      ? relation.direction_b_id
                      : relation.direction_a_id;
                    const relatedDirection = directions.find((direction) => direction.id === relatedId);
                    return (
                      <List.Item
                        actions={canMaintainDetail ? [
                          <Popconfirm
                            key="remove"
                            title={t('research.relationRemoveConfirm')}
                            onConfirm={() => void removeRelation(relation.id)}
                          >
                            <Button type="text" danger size="small" icon={<DeleteOutlined />} aria-label={t('common.delete')} />
                          </Popconfirm>,
                        ] : []}
                      >
                        <List.Item.Meta
                          title={relatedDirection?.name || t('research.relatedDirectionUnavailable')}
                          description={relation.reason}
                        />
                      </List.Item>
                    );
                  }}
                />
              )}
            </Spin>

            {canMaintainDetail ? (
              <div style={{ marginTop: 16 }}>
                {linking ? (
                  <Form form={relationForm} layout="vertical" onFinish={() => void createRelation()}>
                    <Form.Item
                      name="target_direction_id"
                      label={t('research.relatedDirection')}
                      rules={[{ required: true, message: t('research.relatedDirectionRequired') }]}
                    >
                      <Select
                        showSearch
                        optionFilterProp="label"
                        options={relationOptions}
                        placeholder={t('research.relatedDirectionPlaceholder')}
                        notFoundContent={t('research.relatedDirectionEmpty')}
                      />
                    </Form.Item>
                    <Form.Item
                      name="reason"
                      label={t('research.relationReason')}
                      rules={[{ required: true, whitespace: true, message: t('research.relationReasonRequired') }]}
                    >
                      <Input.TextArea rows={2} placeholder={t('research.relationReasonPlaceholder')} />
                    </Form.Item>
                    <Space>
                      <Button type="primary" loading={linkingSaving} onClick={() => void createRelation()}>
                        {t('research.relationCreate')}
                      </Button>
                      <Button onClick={() => setLinking(false)}>{t('common.cancel')}</Button>
                    </Space>
                  </Form>
                ) : (
                  <Button icon={<LinkOutlined />} onClick={openRelationForm} disabled={relationOptions.length === 0}>
                    {t('research.relationCreate')}
                  </Button>
                )}
              </div>
            ) : null}
          </>
        ) : null}
      </Drawer>

      <Drawer
        title={t('research.createTitle')}
        width={560}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        extra={(
          <Space>
            <Button onClick={() => setCreateOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={creating} onClick={() => void createDirection()}>
              {t('common.create')}
            </Button>
          </Space>
        )}
      >
        <Typography.Paragraph type="secondary">
          {t('research.createHint')}
        </Typography.Paragraph>
        <Form form={form} layout="vertical" onFinish={() => void createDirection()}>
          <Form.Item name="name" label={t('research.name')} rules={[{ required: true, whitespace: true, max: 255 }]}>
            <Input autoFocus placeholder={t('research.namePlaceholder')} />
          </Form.Item>
          <Form.Item name="summary" label={t('research.summary')}>
            <Input.TextArea rows={3} placeholder={t('research.summaryPlaceholder')} />
          </Form.Item>
          <Form.Item name="background" label={t('research.background')}>
            <Input.TextArea rows={4} placeholder={t('research.backgroundPlaceholder')} />
          </Form.Item>
          <Form.Item name="scope" label={t('research.scope')}>
            <Input.TextArea rows={3} placeholder={t('research.scopePlaceholder')} />
          </Form.Item>
          <Form.Item name="owner_id" label={t('research.owner')}>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={directionOwners}
              placeholder={t('research.ownerPlaceholder')}
              notFoundContent={t('research.ownerLoadEmpty')}
            />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={t('research.editTitle')}
        width={560}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        extra={(
          <Space>
            <Button onClick={() => setEditOpen(false)}>{t('common.cancel')}</Button>
            <Button type="primary" loading={updating} onClick={() => void updateDirection()}>
              {t('common.save')}
            </Button>
          </Space>
        )}
      >
        <Form form={editForm} layout="vertical" onFinish={() => void updateDirection()}>
          <Form.Item name="name" label={t('research.name')} rules={[{ required: true, whitespace: true, max: 255 }]}>
            <Input />
          </Form.Item>
          <Form.Item name="summary" label={t('research.summary')}>
            <Input.TextArea rows={3} placeholder={t('research.summaryPlaceholder')} />
          </Form.Item>
          <Form.Item name="background" label={t('research.background')}>
            <Input.TextArea rows={4} placeholder={t('research.backgroundPlaceholder')} />
          </Form.Item>
          <Form.Item name="scope" label={t('research.scope')}>
            <Input.TextArea rows={3} placeholder={t('research.scopePlaceholder')} />
          </Form.Item>
          {canCreate ? (
            <Form.Item name="owner_id" label={t('research.owner')}>
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                options={directionOwners}
                placeholder={t('research.ownerPlaceholder')}
                notFoundContent={t('research.ownerLoadEmpty')}
              />
            </Form.Item>
          ) : null}
          <Form.Item name="last_confirmed_at" label={t('research.lastConfirmed')}>
            <Input type="datetime-local" />
          </Form.Item>
          <Form.Item name="review_due_at" label={t('research.reviewDue')}>
            <Input type="datetime-local" />
          </Form.Item>
        </Form>
      </Drawer>

      <Drawer
        title={t('research.mergeTitle')}
        width={560}
        open={mergeOpen}
        onClose={() => setMergeOpen(false)}
        extra={(
          <Space>
            <Button onClick={() => setMergeOpen(false)}>{t('common.cancel')}</Button>
            <Button danger loading={merging} onClick={() => void confirmMerge()}>{t('research.merge')}</Button>
          </Space>
        )}
      >
        <Alert type="warning" showIcon message={t('research.mergeWarning')} style={{ marginBottom: 16 }} />
        <Form form={mergeForm} layout="vertical" onFinish={() => void confirmMerge()}>
          <Form.Item
            name="target_direction_id"
            label={t('research.mergeTarget')}
            rules={[{ required: true, message: t('research.mergeTargetRequired') }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={directions
                .filter((direction) => direction.id !== detail?.id)
                .map((direction) => ({ value: direction.id, label: direction.name }))}
              placeholder={t('research.mergeTargetPlaceholder')}
              notFoundContent={t('research.mergeTargetEmpty')}
            />
          </Form.Item>
          <Form.Item
            name="reason"
            label={t('research.mergeReason')}
            rules={[{ required: true, whitespace: true, message: t('research.mergeReasonRequired') }]}
          >
            <Input.TextArea rows={3} placeholder={t('research.mergeReasonPlaceholder')} />
          </Form.Item>
        </Form>
      </Drawer>
    </PageContainer>
  );
}
