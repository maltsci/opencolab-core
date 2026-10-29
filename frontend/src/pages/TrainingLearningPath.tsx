import { ArrowLeftOutlined, BookOutlined, FileTextOutlined, LockOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Empty, Input, List, Radio, Space, Spin, Steps, Tag, Typography, message } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import apiClient from '../services/api-client';
import PdfPreviewModal from '../components/library/PdfPreviewModal';

const { Paragraph, Text, Title } = Typography;

interface Course {
  id: string;
  name: string;
  description?: string | null;
  version: {
    assets: Array<{ id: string; research_asset_id: string; source_id: string | null; title: string }>;
    knowledge_points: Array<{
      id: string;
      title: string;
      description: string;
      evidence_excerpt: string;
      course_asset_id: string;
      origin_chunk_ref: string | null;
    }>;
  };
}

interface PracticeAttempt {
  id: string;
  knowledge_point_id: string;
  question_text: string;
  question_type: 'single_choice' | 'short_answer';
  options: Array<{ id: string; text: string }> | null;
  status: string;
  answer_text: string | null;
  verdict: string | null;
  score: number | null;
  feedback_text: string | null;
}

interface NextStep {
  knowledge_point_id: string | null;
  reason: 'not_started' | 'needs_review' | 'complete';
}

interface FinalAssessment {
  id: string;
  question_text: string;
  status: string;
  score: number | null;
  feedback_text: string | null;
}

