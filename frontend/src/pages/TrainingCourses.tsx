import { ApartmentOutlined, ArrowLeftOutlined, BookOutlined, DeleteOutlined, EditOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Empty, Form, Input, InputNumber, List, Modal, Popconfirm, Select, Space, Spin, Steps, Tag, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import apiClient from '../services/api-client';

const { Paragraph, Text, Title } = Typography;

type ContentLanguage = 'auto' | 'zh-CN' | 'en-US';

interface AssetOption {
  id: string;
  title: string;
  has_source?: boolean;
  current_revision_id?: string | null;
  source_processing_state?: string | null;
}

interface Member {
  id: string;
  username: string;
  display_name?: string | null;
}

interface CourseAsset {
  id: string;
  research_asset_id: string;
  title: string;
}

interface KnowledgePoint {
  id: string;
  unit_id?: string | null;
  title: string;
  description: string;
  evidence_excerpt: string;
  review_status: string;
  assessment_question?: {
    question_type: 'single_choice' | 'short_answer';
    prompt: string;
    options?: Array<{ id: string; text: string }> | null;
  } | null;
}

interface CourseAssignee {
  user_id: string;
  display_name: string;
  status: string;
  requires_retraining?: boolean;
}

interface CourseUnit {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  pass_score: number;
  course_asset_ids: string[];
  knowledge_points: KnowledgePoint[];
  lesson?: {
    id: string;
    outline: string[];
    lesson_markdown: string;
    evidence: Array<{ excerpt: string }>;
    status: string;
  } | null;
}

interface CourseModule {
  id: string;
  title: string;
  description?: string | null;
  status: string;
  revision_number: number;
  units: CourseUnit[];
  assignees: CourseAssignee[];
}

interface Course {
  id: string;
  name: string;
  description?: string | null;
  content_language: ContentLanguage;
  lifecycle_status: string;
  version: {
    id: string;
    status: string;
    assets: CourseAsset[];
    knowledge_points: KnowledgePoint[];
    assignees: CourseAssignee[];
    modules: CourseModule[];
  };
}

export default function TrainingCourses() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [courses, setCourses] = useState<Course[]>([]);
  const [assets, setAssets] = useState<AssetOption[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedCourse, setSelectedCourse] = useState<Course>();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showCourseForm, setShowCourseForm] = useState(false);
  const [showEditCourseForm, setShowEditCourseForm] = useState(false);
  const [editingPoint, setEditingPoint] = useState<KnowledgePoint>();
  const [editingLessonKey, setEditingLessonKey] = useState<string>();
  const [lessonDraft, setLessonDraft] = useState('');
  const [savingLesson, setSavingLesson] = useState(false);
  const [generatingLessonKey, setGeneratingLessonKey] = useState<string>();
  const [showModuleForm, setShowModuleForm] = useState(false);
  const [editingModule, setEditingModule] = useState<CourseModule>();
  const [unitModule, setUnitModule] = useState<CourseModule>();
  const [courseForm] = Form.useForm();
  const [editCourseForm] = Form.useForm();
  const [editPointForm] = Form.useForm();
  const [moduleForm] = Form.useForm();
  const [editModuleForm] = Form.useForm();
  const [unitForm] = Form.useForm();

  const loadCourses = async (selectCourseId?: string) => {
    const { data } = await apiClient.get<Course[]>('/training/courses');
    setCourses(data);
    const next = selectCourseId
      ? data.find((course) => course.id === selectCourseId)
      : data.find((course) => course.id === selectedCourse?.id);
    setSelectedCourse(next ?? data[0]);
  };

  useEffect(() => {
    Promise.all([
      loadCourses(),
      apiClient.get<AssetOption[]>('/library/assets'),
      apiClient.get<Member[]>('/auth/users'),
    ])
      .then(([, assetResponse, memberResponse]) => {
        setAssets(assetResponse.data);
        setMembers(memberResponse.data);
      })
      .catch(() => message.error(t('trainingCourses.loadFailed')))
      .finally(() => setLoading(false));
  }, []);

  const readyAssets = useMemo(
    () => assets.filter((asset) => asset.has_source && asset.current_revision_id && asset.source_processing_state === 'ready'),
    [assets],
  );

  const createCourse = async (values: { name: string; description?: string; content_language: ContentLanguage }) => {
    setCreating(true);
    try {
      const { data } = await apiClient.post<Course>('/training/courses', values);
      setShowCourseForm(false);
      courseForm.resetFields();
      await loadCourses(data.id);
      message.success(t('trainingCourses.created'));
    } catch {
      message.error(t('trainingCourses.createFailed'));
    } finally {
      setCreating(false);
    }
  };

  const updateCourse = async (values: { name: string; description?: string; content_language: ContentLanguage }) => {
    if (!selectedCourse) return;
    setCreating(true);
    try {
      await apiClient.put(`/training/courses/${selectedCourse.id}`, values);
      setShowEditCourseForm(false);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.courseUpdated'));
    } catch {
      message.error(t('trainingCourses.courseUpdateFailed'));
    } finally {
      setCreating(false);
    }
  };

  const bindAssets = async (assetIds: string[]) => {
    if (!selectedCourse) return;
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/assets`, { research_asset_ids: assetIds });
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.assetBound'));
    } catch (error: unknown) {
      const status = (error as { response?: { status?: number } }).response?.status;
      message.error(t(status === 403 ? 'trainingCourses.assetAccessDenied' : 'trainingCourses.assetBindFailed'));
    }
  };

  const removeCourseAsset = async (courseAssetId: string) => {
    if (!selectedCourse) return;
    try {
      await apiClient.delete(`/training/courses/${selectedCourse.id}/assets/${courseAssetId}`);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.assetRemoved'));
    } catch {
      message.error(t('trainingCourses.assetRemoveFailed'));
    }
  };

  const approveKnowledgePoint = async (knowledgePointId: string) => {
    if (!selectedCourse) return;
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/knowledge-points/${knowledgePointId}/approve`);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.pointApproved'));
    } catch {
      message.error(t('trainingCourses.pointApproveFailed'));
    }
  };

  const updateKnowledgePoint = async (values: { title: string; description: string }) => {
    if (!selectedCourse || !editingPoint) return;
    setCreating(true);
    try {
      await apiClient.put(`/training/courses/${selectedCourse.id}/knowledge-points/${editingPoint.id}`, values);
      setEditingPoint(undefined);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.pointUpdated'));
    } catch {
      message.error(t('trainingCourses.pointUpdateFailed'));
    } finally {
      setCreating(false);
    }
  };

  const discardKnowledgePoint = async (knowledgePointId: string) => {
    if (!selectedCourse) return;
    try {
      await apiClient.delete(`/training/courses/${selectedCourse.id}/knowledge-points/${knowledgePointId}`);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.pointDiscarded'));
    } catch {
      message.error(t('trainingCourses.pointDiscardFailed'));
    }
  };

  const publishCourse = async () => {
    if (!selectedCourse) return;
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/publish`);
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.published'));
    } catch {
      message.error(t('trainingCourses.publishFailed'));
    }
  };

  const createModule = async (values: { title: string; description?: string }) => {
    if (!selectedCourse) return;
    setCreating(true);
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/modules`, values);
      setShowModuleForm(false);
      moduleForm.resetFields();
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.moduleCreated'));
    } catch {
      message.error(t('trainingCourses.structureFailed'));
    } finally {
      setCreating(false);
    }
  };

  const updateModule = async (values: { title: string; description?: string }) => {
    if (!selectedCourse || !editingModule) return;
    setCreating(true);
    try {
      await apiClient.put(`/training/courses/${selectedCourse.id}/modules/${editingModule.id}`, values);
      setEditingModule(undefined);
      editModuleForm.resetFields();
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.moduleUpdated'));
    } catch {
      message.error(t('trainingCourses.structureFailed'));
    } finally {
      setCreating(false);
    }
  };

  const generateCourseStructure = async () => {
    if (!selectedCourse) return;
    setCreating(true);
    try {
      await apiClient.post(
        `/training/courses/${selectedCourse.id}/modules/generate`,
        undefined,
        { timeout: 120000 },
      );
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.structureGenerated'));
    } catch {
      message.error(t('trainingCourses.structureGenerateFailed'));
    } finally {
      setCreating(false);
    }
  };

  const createUnit = async (values: { title: string; description?: string; pass_score: number }) => {
    if (!selectedCourse || !unitModule) return;
    setCreating(true);
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/modules/${unitModule.id}/units`, values);
      setUnitModule(undefined);
      unitForm.resetFields();
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.unitCreated'));
    } catch {
      message.error(t('trainingCourses.structureFailed'));
    } finally {
      setCreating(false);
    }
  };

  const bindUnitAssets = async (moduleId: string, unitId: string, courseAssetIds: string[]) => {
    if (!selectedCourse) return;
    try {
      await apiClient.put(`/training/courses/${selectedCourse.id}/modules/${moduleId}/units/${unitId}/assets`, { course_asset_ids: courseAssetIds });
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.unitMaterialsBound'));
    } catch {
      message.error(t('trainingCourses.structureFailed'));
    }
  };

  const generateUnitLesson = async (moduleId: string, unitId: string) => {
    if (!selectedCourse) return;
    const lessonKey = `${moduleId}:${unitId}`;
    setGeneratingLessonKey(lessonKey);
    try {
      await apiClient.post(`/training/courses/${selectedCourse.id}/modules/${moduleId}/units/${unitId}/lesson/generate`, undefined, { timeout: 120000 });
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.lessonGenerated'));
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      message.error(
        detail
          ? `${t('trainingCourses.lessonGenerateFailed')}: ${detail}`
          : t('trainingCourses.lessonGenerateFailed'),
      );
    } finally {
      setGeneratingLessonKey(undefined);
    }
  };

  const approveUnitLesson = async (moduleId: string, unitId: string) => {
    if (!selectedCourse) return;
    await apiClient.post(`/training/courses/${selectedCourse.id}/modules/${moduleId}/units/${unitId}/lesson/approve`);
    await loadCourses(selectedCourse.id);
    message.success(t('trainingCourses.lessonApproved'));
  };

  const updateUnitLesson = async (moduleId: string, unitId: string) => {
    if (!selectedCourse || !lessonDraft.trim()) return;
    setSavingLesson(true);
    try {
      await apiClient.put(
        `/training/courses/${selectedCourse.id}/modules/${moduleId}/units/${unitId}/lesson`,
        { lesson_markdown: lessonDraft },
      );
      setEditingLessonKey(undefined);
      setLessonDraft('');
      await loadCourses(selectedCourse.id);
      message.success(t('trainingCourses.lessonUpdated'));
    } catch {
      message.error(t('trainingCourses.lessonUpdateFailed'));
    } finally {
      setSavingLesson(false);
    }
  };

  const assignModule = async (moduleId: string, traineeIds: string[]) => {
    if (!selectedCourse || !traineeIds.length) return;
    await apiClient.post(`/training/courses/${selectedCourse.id}/modules/${moduleId}/assignments`, { trainee_ids: traineeIds });
    await loadCourses(selectedCourse.id);
    message.success(t('trainingCourses.moduleAssigned'));
  };

  const assignCourse = async (traineeIds: string[]) => {
    if (!selectedCourse) return;
    try {
      const { data } = await apiClient.post<{ assignments: unknown[]; skipped_trainee_ids: string[] }>(
        `/training/courses/${selectedCourse.id}/assignments/batch`, { trainee_ids: traineeIds },
      );
      message.success(t('trainingCourses.assignedMany', { count: data.assignments.length }));
      if (data.skipped_trainee_ids.length) message.warning(t('trainingCourses.assignmentSkipped', { count: data.skipped_trainee_ids.length }));
      await loadCourses(selectedCourse.id);
    } catch {
      message.error(t('trainingCourses.assignFailed'));
    }
  };

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '200px auto' }} />;
  }

  return (
    <div style={{ maxWidth: 1160, margin: '0 auto', padding: '40px 24px 64px' }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/training')} style={{ marginBottom: 20 }}>
        {t('trainingCourses.backToDemo')}
      </Button>
      <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 28 }}>
        <Title level={2} style={{ margin: 0 }}>{t('trainingCourses.title')}</Title>
        <Paragraph type="secondary" style={{ maxWidth: 760, margin: 0 }}>
          {t('trainingCourses.description')}
        </Paragraph>
      </Space>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 0.8fr) minmax(0, 2fr)', gap: 24 }}>
        <Card
          title={t('trainingCourses.courseList')}
          extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setShowCourseForm(true)}>{t('trainingCourses.newCourse')}</Button>}
        >
          {courses.length === 0 ? <Empty description={t('trainingCourses.emptyCourses')} /> : (
            <List
              dataSource={courses}
              renderItem={(course) => (
                <List.Item
                  onClick={() => setSelectedCourse(course)}
                  style={{ cursor: 'pointer', paddingInline: 8, background: selectedCourse?.id === course.id ? '#e6f4ff' : undefined }}
                >
                  <List.Item.Meta title={course.name} description={<Tag color={course.version.status === 'published' ? 'green' : 'gold'}>{t(`trainingCourses.status.${course.version.status}`)}</Tag>} />
                </List.Item>
              )}
            />
          )}
        </Card>

        {selectedCourse ? (
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            <Card
              title={selectedCourse.name}
              extra={(
                <Space>
                  {selectedCourse.version.status === 'draft' && (
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        editCourseForm.setFieldsValue({
                          name: selectedCourse.name,
                          description: selectedCourse.description,
                          content_language: selectedCourse.content_language,
                        });
                        setShowEditCourseForm(true);
                      }}
                    >
                      {t('trainingCourses.editCourse')}
                    </Button>
                  )}
                  <Tag color={selectedCourse.version.status === 'published' ? 'green' : 'gold'}>{t(`trainingCourses.status.${selectedCourse.version.status}`)}</Tag>
                  <Tag>{t(`trainingCourses.contentLanguage.${selectedCourse.content_language}`)}</Tag>
                </Space>
              )}
            >
              {selectedCourse.description && <Paragraph>{selectedCourse.description}</Paragraph>}
              <Steps
                size="small"
                current={selectedCourse.version.status === 'published' ? 2 : selectedCourse.version.knowledge_points.length ? 1 : 0}
                items={[{ title: t('trainingCourses.stepSource') }, { title: t('trainingCourses.stepKnowledge') }, { title: t('trainingCourses.stepPublish') }]}
              />
            </Card>

            <Card title={t('trainingCourses.materials')}>
              {selectedCourse.version.status === 'draft' && (
                <Select
                  mode="multiple"
                  showSearch
                  placeholder={t('trainingCourses.materialPlaceholder')}
                  optionFilterProp="label"
                  options={readyAssets
                    .filter((asset) => !selectedCourse.version.assets.some((bound) => bound.research_asset_id === asset.id))
                    .map((asset) => ({ value: asset.id, label: asset.title }))}
                  onChange={(assetIds) => {
                    if (assetIds.length > 0) void bindAssets(assetIds);
                  }}
                  style={{ width: '100%', marginBottom: 16 }}
                />
              )}
              {selectedCourse.version.assets.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('trainingCourses.noMaterials')} /> : (
                <List
                  dataSource={selectedCourse.version.assets}
                  renderItem={(asset) => (
                    <List.Item
                      actions={selectedCourse.version.status === 'draft' ? [
                        <Popconfirm
                          key="remove"
                          title={t('trainingCourses.assetRemoveConfirm')}
                          description={t('trainingCourses.assetRemoveDescription')}
                          onConfirm={() => void removeCourseAsset(asset.id)}
                        >
                          <Button danger type="link" icon={<DeleteOutlined />}>{t('trainingCourses.removeAsset')}</Button>
                        </Popconfirm>,
                      ] : undefined}
                    >
                      <BookOutlined />&nbsp; {asset.title}
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card
              title={t('trainingCourses.courseStructure')}
              extra={(
                <Space wrap>
                  <Popconfirm
                    title={t('trainingCourses.generateStructureConfirm')}
                    description={t('trainingCourses.generateStructureDescription')}
                    onConfirm={() => void generateCourseStructure()}
                    disabled={!selectedCourse.version.assets.length}
                  >
                    <Button
                      icon={<ApartmentOutlined />}
                      loading={creating}
                      disabled={!selectedCourse.version.assets.length}
                    >
                      {t('trainingCourses.generateStructure')}
                    </Button>
                  </Popconfirm>
                  <Button icon={<PlusOutlined />} onClick={() => setShowModuleForm(true)}>
                    {t('trainingCourses.addModule')}
                  </Button>
                </Space>
              )}
            >
              {selectedCourse.version.status === 'published' && (
                <Alert
                  type="warning"
                  showIcon
                  message={t('trainingCourses.publishedEditingTitle')}
                  description={t('trainingCourses.publishedEditingDescription')}
                  style={{ marginBottom: 16 }}
                />
              )}
              {selectedCourse.version.modules.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('trainingCourses.noModules')} /> : (
                <List
                  dataSource={selectedCourse.version.modules}
                  renderItem={(module) => (
                    <List.Item>
                      <div style={{ width: '100%' }}>
                        <Space wrap style={{ marginBottom: 10 }}>
                          <Text strong>{module.title}</Text><Tag>{module.units.length} {t('trainingCourses.units')}</Tag>
                          {module.revision_number > 1 && <Tag>{t('trainingCourses.moduleRevision', { revision: module.revision_number })}</Tag>}
                          {module.assignees.map((assignee) => (
                            <Tag color={assignee.requires_retraining ? 'orange' : 'blue'} key={assignee.user_id}>
                              {assignee.display_name}
                              {assignee.requires_retraining ? ` · ${t('trainingCourses.retrainingRequired')}` : ''}
                            </Tag>
                          ))}
                          <Button
                            type="link"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingModule(module);
                              editModuleForm.setFieldsValue({
                                title: module.title,
                                description: module.description,
                              });
                            }}
                          >
                            {t('trainingCourses.editModule')}
                          </Button>
                        </Space>
                        {module.description && <Paragraph type="secondary">{module.description}</Paragraph>}
                        <Space direction="vertical" size={4} style={{ marginBottom: 12 }}>
                          <Select
                            mode="multiple"
                            placeholder={t('trainingCourses.assignModule')}
                            options={members.filter((member) => !module.assignees.some((assignee) => assignee.user_id === member.id)).map((member) => ({ value: member.id, label: member.display_name || member.username }))}
                            onChange={(ids) => { if (ids.length) void assignModule(module.id, ids); }}
                            style={{ minWidth: 320 }}
                          />
                          <Text type="secondary">{t('trainingCourses.moduleAssignmentHint')}</Text>
                        </Space>
                        <List
                          size="small"
                          dataSource={module.units}
                          locale={{ emptyText: t('trainingCourses.noUnits') }}
                          renderItem={(unit) => (
                            <List.Item>
                              <Space direction="vertical" style={{ width: '100%' }}>
                                <Space wrap><Text strong>{unit.title}</Text><Tag color={unit.status === 'approved' ? 'green' : 'gold'}>{t(`trainingCourses.unitStatus.${unit.status}`)}</Tag></Space>
                                <Space wrap>
                                  <Select
                                    mode="multiple"
                                    placeholder={t('trainingCourses.unitMaterials')}
                                    value={unit.course_asset_ids}
                                    options={selectedCourse.version.assets.map((asset) => ({ value: asset.id, label: asset.title }))}
                                    onChange={(ids) => void bindUnitAssets(module.id, unit.id, ids)}
                                    style={{ minWidth: 260 }}
                                  />
                                  <Button
                                    loading={generatingLessonKey === `${module.id}:${unit.id}`}
                                    disabled={
                                      !unit.course_asset_ids.length
                                      || (!!generatingLessonKey && generatingLessonKey !== `${module.id}:${unit.id}`)
                                    }
                                    onClick={() => void generateUnitLesson(module.id, unit.id)}
                                  >
                                    {t(unit.lesson
                                      ? 'trainingCourses.regenerateLesson'
                                      : 'trainingCourses.generateLesson')}
                                  </Button>
                                  {unit.lesson?.status === 'pending' && (
                                    <>
                                      <Button
                                        icon={<EditOutlined />}
                                        onClick={() => {
                                          setEditingLessonKey(`${module.id}:${unit.id}`);
                                          setLessonDraft(unit.lesson?.lesson_markdown || '');
                                        }}
                                      >
                                        {t('trainingCourses.editLesson')}
                                      </Button>
                                      <Button type="primary" onClick={() => void approveUnitLesson(module.id, unit.id)}>{t('trainingCourses.approveLesson')}</Button>
                                    </>
                                  )}
                                </Space>
                                {editingLessonKey === `${module.id}:${unit.id}` && (
                                  <div style={{ width: '100%', padding: '14px 16px', background: '#fafafa', borderRadius: 8 }}>
                                    <Space direction="vertical" size={10} style={{ width: '100%' }}>
                                      <div>
                                        <Text strong>{t('trainingCourses.lessonEditorTitle')}</Text>
                                        <br />
                                        <Text type="secondary">{t('trainingCourses.lessonEditorHint')}</Text>
                                      </div>
                                      <Input.TextArea
                                        value={lessonDraft}
                                        onChange={(event) => setLessonDraft(event.target.value)}
                                        rows={14}
                                        showCount
                                        maxLength={50000}
                                      />
                                      <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
                                        <Button onClick={() => { setEditingLessonKey(undefined); setLessonDraft(''); }}>
                                          {t('common.cancel')}
                                        </Button>
                                        <Button
                                          type="primary"
                                          loading={savingLesson}
                                          disabled={!lessonDraft.trim()}
                                          onClick={() => void updateUnitLesson(module.id, unit.id)}
                                        >
                                          {t('trainingCourses.saveLesson')}
                                        </Button>
                                      </Space>
                                    </Space>
                                  </div>
                                )}
                                {unit.lesson && (
                                  <details>
                                    <summary>{t('trainingCourses.previewLesson')}</summary>
                                    <div style={{ marginTop: 10 }}>
                                      <Text strong>{t('trainingCourses.lessonOutline')}</Text>
                                      <ol>{unit.lesson.outline.map((item) => <li key={item}>{item}</li>)}</ol>
                                      <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', background: '#fafafa', padding: 12 }}>{unit.lesson.lesson_markdown}</pre>
                                    </div>
                                  </details>
                                )}
                                {unit.knowledge_points.length > 0 && (
                                  <div style={{ borderLeft: '3px solid #1677ff', paddingLeft: 14 }}>
                                    <Text strong>{t('trainingCourses.unitKnowledgePackage')}</Text>
                                    <List
                                      size="small"
                                      dataSource={unit.knowledge_points}
                                      renderItem={(point) => (
                                        <List.Item
                                          actions={point.review_status === 'pending' && selectedCourse.version.status === 'draft'
                                            ? [
                                              <Button key="edit" size="small" icon={<EditOutlined />} onClick={() => { setEditingPoint(point); editPointForm.setFieldsValue(point); }}>{t('trainingCourses.editPoint')}</Button>,
                                              <Popconfirm key="discard" title={t('trainingCourses.discardPointConfirm')} onConfirm={() => void discardKnowledgePoint(point.id)}><Button danger size="small" icon={<DeleteOutlined />}>{t('trainingCourses.discardPoint')}</Button></Popconfirm>,
                                              <Button key="approve" type="primary" size="small" onClick={() => void approveKnowledgePoint(point.id)}>{t('trainingCourses.approvePoint')}</Button>,
                                            ]
                                            : undefined}
                                        >
                                          <List.Item.Meta
                                            title={<Space size={8}>{point.title}<Tag color={point.review_status === 'approved' ? 'green' : 'gold'}>{t(`trainingCourses.review.${point.review_status}`)}</Tag></Space>}
                                            description={(
                                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                                <Text>{point.description}</Text>
                                                <Text type="secondary">{t('trainingCourses.evidence')}: {point.evidence_excerpt}</Text>
                                                {point.assessment_question && (
                                                  <div style={{ background: '#fafafa', padding: '8px 10px', borderRadius: 6 }}>
                                                    <Tag>{t(`trainingCourses.questionType.${point.assessment_question.question_type}`)}</Tag>
                                                    <Text>{point.assessment_question.prompt}</Text>
                                                    {point.assessment_question.options?.length ? (
                                                      <ol type="A" style={{ margin: '6px 0 0 20px' }}>
                                                        {point.assessment_question.options.map((option) => <li key={option.id}>{option.text}</li>)}
                                                      </ol>
                                                    ) : null}
                                                  </div>
                                                )}
                                              </Space>
                                            )}
                                          />
                                        </List.Item>
                                      )}
                                    />
                                  </div>
                                )}
                              </Space>
                            </List.Item>
                          )}
                        />
                        <Button type="dashed" size="small" onClick={() => setUnitModule(module)}>{t('trainingCourses.addUnit')}</Button>
                      </div>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            {selectedCourse.version.status === 'draft' ? (
              <Alert
                type="info"
                showIcon
                message={t('trainingCourses.publishHint')}
                action={<Button type="primary" onClick={publishCourse}>{t('trainingCourses.publish')}</Button>}
              />
            ) : (
              <Card title={t('trainingCourses.assignments')}>
                {selectedCourse.version.assignees.length > 0 && (
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Text type="secondary">{t('trainingCourses.assignedMembers')}:</Text>
                    {selectedCourse.version.assignees.map((assignee) => (
                      <Tag key={assignee.user_id} color="blue">
                        {assignee.display_name} · {t(`trainingCourses.assignmentStatus.${assignee.status}`)}
                        <Button type="link" size="small" style={{ paddingInline: 6 }} onClick={() => navigate(`/training/reports/${assignee.user_id}`)}>
                          {t('trainingCourses.viewReport')}
                        </Button>
                      </Tag>
                    ))}
                  </Space>
                )}
                <Select
                  mode="multiple"
                  showSearch
                  placeholder={t('trainingCourses.assignPlaceholder')}
                  optionFilterProp="label"
                  options={members
                    .filter((member) => !selectedCourse.version.assignees.some((assignee) => assignee.user_id === member.id))
                    .map((member) => ({ value: member.id, label: member.display_name || member.username }))}
                  onChange={(ids) => { if (ids.length) void assignCourse(ids); }}
                  suffixIcon={<SendOutlined />}
                  style={{ width: '100%' }}
                />
              </Card>
            )}
          </Space>
        ) : <Card><Empty description={t('trainingCourses.selectCourse')} /></Card>}
      </div>

      <Modal title={t('trainingCourses.newCourse')} open={showCourseForm} onCancel={() => setShowCourseForm(false)} onOk={() => courseForm.submit()} confirmLoading={creating}>
        <Form form={courseForm} layout="vertical" initialValues={{ content_language: 'auto' }} onFinish={createCourse}>
          <Form.Item name="name" label={t('trainingCourses.courseName')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.courseDescription')}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item
            name="content_language"
            label={t('trainingCourses.contentLanguageLabel')}
            extra={t('trainingCourses.contentLanguageHint')}
            rules={[{ required: true }]}
          >
            <Select options={(['auto', 'zh-CN', 'en-US'] as ContentLanguage[]).map((value) => ({ value, label: t(`trainingCourses.contentLanguage.${value}`) }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('trainingCourses.editCourse')} open={showEditCourseForm} onCancel={() => setShowEditCourseForm(false)} onOk={() => editCourseForm.submit()} confirmLoading={creating}>
        <Form form={editCourseForm} layout="vertical" onFinish={updateCourse}>
          <Form.Item name="name" label={t('trainingCourses.courseName')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.courseDescription')}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item
            name="content_language"
            label={t('trainingCourses.contentLanguageLabel')}
            extra={t('trainingCourses.contentLanguageHint')}
            rules={[{ required: true }]}
          >
            <Select options={(['auto', 'zh-CN', 'en-US'] as ContentLanguage[]).map((value) => ({ value, label: t(`trainingCourses.contentLanguage.${value}`) }))} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={t('trainingCourses.editPoint')} open={!!editingPoint} onCancel={() => setEditingPoint(undefined)} onOk={() => editPointForm.submit()} confirmLoading={creating}>
        <Form form={editPointForm} layout="vertical" onFinish={updateKnowledgePoint}>
          <Form.Item name="title" label={t('trainingCourses.pointTitle')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.pointDescription')} rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={t('trainingCourses.addModule')} open={showModuleForm} onCancel={() => setShowModuleForm(false)} onOk={() => moduleForm.submit()} confirmLoading={creating}>
        <Form form={moduleForm} layout="vertical" onFinish={createModule}>
          <Form.Item name="title" label={t('trainingCourses.moduleTitle')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.moduleDescription')}><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
      <Modal title={t('trainingCourses.editModule')} open={!!editingModule} onCancel={() => setEditingModule(undefined)} onOk={() => editModuleForm.submit()} confirmLoading={creating}>
        <Form form={editModuleForm} layout="vertical" onFinish={updateModule}>
          <Form.Item name="title" label={t('trainingCourses.moduleTitle')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.moduleDescription')}><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
      <Modal title={t('trainingCourses.addUnit')} open={!!unitModule} onCancel={() => setUnitModule(undefined)} onOk={() => unitForm.submit()} confirmLoading={creating}>
        <Form form={unitForm} layout="vertical" initialValues={{ pass_score: 80 }} onFinish={createUnit}>
          <Form.Item name="title" label={t('trainingCourses.unitTitle')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label={t('trainingCourses.unitDescription')}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="pass_score" label={t('trainingCourses.unitPassScore')} rules={[{ required: true }]}><InputNumber min={1} max={100} addonAfter="%" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
