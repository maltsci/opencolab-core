import { ArrowLeftOutlined, BookOutlined, MenuFoldOutlined, MenuUnfoldOutlined, SendOutlined } from '@ant-design/icons';
import { Alert, Button, Input, List, Radio, Select, Space, Spin, Tag, Tooltip, Typography, message } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import PdfPreviewModal from '../components/library/PdfPreviewModal';
import apiClient from '../services/api-client';
import { getSourcePreviewUrl } from '../services/source-preview';
import './training-module-learning.css';

const { Paragraph, Text, Title } = Typography;

interface Evidence {
  evidence_id: string;
  excerpt: string;
  chunk_index: number;
  source_id?: string;
  source_title?: string;
  page_number?: number | null;
}

interface LessonVisual {
  kind: 'source_page' | 'concept_diagram';
  title: string;
  caption?: string;
  evidence_id: string;
  source_id?: string;
  page_number?: number;
  nodes?: { id: string; label: string }[];
}

interface Unit {
  id: string;
  title: string;
  description: string | null;
  pass_score: number;
  lesson: {
    outline: string[];
    lesson_markdown: string;
    evidence: Evidence[];
    visuals: LessonVisual[];
  } | null;
}

interface ModuleLearning {
  course_name: string;
  module_title: string;
  module_description: string | null;
  status: string;
  requires_retraining: boolean;
  display_language: ContentLanguage;
  units: Unit[];
}

type ContentLanguage = 'zh-CN' | 'en-US';

interface ChatMessage { role: 'user' | 'assistant'; content: string }
interface AssessmentQuestion {
  id: string;
  question_type: 'single_choice' | 'short_answer';
  prompt: string;
  options?: { id: string; text: string }[];
}
interface Assessment {
  id: string;
  questions: AssessmentQuestion[];
  status: string;
  score: number | null;
  passed: boolean;
  feedback: string | null;
  display_language: ContentLanguage;
}
interface LessonSection { title: string; markdown: string }

function splitLessonMarkdown(markdown: string, outline: string[]): LessonSection[] {
  const matches = [...markdown.matchAll(/^#{1,3}\s+(.+)$/gm)];
  if (!matches.length) return [{ title: outline[0] || '', markdown }];
  return matches.map((match, index) => ({
    title: match[1].trim(),
    markdown: markdown.slice(match.index ?? 0, matches[index + 1]?.index ?? markdown.length).trim(),
  }));
}

function linkifyEvidenceCitations(markdown: string): string {
  return markdown.replace(
    /(?:\[(E\d+)]|【(E\d+)】)(?!\()/g,
    (_match, bracketId: string | undefined, fullWidthId: string | undefined) => {
      const evidenceId = bracketId || fullWidthId;
      return `[${evidenceId}](evidence:${evidenceId})`;
    },
  );
}

function markdownUrlTransform(url: string): string {
  return url.startsWith('evidence:') ? url : defaultUrlTransform(url);
}

function SourcePageVisual({ visual }: { visual: LessonVisual }) {
  const { t } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!visual.source_id || !visual.page_number) return;
    let cancelled = false;
    getSourcePreviewUrl(visual.source_id, 'thumbnail', visual.page_number)
      .then((value) => { if (!cancelled) setUrl(value); })
      .catch(() => { if (!cancelled) setUrl(null); });
    return () => { cancelled = true; };
  }, [visual.page_number, visual.source_id]);
  if (!url) return null;
  return (
    <figure className="lesson-visual lesson-source-visual">
      <div className="lesson-visual-kicker">{t('trainingModule.sourceVisual')}</div>
      <img src={url} alt={visual.title} />
      <figcaption><Text strong>{visual.title}</Text>{visual.caption && <Paragraph>{visual.caption}</Paragraph>}</figcaption>
    </figure>
  );
}