export default function TrainingLearningPath() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { assignmentId } = useParams();
  const [course, setCourse] = useState<Course>();
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempts, setAttempts] = useState<Record<string, PracticeAttempt>>({});
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [workingPointId, setWorkingPointId] = useState<string>();
  const [nextStep, setNextStep] = useState<NextStep>();
  const [nextStepLoading, setNextStepLoading] = useState(true);
  const [assessment, setAssessment] = useState<FinalAssessment>();
  const [assessmentAnswer, setAssessmentAnswer] = useState('');
  const [assessmentWorking, setAssessmentWorking] = useState(false);
  const [preview, setPreview] = useState<{ sourceId: string; title: string; evidenceExcerpt?: string }>();

  useEffect(() => {
    if (!assignmentId) return;
    apiClient.get<Course>(`/training/assignments/${assignmentId}/learning`)
      .then(({ data }) => setCourse(data))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, [assignmentId]);

  const loadNextStep = async () => {
    if (!assignmentId) return;
    setNextStepLoading(true);
    try {
      const { data } = await apiClient.get<NextStep>(`/training/assignments/${assignmentId}/next-step`);
      setNextStep(data);
    } catch {
      setNextStep(undefined);
    } finally {
      setNextStepLoading(false);
    }
  };

  useEffect(() => {
    void loadNextStep();
  }, [assignmentId]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '200px auto' }} />;
  if (failed || !course) return <Empty description={t('trainingPath.loadFailed')} style={{ marginTop: 160 }} />;

  const startPractice = async (knowledgePointId: string) => {
    if (!assignmentId) return;
    setWorkingPointId(knowledgePointId);
    try {
      const { data } = await apiClient.post<PracticeAttempt>(`/training/assignments/${assignmentId}/practice`, { knowledge_point_id: knowledgePointId });
      setAttempts((current) => ({ ...current, [knowledgePointId]: data }));
    } catch {
      message.error(t('trainingPath.practiceStartFailed'));
    } finally {
      setWorkingPointId(undefined);
    }
  };

  const submitAnswer = async (knowledgePointId: string) => {
    const attempt = attempts[knowledgePointId];
    const answer = answers[knowledgePointId]?.trim();
    if (!attempt || !answer) return;
    setWorkingPointId(knowledgePointId);
    try {
      const { data } = await apiClient.post<PracticeAttempt>(`/training/practice/${attempt.id}/answer`, { answer_text: answer }, { timeout: 120000 });
      setAttempts((current) => ({ ...current, [knowledgePointId]: data }));
      await loadNextStep();
    } catch {
      message.error(t('trainingPath.practiceAnswerFailed'));
    } finally {
      setWorkingPointId(undefined);
    }
  };

  const startAssessment = async () => {
    if (!assignmentId) return;
    setAssessmentWorking(true);
    try {
      const { data } = await apiClient.post<FinalAssessment>(`/training/assignments/${assignmentId}/final-assessment`);
      setAssessment(data);
    } catch {
      message.error(t('trainingPath.assessmentStartFailed'));
    } finally {
      setAssessmentWorking(false);
    }
  };

  const submitAssessment = async () => {
    if (!assessment || !assessmentAnswer.trim()) return;
    setAssessmentWorking(true);
    try {
      const { data } = await apiClient.post<FinalAssessment>(`/training/final-assessments/${assessment.id}/answer`, { answer_text: assessmentAnswer.trim() }, { timeout: 120000 });
      setAssessment(data);
      await loadNextStep();
    } catch {
      message.error(t('trainingPath.assessmentAnswerFailed'));
    } finally {
      setAssessmentWorking(false);
    }
  };

  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '40px 24px 64px' }}>
      <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/training')} style={{ marginBottom: 20 }}>
        {t('trainingPath.back')}
      </Button>
      <Space direction="vertical" size={8} style={{ width: '100%', marginBottom: 28 }}>
        <Tag color="blue" style={{ width: 'fit-content' }}>{t('trainingPath.badge')}</Tag>
        <Title level={2} style={{ margin: 0 }}>{course.name}</Title>
        {course.description && <Paragraph type="secondary" style={{ margin: 0 }}>{course.description}</Paragraph>}
      </Space>

      <Card style={{ marginBottom: 24 }}>
        <Steps direction="vertical" size="small" current={0} items={[
          { title: t('trainingPath.stepLearn'), description: t('trainingPath.stepLearnDescription') },
          { title: t('trainingPath.stepPractice'), description: t('trainingPath.stepPracticeDescription') },
          { title: t('trainingPath.stepAssessment'), description: t('trainingPath.stepAssessmentDescription') },
        ]} />
      </Card>

      <Alert type="info" showIcon message={t('trainingPath.currentScope')} style={{ marginBottom: 24 }} />

      {nextStep && (
        <Card style={{ marginBottom: 24, borderColor: '#91caff', background: '#f0f7ff' }}>
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text strong>{t(`trainingPath.next.${nextStep.reason}`)}</Text>
            {nextStep.knowledge_point_id && (
              <Button type="primary" onClick={() => document.getElementById(`knowledge-point-${nextStep.knowledge_point_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
                {t('trainingPath.goToNext')}
              </Button>
            )}
          </Space>
        </Card>
      )}

      <Card title={t('trainingPath.materials')} style={{ marginBottom: 24 }}>
        <List
          dataSource={course.version.assets}
          renderItem={(asset) => (
            <List.Item
              actions={asset.source_id ? [<Button type="link" key="open" onClick={() => setPreview({ sourceId: asset.source_id as string, title: asset.title })}>{t('trainingPath.openMaterial')}</Button>] : undefined}
            >
              <BookOutlined />&nbsp; {asset.title}
            </List.Item>
          )}
        />
      </Card>

      <Space direction="vertical" size={18} style={{ width: '100%' }}>
        <Title level={3} style={{ marginBottom: 0 }}>{t('trainingPath.topics')}</Title>
        {course.version.knowledge_points.map((point, index) => (
          <Card id={`knowledge-point-${point.id}`} key={point.id} title={<Space><Tag>{index + 1}</Tag><span>{point.title}</span></Space>}>
            <Paragraph>{point.description}</Paragraph>
            <div style={{ padding: 16, borderRadius: 8, background: '#fafafa' }}>
              <Text type="secondary"><FileTextOutlined /> {t('trainingPath.evidence')}</Text>
              <Paragraph style={{ margin: '8px 0 0' }}>{point.evidence_excerpt}</Paragraph>
              {course.version.assets.find((asset) => asset.id === point.course_asset_id)?.source_id && (
                <Button
                  type="link"
                  style={{ paddingInline: 0, marginTop: 4 }}
                  onClick={() => {
                    const asset = course.version.assets.find((item) => item.id === point.course_asset_id);
                    if (asset?.source_id) setPreview({ sourceId: asset.source_id, title: asset.title, evidenceExcerpt: point.evidence_excerpt });
                  }}
                >
                  {t('trainingPath.openEvidence')}
                </Button>
              )}
            </div>
            <div style={{ marginTop: 20 }}>
              {!attempts[point.id] && (
                <Button type="primary" loading={workingPointId === point.id} onClick={() => startPractice(point.id)}>
                  {t('trainingPath.startPractice')}
                </Button>
              )}
              {attempts[point.id]?.status === 'pending' && (
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Text strong>{attempts[point.id].question_text}</Text>
                  {attempts[point.id].question_type === 'single_choice' ? (
                    <Radio.Group value={answers[point.id]} onChange={(event) => setAnswers((current) => ({ ...current, [point.id]: event.target.value }))}>
                      <Space direction="vertical">
                        {attempts[point.id].options?.map((option) => <Radio key={option.id} value={option.id}>{option.id}. {option.text}</Radio>)}
                      </Space>
                    </Radio.Group>
                  ) : (
                    <Input.TextArea
                      rows={4}
                      value={answers[point.id] || ''}
                      placeholder={t('trainingPath.answerPlaceholder')}
                      onChange={(event) => setAnswers((current) => ({ ...current, [point.id]: event.target.value }))}
                    />
                  )}
                  <Button type="primary" loading={workingPointId === point.id} disabled={!answers[point.id]?.trim()} onClick={() => submitAnswer(point.id)}>
                    {t('trainingPath.submitAnswer')}
                  </Button>
                </Space>
              )}
              {attempts[point.id]?.status === 'evaluated' && (
                <Alert
                  type={attempts[point.id].verdict === 'correct' ? 'success' : attempts[point.id].verdict === 'partial' ? 'warning' : 'error'}
                  showIcon
                  message={t(`trainingPath.verdict.${attempts[point.id].verdict}`)}
                  description={<><div>{t('trainingPath.score', { score: attempts[point.id].score })}</div><div>{attempts[point.id].feedback_text}</div></>}
                />
              )}
            </div>
          </Card>
        ))}
      </Space>

      <Card
        title={t('trainingPath.finalAssessment')}
        style={{ marginTop: 36 }}
      >
        {nextStepLoading ? (
          <Spin size="small" />
        ) : nextStep?.reason !== 'complete' ? (
          <Alert
            type="info"
            showIcon
            icon={<LockOutlined />}
            message={t('trainingPath.assessmentLocked')}
            description={t('trainingPath.assessmentLockedDescription')}
          />
        ) : (
          <>
            {!assessment && (
              <Space direction="vertical" size={10}>
                <Text>{t('trainingPath.assessmentReady')}</Text>
                <Button type="primary" loading={assessmentWorking} onClick={startAssessment}>
                  {t('trainingPath.startAssessment')}
                </Button>
              </Space>
            )}
            {assessment?.status === 'pending' && (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Text strong>{assessment.question_text}</Text>
                <Input.TextArea rows={6} value={assessmentAnswer} placeholder={t('trainingPath.answerPlaceholder')} onChange={(event) => setAssessmentAnswer(event.target.value)} />
                <Button type="primary" loading={assessmentWorking} disabled={!assessmentAnswer.trim()} onClick={submitAssessment}>{t('trainingPath.submitAssessment')}</Button>
              </Space>
            )}
            {assessment?.status === 'evaluated' && (
              <Alert
                type={(assessment.score || 0) >= 80 ? 'success' : 'warning'}
                showIcon
                message={(assessment.score || 0) >= 80 ? t('trainingPath.assessmentPassed') : t('trainingPath.assessmentNeedsReview')}
                description={<><div>{t('trainingPath.score', { score: assessment.score })}</div><div>{assessment.feedback_text}</div></>}
              />
            )}
          </>
        )}
      </Card>
      <PdfPreviewModal
        open={!!preview}
        sourceId={preview?.sourceId || null}
        title={preview?.title}
        evidenceExcerpt={preview?.evidenceExcerpt}
        onClose={() => setPreview(undefined)}
      />
    </div>
  );
}