function ConceptDiagram({ visual }: { visual: LessonVisual }) {
  const { t } = useTranslation();
  const nodes = visual.nodes || [];
  if (nodes.length < 2) return null;
  return (
    <figure className="lesson-visual lesson-concept-visual">
      <div className="lesson-visual-kicker">{t('trainingModule.aiVisual')}</div>
      <svg viewBox={`0 0 720 ${nodes.length * 84 + 24}`} role="img" aria-label={visual.title}>
        {nodes.slice(0, -1).map((node, index) => (
          <line key={node.id} x1="360" y1={76 + index * 84} x2="360" y2={104 + index * 84} />
        ))}
        {nodes.map((node, index) => (
          <g key={node.id} transform={`translate(110 ${20 + index * 84})`}>
            <rect width="500" height="56" rx="10" />
            <text x="250" y="34" textAnchor="middle">{node.label}</text>
          </g>
        ))}
      </svg>
      <figcaption><Text strong>{visual.title}</Text>{visual.caption && <Paragraph>{visual.caption}</Paragraph>}</figcaption>
    </figure>
  );
}

export default function TrainingModuleLearning() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const [learning, setLearning] = useState<ModuleLearning | null>(null);
  const [loading, setLoading] = useState(true);
  const [outlineVisible, setOutlineVisible] = useState(true);
  const [activeAnchor, setActiveAnchor] = useState('');
  const [previewEvidence, setPreviewEvidence] = useState<Evidence | null>(null);
  const [questions, setQuestions] = useState<Record<string, string>>({});
  const [histories, setHistories] = useState<Record<string, ChatMessage[]>>({});
  const [askingUnitId, setAskingUnitId] = useState<string | null>(null);
  const [assessments, setAssessments] = useState<Record<string, Assessment>>({});
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [assessmentUnitId, setAssessmentUnitId] = useState<string | null>(null);
  const [languageChanging, setLanguageChanging] = useState(false);
  const [displayLanguage, setDisplayLanguage] = useState<ContentLanguage>(() => {
    const saved = window.localStorage.getItem('training-content-language');
    if (saved === 'zh-CN' || saved === 'en-US') return saved;
    return i18n.resolvedLanguage?.startsWith('zh') ? 'zh-CN' : 'en-US';
  });

  useEffect(() => {
    if (!assignmentId) return;
    setLoading(true);
    apiClient.get<ModuleLearning>(`/training/module-assignments/${assignmentId}/learning`, {
      params: { language: displayLanguage },
      timeout: 120000,
    })
      .then(({ data }) => setLearning(data))
      .catch(() => message.error(t('trainingModule.loadFailed')))
      .finally(() => setLoading(false));
  }, [assignmentId, displayLanguage, t]);

  const changeDisplayLanguage = async (language: ContentLanguage) => {
    setDisplayLanguage(language);
    window.localStorage.setItem('training-content-language', language);
    const currentAssessments = Object.entries(assessments);
    if (!currentAssessments.length) return;
    setLanguageChanging(true);
    try {
      const translated = await Promise.all(currentAssessments.map(async ([unitId, assessment]) => {
        const { data } = await apiClient.get<Assessment>(`/training/unit-assessments/${assessment.id}`, {
          params: { language },
          timeout: 120000,
        });
        return [unitId, data] as const;
      }));
      setAssessments(Object.fromEntries(translated));
    } catch {
      message.error(t('trainingModule.languageSwitchFailed'));
    } finally {
      setLanguageChanging(false);
    }
  };

  const sectionsByUnit = useMemo(() => new Map(
    (learning?.units || []).map((unit) => [
      unit.id,
      unit.lesson ? splitLessonMarkdown(unit.lesson.lesson_markdown, unit.lesson.outline) : [],
    ]),
  ), [learning]);

  const scrollToAnchor = (anchor: string) => {
    setActiveAnchor(anchor);
    document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const ask = async (unitId: string) => {
    const question = questions[unitId]?.trim();
    if (!assignmentId || !question) return;
    setAskingUnitId(unitId);
    try {
      const { data } = await apiClient.post<{ history: ChatMessage[] }>(
        `/training/module-assignments/${assignmentId}/units/${unitId}/ask`,
        { question, language: displayLanguage },
        { timeout: 120000 },
      );
      setHistories((current) => ({ ...current, [unitId]: data.history }));
      setQuestions((current) => ({ ...current, [unitId]: '' }));
    } catch {
      message.error(t('trainingModule.askFailed'));
    } finally {
      setAskingUnitId(null);
    }
  };

  const startAssessment = async (unitId: string) => {
    if (!assignmentId) return;
    setAssessmentUnitId(unitId);
    try {
      const { data } = await apiClient.post<Assessment>(
        `/training/module-assignments/${assignmentId}/units/${unitId}/assessment`,
        undefined,
        { params: { language: displayLanguage }, timeout: 120000 },
      );
      setAssessments((current) => ({ ...current, [unitId]: data }));
      setAnswers((current) => ({ ...current, [unitId]: {} }));
    } catch {
      message.error(t('trainingModule.assessmentGenerateFailed'));
    } finally {
      setAssessmentUnitId(null);
    }
  };

  const submitAssessment = async (unitId: string) => {
    const assessment = assessments[unitId];
    if (!assessment) return;
    setAssessmentUnitId(unitId);
    try {
      const { data } = await apiClient.post<Assessment>(
        `/training/unit-assessments/${assessment.id}/answer`,
        { answers: answers[unitId] || {}, language: displayLanguage },
        { timeout: 120000 },
      );
      setAssessments((current) => ({ ...current, [unitId]: data }));
      message.success(data.passed ? t('trainingModule.assessmentPassed') : t('trainingModule.assessmentNeedsReview'));
    } catch {
      message.error(t('trainingModule.assessmentSubmitFailed'));
    } finally {
      setAssessmentUnitId(null);
    }
  };

  const renderMarkdown = (markdown: string, evidence: Evidence[]) => (
    <ReactMarkdown
      urlTransform={markdownUrlTransform}
      components={{
        a: ({ href, children }) => {
          if (!href?.startsWith('evidence:')) return <a href={href}>{children}</a>;
          const evidenceId = href.slice('evidence:'.length);
          const item = evidence.find((candidate) => candidate.evidence_id === evidenceId);
          return (
            <Tooltip
              overlayClassName="evidence-tooltip"
              title={item ? (
                <div>
                  <Text strong>{item.source_title || evidenceId}</Text>
                  {item.page_number && <Text> · {t('trainingModule.pageNumber', { page: item.page_number })}</Text>}
                  <Paragraph>{item.excerpt}</Paragraph>
                  {item.source_id && <Text type="secondary">{t('trainingModule.clickToPreview')}</Text>}
                </div>
              ) : evidenceId}
            >
              <button className="evidence-citation" type="button" onClick={() => item?.source_id && setPreviewEvidence(item)}>
                {children}
              </button>
            </Tooltip>
          );
        },
      }}
    >
      {linkifyEvidenceCitations(markdown)}
    </ReactMarkdown>
  );

  if (loading) return <Spin size="large" className="training-reader-loading" />;
  if (!learning) return <Alert type="error" showIcon message={t('trainingModule.loadFailed')} />;

  return (
    <div className="training-reader">
      <header className="training-reader-header">
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/training')}>
          {t('trainingModule.back')}
        </Button>
        <div className="training-reader-title">
          <Text type="secondary">{learning.course_name}</Text>
          <Title level={1}>{learning.module_title}</Title>
          {learning.module_description && <Paragraph>{learning.module_description}</Paragraph>}
          <Tag color="blue">{t(`trainingHome.assignmentStatus.${learning.status}`)}</Tag>
        </div>
        <div className="training-language-switcher">
          <Text type="secondary">{t('trainingModule.contentLanguage')}</Text>
          <Select<ContentLanguage>
            value={displayLanguage}
            loading={languageChanging}
            options={[
              { value: 'zh-CN', label: t('trainingModule.languageChinese') },
              { value: 'en-US', label: t('trainingModule.languageEnglish') },
            ]}
            onChange={changeDisplayLanguage}
          />
        </div>
      </header>

      {learning.requires_retraining && (
        <Alert
          type="warning"
          showIcon
          message={t('trainingModule.retrainingTitle')}
          description={t('trainingModule.retrainingDescription')}
        />
      )}

      {learning.units.length === 0 ? <Alert type="info" showIcon message={t('trainingModule.noUnits')} /> : (
        <div className={`training-reader-layout${outlineVisible ? '' : ' outline-hidden'}`}>
          {outlineVisible ? (
            <aside className="training-outline">
              <div className="training-outline-heading">
                <span><BookOutlined /> {t('trainingModule.outline')}</span>
                <Button type="text" size="small" icon={<MenuFoldOutlined />} aria-label={t('trainingModule.hideOutline')} onClick={() => setOutlineVisible(false)} />
              </div>
              <nav>
                {learning.units.map((unit, unitIndex) => (
                  <div className="training-outline-unit" key={unit.id}>
                    <Text type="secondary">{t('trainingModule.unitNumber', { number: unitIndex + 1 })}</Text>
                    <button className={activeAnchor === `unit-${unit.id}` ? 'active' : ''} type="button" onClick={() => scrollToAnchor(`unit-${unit.id}`)}>
                      {unit.title}
                    </button>
                    {(sectionsByUnit.get(unit.id) || []).map((section, sectionIndex) => {
                      const anchor = `unit-${unit.id}-section-${sectionIndex}`;
                      return (
                        <button className={`training-outline-section${activeAnchor === anchor ? ' active' : ''}`} key={anchor} type="button" onClick={() => scrollToAnchor(anchor)}>
                          {section.title || unit.lesson?.outline[sectionIndex] || `${sectionIndex + 1}`}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </nav>
            </aside>
          ) : (
            <Button className="training-outline-show" icon={<MenuUnfoldOutlined />} onClick={() => setOutlineVisible(true)}>
              {t('trainingModule.showOutline')}
            </Button>
          )}

          <main className="training-reading-column">
            {learning.units.map((unit, unitIndex) => {
              const sections = sectionsByUnit.get(unit.id) || [];
              const evidence = unit.lesson?.evidence || [];
              return (
                <article className="training-unit" id={`unit-${unit.id}`} key={unit.id}>
                  <div className="training-unit-number">{t('trainingModule.unitNumber', { number: unitIndex + 1 })}</div>
                  <Title level={2}>{unit.title}</Title>
                  {unit.description && <Paragraph className="training-unit-lead">{unit.description}</Paragraph>}
                  {!unit.lesson ? <Alert type="info" message={t('trainingModule.lessonUnavailable')} /> : (
                    <>
                      <div className="training-lesson">
                        {sections.map((section, sectionIndex) => (
                          <section id={`unit-${unit.id}-section-${sectionIndex}`} key={`${unit.id}-${sectionIndex}`}>
                            {renderMarkdown(section.markdown, evidence)}
                            {sectionIndex === 0 && unit.lesson?.visuals.map((visual, visualIndex) => (
                              visual.kind === 'source_page'
                                ? <SourcePageVisual key={`${visual.evidence_id}-${visualIndex}`} visual={visual} />
                                : <ConceptDiagram key={`${visual.evidence_id}-${visualIndex}`} visual={visual} />
                            ))}
                          </section>
                        ))}
                      </div>

                      <details className="training-evidence-drawer">
                        <summary>{t('trainingModule.evidence')} · {evidence.length}</summary>
                        <List dataSource={evidence} renderItem={(item) => (
                          <List.Item>
                            <button className="training-evidence-row" type="button" disabled={!item.source_id} onClick={() => item.source_id && setPreviewEvidence(item)}>
                              <Text strong>[{item.evidence_id}] {item.source_title}</Text>
                              {item.page_number && <Text type="secondary">{t('trainingModule.pageNumber', { page: item.page_number })}</Text>}
                              <span>{item.excerpt}</span>
                            </button>
                          </List.Item>
                        )} />
                      </details>

                      <section className="training-interaction-panel">
                        <Title level={3}>{t('trainingModule.tutor')}</Title>
                        <List
                          locale={{ emptyText: t('trainingModule.noQuestions') }}
                          dataSource={histories[unit.id] || []}
                          renderItem={(item) => (
                            <List.Item className={`tutor-message ${item.role}`}>
                              <Text strong>{item.role === 'user' ? t('trainingModule.you') : t('trainingModule.aiTutor')}</Text>
                              <div>{renderMarkdown(item.content, evidence)}</div>
                            </List.Item>
                          )}
                        />
                        <Space.Compact className="training-question-input">
                          <Input value={questions[unit.id] || ''} placeholder={t('trainingModule.questionPlaceholder')} onChange={(event) => setQuestions((current) => ({ ...current, [unit.id]: event.target.value }))} onPressEnter={() => ask(unit.id)} />
                          <Button type="primary" icon={<SendOutlined />} loading={askingUnitId === unit.id} onClick={() => ask(unit.id)}>{t('trainingModule.ask')}</Button>
                        </Space.Compact>
                      </section>

                      <section className="training-assessment-panel">
                        <div className="training-panel-heading">
                          <Title level={3}>{t('trainingModule.assessment')}</Title>
                          <Text type="secondary">{t('trainingModule.passScore', { score: unit.pass_score })}</Text>
                        </div>
                        {!assessments[unit.id] ? (
                          <Button type="primary" loading={assessmentUnitId === unit.id} onClick={() => startAssessment(unit.id)}>{t('trainingModule.startAssessment')}</Button>
                        ) : (
                          <Space direction="vertical" size={24} className="training-assessment-questions">
                            {assessments[unit.id].questions.map((question, index) => (
                              <div className="training-assessment-question" key={question.id}>
                                <Paragraph strong>{index + 1}. {question.prompt}</Paragraph>
                                {question.question_type === 'single_choice' ? (
                                  <Radio.Group disabled={assessments[unit.id].status === 'evaluated'} value={answers[unit.id]?.[question.id]} onChange={(event) => setAnswers((current) => ({ ...current, [unit.id]: { ...current[unit.id], [question.id]: event.target.value } }))}>
                                    <Space direction="vertical">{question.options?.map((option) => <Radio key={option.id} value={option.id}>{option.id}. {option.text}</Radio>)}</Space>
                                  </Radio.Group>
                                ) : (
                                  <Input.TextArea rows={3} disabled={assessments[unit.id].status === 'evaluated'} value={answers[unit.id]?.[question.id] || ''} onChange={(event) => setAnswers((current) => ({ ...current, [unit.id]: { ...current[unit.id], [question.id]: event.target.value } }))} />
                                )}
                              </div>
                            ))}
                            {assessments[unit.id].status === 'pending' ? (
                              <Button type="primary" loading={assessmentUnitId === unit.id} onClick={() => submitAssessment(unit.id)}>{t('trainingModule.submitAssessment')}</Button>
                            ) : (
                              <Alert showIcon type={assessments[unit.id].passed ? 'success' : 'warning'} message={t('trainingModule.assessmentResult', { score: assessments[unit.id].score })} description={assessments[unit.id].feedback} />
                            )}
                          </Space>
                        )}
                      </section>
                    </>
                  )}
                </article>
              );
            })}
          </main>
        </div>
      )}

      <PdfPreviewModal open={!!previewEvidence} sourceId={previewEvidence?.source_id || null} title={previewEvidence?.source_title} evidenceExcerpt={previewEvidence?.excerpt} pageNumber={previewEvidence?.page_number} onClose={() => setPreviewEvidence(null)} />
    </div>
  );
}
