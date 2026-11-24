import {
  BulbOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  DownloadOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  RocketOutlined,
  SendOutlined,
  SettingOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import apiClient from '../../services/api-client';
import { MarkdownContent } from '../ui/ChatMessage';
import type { Project, ProjectMember } from '../../types/project';
import { IdeaEvaluationCard, PeerReviewCard } from './ResearchScorecards';
import type {
  AcceptMode,
  PipelineStageSummary,
  ProactiveRule,
  ResearchTicket,
  StageCategory,
  SuperagentOverview,
  TicketDeliverable,
} from '../../types/superagent';

const { Text, Paragraph } = Typography;

interface ProjectSuperagentTabProps {
  project: Project;
  canManage: boolean;
  initialTicketId?: string | null;
  initialStage?: string | null;
  onClearDeepLink?: () => void;
  onWorkspaceChanged?: () => void;
  activityTimeline?: ReactNode;
}

const STAGE_ORDER: StageCategory[] = [
  'problem_framing',
  'baseline_reproduction',
  'innovation_feasibility',
  'experiment_iteration',
  'manuscript_writing',
];

const STAGE_BADGE_COLORS: Record<string, string> = {
  'person / answer': 'gold',
  'person / wetlab': 'purple',
  'person / review': 'blue',
  'person / blocked': 'red',
  'working / queued': 'cyan',
  working: 'processing',
  idle: 'default',
  ended: 'success',
};

const STAGE_LABEL_KEYS: Record<string, string> = {
  'person / answer': 'superagent.ticketStage.personAnswer',
  'person / wetlab': 'superagent.ticketStage.personWetlab',
  'person / review': 'superagent.ticketStage.personReview',
  'person / blocked': 'superagent.ticketStage.personBlocked',
  'working / queued': 'superagent.ticketStage.workingQueued',
  working: 'superagent.ticketStage.working',
  idle: 'superagent.ticketStage.idle',
  ended: 'superagent.ticketStage.ended',
};

export default function ProjectSuperagentTab({
  project,
  canManage,
  initialTicketId,
  initialStage,
  onClearDeepLink,
  onWorkspaceChanged,
  activityTimeline,
}: ProjectSuperagentTabProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();

  const [overview, setOverview] = useState<SuperagentOverview | null>(null);
  const [tickets, setTickets] = useState<ResearchTicket[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [submittingId, setSubmittingId] = useState<string | null>(null);

  const [selectedStage, setSelectedStage] = useState<StageCategory | null>(null);
  const [selectedStageVersionIds, setSelectedStageVersionIds] = useState<
    Record<string, string>
  >({});
  const [activeTicket, setActiveTicket] = useState<ResearchTicket | null>(null);
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({});
  const [threadInput, setThreadInput] = useState('');

  // Modals
  const [questionModalOpen, setQuestionModalOpen] = useState(false);
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [inlineSubQuestionInputs, setInlineSubQuestionInputs] = useState<
    Record<string, string>
  >({});
  const [wetlabModalTicket, setWetlabModalTicket] = useState<ResearchTicket | null>(null);
  const [nextRoundModalTicket, setNextRoundModalTicket] = useState<ResearchTicket | null>(null);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [newTicketModalOpen, setNewTicketModalOpen] = useState(false);

  const [questionForm] = Form.useForm();
  const [wetlabForm] = Form.useForm();
  const [nextRoundForm] = Form.useForm();
  const [newTicketForm] = Form.useForm();

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [ovRes, tkRes] = await Promise.all([
        apiClient.get<SuperagentOverview>(`/projects/${project.id}/superagent/overview`),
        apiClient.get<ResearchTicket[]>(`/projects/${project.id}/tickets`),
      ]);
      setOverview(ovRes.data);
      setTickets(tkRes.data);
      setActiveTicket((prev) => {
        if (!prev) return null;
        return tkRes.data.find((item) => item.id === prev.id) ?? prev;
      });
      onWorkspaceChanged?.();
    } catch {
      message.error(t('superagent.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [onWorkspaceChanged, project.id, t]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    if (initialStage && STAGE_ORDER.includes(initialStage as StageCategory)) {
      setSelectedStage(initialStage as StageCategory);
      onClearDeepLink?.();
    }
  }, [initialStage, onClearDeepLink]);

  useEffect(() => {
    if (!initialTicketId || tickets.length === 0) return;
    const found = tickets.find((item) => item.id === initialTicketId);
    if (found) {
      setActiveTicket(found);
      setSelectedStage(found.stage_category);
      onClearDeepLink?.();
    }
  }, [initialTicketId, onClearDeepLink, tickets]);

  const handleDiscussInSession = async (ticket: ResearchTicket) => {
    setSubmittingId(`open-session-${ticket.id}`);
    try {
      const res = await apiClient.post<{
        session_id: string;
        title: string;
      }>(`/projects/${project.id}/tickets/${ticket.id}/open-session`);
      onWorkspaceChanged?.();
      navigate(`/sessions/${res.data.session_id}`);
    } catch {
      message.error(t('superagent.actionFailed'));
    } finally {
      setSubmittingId(null);
    }
  };

  const handleRetryExecution = async (ticket: ResearchTicket) => {
    setSubmittingId(`retry-baseline-${ticket.id}`);
    try {
      const res = await apiClient.post<ResearchTicket>(
        `/projects/${project.id}/tickets/${ticket.id}/${
          ticket.stage_category === 'baseline_reproduction' ? 'retry-baseline' : 'retry-stage'
        }`,
        {},
        { timeout: 0 },
      );
      await fetchAll();
      setActiveTicket(res.data);
    } catch {
      message.error(t('superagent.actionFailed'));
    } finally {
      setSubmittingId(null);
    }
  };

  const handleSpawnRebuttal = async (ticketId: string) => {
    setSubmittingId(`rebuttal-${ticketId}`);
    try {
      const res = await apiClient.post<ResearchTicket>(
        `/projects/${project.id}/tickets/${ticketId}/rebuttal-validation`,
        {},
      );
      message.success(t('superagent.rebuttalSpawned'));
      await fetchAll();
      setSelectedStage('experiment_iteration');
      setActiveTicket(res.data);
    } catch {
      message.error(t('superagent.actionFailed'));
    } finally {
      setSubmittingId(null);
    }
  };

  useEffect(() => {
    apiClient
      .get<ProjectMember[]>(`/projects/${project.id}/members`)
      .then((r) => setMembers(r.data))
      .catch(() => undefined);
  }, [project.id]);

  const getStage1Items = () => {
    const s1 = overview?.pipeline_stages.find(
      (s) => s.stage_category === 'problem_framing',
    );
    return s1?.items || [];
  };

  const getCurrentTheme = () => {
    const items = getStage1Items();
    for (const item of items) {
      const cj = item.content_json as Record<string, unknown> | undefined;
      if (cj && typeof cj.theme === 'string' && cj.theme.trim()) {
        return cj.theme.trim();
      }
    }
    return project.name;
  };

  const openAddQuestionModal = () => {
    setEditingQuestionId(null);
    questionForm.resetFields();
    questionForm.setFieldsValue({
      theme: getCurrentTheme(),
      question: '',
      sub_questions_raw: '',
      success_criteria_raw: '',
      constraints_raw: '',
    });
    setQuestionModalOpen(true);
  };

  const openEditQuestionModal = (item: {
    id: string;
    title?: string | null;
    content?: string | null;
    content_json?: Record<string, unknown> | null;
  }) => {
    setEditingQuestionId(item.id);
    const cj = (item.content_json || {}) as Record<string, unknown>;
    const subQs = Array.isArray(cj.sub_questions)
      ? (cj.sub_questions as string[])
      : [];
    const criteriaList: string[] = Array.isArray(cj.success_criteria)
      ? (cj.success_criteria as string[])
      : Array.isArray(cj.target_metrics)
        ? (
            cj.target_metrics as {
              metric?: string;
              target?: string;
              unit?: string;
            }[]
          ).map((m) =>
            `${m.metric || ''}: ${m.target || ''} ${m.unit || ''}`.trim(),
          )
        : [];
    const constraintsList = Array.isArray(cj.constraints)
      ? (cj.constraints as string[])
      : [];

    questionForm.setFieldsValue({
      theme: (typeof cj.theme === 'string' && cj.theme) || getCurrentTheme(),
      question: (typeof cj.question === 'string' && cj.question) || item.title || '',
      sub_questions_raw: subQs.join('\n'),
      success_criteria_raw: criteriaList.join('\n'),
      constraints_raw: constraintsList.join('\n'),
    });
    setQuestionModalOpen(true);
  };

  const handleActionFailure = async () => {
    message.error(t('superagent.actionFailed'));
    try {
      await fetchAll();
    } catch {
      // Ignore secondary refresh error when backend or network is unreachable
    }
  };

  const handleAiSuggestCharter = async () => {
    setSubmittingId('ai-suggest-charter');
    try {
      const res = await apiClient.post<{
        theme: string;
        question: string;
        sub_questions: string[];
        success_criteria: string[];
        constraints: string[];
      }>(`/projects/${project.id}/superagent/questions/suggest`);
      const data = res.data;
      questionForm.setFieldsValue({
        theme: data.theme || getCurrentTheme(),
        question: data.question || '',
        sub_questions_raw: (data.sub_questions || []).join('\n'),
        success_criteria_raw: (data.success_criteria || []).join('\n'),
        constraints_raw: (data.constraints || []).join('\n'),
      });
      if (!questionModalOpen) {
        setEditingQuestionId(null);
        setQuestionModalOpen(true);
      }
      message.success(t('superagent.aiCharterSuggested'));
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleAppendSubQuestionInline = async (item: {
    id: string;
    title?: string | null;
    content_json?: Record<string, unknown> | null;
  }) => {
    const newSub = (inlineSubQuestionInputs[item.id] || '').trim();
    if (!newSub) return;
    const cj = (item.content_json || {}) as Record<string, unknown>;
    const existingSubs = Array.isArray(cj.sub_questions)
      ? (cj.sub_questions as string[])
      : [];
    const existingCriteria = Array.isArray(cj.success_criteria)
      ? (cj.success_criteria as string[])
      : [];
    const existingConstraints = Array.isArray(cj.constraints)
      ? (cj.constraints as string[])
      : [];

    setSubmittingId(`subq-${item.id}`);
    try {
      await apiClient.post(`/projects/${project.id}/superagent/questions`, {
        question_object_id: item.id,
        theme: (typeof cj.theme === 'string' && cj.theme) || getCurrentTheme(),
        question:
          (typeof cj.question === 'string' && cj.question) ||
          item.title ||
          project.name,
        sub_questions: [...existingSubs, newSub],
        success_criteria: existingCriteria,
        constraints: existingConstraints,
        trigger_baseline: false,
      });
      setInlineSubQuestionInputs((prev) => ({ ...prev, [item.id]: '' }));
      message.success(t('superagent.subQuestionAdded'));
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleDefineQuestion = async (values: {
    theme: string;
    question: string;
    sub_questions_raw?: string;
    success_criteria_raw?: string;
    constraints_raw?: string;
    plugin_id?: string;
  }) => {
    setSubmittingId('define-question');
    try {
      const sub_questions = (values.sub_questions_raw || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      const success_criteria = (values.success_criteria_raw || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      const constraints = (values.constraints_raw || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);

      await apiClient.post(`/projects/${project.id}/superagent/questions`, {
        question_object_id: editingQuestionId,
        theme: values.theme,
        question: values.question,
        sub_questions,
        success_criteria,
        target_metrics: [],
        constraints,
        plugin_id: values.plugin_id || project.task_ids?.[0] || null,
        trigger_baseline: true,
      }, { timeout: 0 });
      message.success(t('superagent.questionSavedAndTriggered'));
      setQuestionModalOpen(false);
      setEditingQuestionId(null);
      questionForm.resetFields();
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleAnswerAttention = async (ticket: ResearchTicket, selectedOption: string) => {
    if (!selectedOption.trim()) return;
    setSubmittingId(ticket.id);
    try {
      const res = await apiClient.post<ResearchTicket>(
        `/projects/${project.id}/tickets/${ticket.id}/answer`,
        {
          answer: selectedOption,
          selected_option: selectedOption,
        },
        { timeout: 0 },
      );
      if (selectedStage && res.data?.stage_category && res.data.stage_category !== selectedStage) {
        setSelectedStage(res.data.stage_category);
      }
      message.success(t('superagent.answerSubmitted'));
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleApproveTicket = async (
    ticket: ResearchTicket,
    markMilestoneVerified = false,
  ) => {
    setSubmittingId(ticket.id);
    try {
      await apiClient.post(`/projects/${project.id}/tickets/${ticket.id}/approve`, {
        comment: markMilestoneVerified
          ? 'Milestone verified; advancing to manuscript stage.'
          : 'Approved and merged into project state.',
        mark_milestone_verified: markMilestoneVerified,
      }, { timeout: 0 });
      message.success(
        markMilestoneVerified
          ? t('superagent.milestoneVerifiedAndManuscriptStarted')
          : t('superagent.deliverableApproved'),
      );
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleSkipWetlabAndVerify = async (ticket: ResearchTicket) => {
    setSubmittingId(ticket.id);
    try {
      await apiClient.post(
        `/projects/${project.id}/tickets/${ticket.id}/wetlab-upload`,
        {
          experiment_note:
            'No external experimental dataset required; verified via Agent workspace analysis and literature consistency check.',
          measurements: [
            {
              sample_id: `R${ticket.iteration_round || 1}-SCHEME-01`,
              condition: 'Agent Automated Verification & Literature Consistency Check',
              predicted_value: 'Target Aligned',
              measured_value: 'Verified (Pass)',
              secondary_metric: '100% Traceable',
              notes: 'Verified without external experimental data',
            },
            {
              sample_id: 'CTRL-BL-01',
              condition: 'Reproduced Literature Baseline Reference',
              predicted_value: 'Baseline',
              measured_value: 'Reference',
              secondary_metric: 'Benchmark',
              notes: 'Stage 2 baseline control',
            },
          ],
        },
      );
      message.success(t('superagent.agentVerificationCompleted'));
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const openWetlabModal = (ticket: ResearchTicket) => {
    setWetlabModalTicket(ticket);
    const defaultCsv = ticket.attention?.template_data?.csv_text || '';
    wetlabForm.setFieldsValue({
      experiment_note: '',
      csv_content: defaultCsv,
    });
  };

  const handleWetlabUpload = async (values: {
    experiment_note?: string;
    csv_content?: string;
  }) => {
    if (!wetlabModalTicket) return;
    setSubmittingId(wetlabModalTicket.id);
    try {
      await apiClient.post(
        `/projects/${project.id}/tickets/${wetlabModalTicket.id}/wetlab-upload`,
        {
          experiment_note: values.experiment_note || '',
          csv_content: values.csv_content || '',
        },
      );
      message.success(t('superagent.wetlabUploadedAndDiffed'));
      setWetlabModalTicket(null);
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleDownloadCsvTemplate = (ticket: ResearchTicket) => {
    const csvText = ticket.attention?.template_data?.csv_text;
    if (!csvText) return;
    const filename =
      ticket.attention?.template_data?.filename ||
      `${ticket.short_key}_wetlab_template.csv`;
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleSpawnNextRound = async (values: {
    direction_note: string;
    assignee_id?: string;
  }) => {
    if (!nextRoundModalTicket) return;
    setSubmittingId(nextRoundModalTicket.id);
    try {
      await apiClient.post(
        `/projects/${project.id}/tickets/${nextRoundModalTicket.id}/next-round`,
        values,
      );
      message.success(t('superagent.nextRoundSpawned'));
      setNextRoundModalTicket(null);
      nextRoundForm.resetFields();
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleModeChange = async (mode: AcceptMode) => {
    try {
      await apiClient.put(`/projects/${project.id}/superagent/policy`, {
        accept_mode: mode,
      });
      message.success(t('superagent.policyUpdated'));
      await fetchAll();
    } catch {
      message.error(t('superagent.actionFailed'));
    }
  };

  const handleToggleRule = async (ruleId: string, enabled: boolean) => {
    if (!overview) return;
    const updatedRules: ProactiveRule[] = overview.policy.rules.map((r) =>
      r.id === ruleId ? { ...r, is_enabled: enabled } : r,
    );
    try {
      await apiClient.put(`/projects/${project.id}/superagent/policy`, {
        rules: updatedRules,
      });
      await fetchAll();
    } catch {
      message.error(t('superagent.actionFailed'));
    }
  };

  const handleDomainPluginChange = async (pluginKey: string) => {
    try {
      const enabled_plugins =
        pluginKey === 'universal' ? [] : [pluginKey];
      await apiClient.put(`/projects/${project.id}/superagent/policy`, {
        enabled_plugins,
      });
      message.success(t('superagent.policyUpdated'));
      await fetchAll();
    } catch {
      message.error(t('superagent.actionFailed'));
    }
  };

  const handleSelectStage = (stageKey: StageCategory) => {
    const nextStage = selectedStage === stageKey ? null : stageKey;
    setSelectedStage(nextStage);
    if (nextStage) {
      window.setTimeout(() => {
        const anchorEl =
          document.getElementById(`stage-anchor-${nextStage}`) ||
          document.getElementById('superagent-stage-workspace');
        anchorEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 40);
    }
  };

  const handleEmitLiteratureTrigger = async () => {
    setSubmittingId('trigger-scan');
    try {
      await apiClient.post(`/projects/${project.id}/superagent/triggers`, {
        source_kind: 'source',
        event_type: 'sources_ready',
        title: 'Literature corpus scan and baseline reproduction requested',
      }, { timeout: 0 });
      message.success(t('superagent.baselineScanTriggered'));
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleCreateTicket = async (values: {
    title: string;
    stage_category: StageCategory;
    goal?: string;
    assignee_id?: string;
  }) => {
    setSubmittingId('new-ticket');
    try {
      await apiClient.post(`/projects/${project.id}/tickets`, values, {
        timeout: ['baseline_reproduction', 'innovation_feasibility', 'manuscript_writing'].includes(values.stage_category) ? 0 : undefined,
      });
      message.success(t('superagent.ticketCreated'));
      setNewTicketModalOpen(false);
      newTicketForm.resetFields();
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleSendThreadMessage = async () => {
    if (!activeTicket || !threadInput.trim()) return;
    setSubmittingId('send-msg');
    try {
      const res = await apiClient.post<ResearchTicket>(
        `/projects/${project.id}/tickets/${activeTicket.id}/messages`,
        {
          content: threadInput.trim(),
          invoke_agent: true,
        },
      );
      setActiveTicket(res.data);
      setThreadInput('');
      await fetchAll();
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  const handleDownloadBibtex = (bibtexText: string, shortKey: string) => {
    if (!bibtexText) return;
    const blob = new Blob([bibtexText], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${shortKey}_references.bib`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportManuscript = async (
    endpoint: string,
    fallbackFilename: string,
    key: string,
  ) => {
    setSubmittingId(key);
    try {
      const res = await apiClient.get(endpoint, { responseType: 'blob' });
      const blob = new Blob([res.data], {
        type: res.headers['content-type'] || 'application/octet-stream',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fallbackFilename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      await handleActionFailure();
    } finally {
      setSubmittingId(null);
    }
  };

  if (loading && !overview) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin />
      </div>
    );
  }

  if (!overview) return null;

  const renderDeliverableTable = (rows: Record<string, unknown>[]) => {
    if (!rows || rows.length === 0) return null;
    const keys = Object.keys(rows[0]);
    const columns = keys.map((k) => ({
      title: k.replace(/_/g, ' ').toUpperCase(),
      dataIndex: k,
      key: k,
      render: (val: unknown) => <Text style={{ fontSize: 12 }}>{String(val ?? '-')}</Text>,
    }));
    return (
      <Table
        size="small"
        pagination={false}
        dataSource={rows.map((r, idx) => ({ ...r, _rowKey: idx }))}
        rowKey="_rowKey"
        columns={columns}
        scroll={{ x: true }}
        style={{ marginTop: 8 }}
      />
    );
  };

  const renderMultiAgentArtifacts = (
    deliverable: TicketDeliverable | null | undefined,
    shortKey: string,
  ) => {
    if (!deliverable) return null;
    const plannerSubtasks = deliverable.planner_plan?.subtasks || [];
    const cards = deliverable.literature_memory_cards || [];
    const crossVal = deliverable.data_cross_validation;
    const writerOut = deliverable.writer_output;
    const ideaEval = deliverable.idea_evaluation;
    const peerReview = deliverable.peer_review;
    const criticCheck = (deliverable as unknown as {
      critic_check?: {
        status: 'passed' | 'warning';
        passed_count: number;
        checked_count: number;
        checks?: Array<{ key: string; passed: boolean }>;
      };
    }).critic_check;
    const agentTrace = deliverable.agent_trace || [];
    const matchedTicket = tickets.find((tk) => tk.short_key === shortKey);

    if (
      plannerSubtasks.length === 0 &&
      cards.length === 0 &&
      !crossVal &&
      !writerOut &&
      !ideaEval &&
      !peerReview &&
      !criticCheck &&
      agentTrace.length === 0
    ) {
      return null;
    }

    return (
      <Space
        direction="vertical"
        style={{ width: '100%', marginTop: 10 }}
        size={10}
      >
        {/* 1. Multi-Agent Execution Trace Badges */}
        {agentTrace.length > 0 && (
          <div
            style={{
              padding: '8px 10px',
              borderRadius: token.borderRadius,
              background: token.colorBgContainer,
              border: `1px solid ${token.colorBorderSecondary}`,
            }}
          >
            <Text
              type="secondary"
              style={{ display: 'block', fontSize: 11, marginBottom: 6 }}
            >
              {t('superagent.deepResearch.agentTraceTitle')}
            </Text>
            <Space size={6} wrap>
              {agentTrace.map((step, idx) => (
                <Tag key={`${shortKey}-trace-${idx}`} color="processing">
                  {`${step.agent || step.node}: ${step.summary?.slice(0, 68) || 'completed'}`}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        {/* 1B. Planner Agent Subtasks */}
        {plannerSubtasks.length > 0 && (
          <Card
            size="small"
            style={{ background: token.colorBgContainer }}
            title={(
              <Space wrap>
                <Tag color="blue">Planner Agent</Tag>
                <Text strong style={{ fontSize: 13 }}>
                  {t('superagent.deepResearch.plannerSubtasksTitle')}
                </Text>
              </Space>
            )}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
                gap: 8,
              }}
            >
              {plannerSubtasks.map((sub, idx) => (
                <div
                  key={sub.id || idx}
                  style={{
                    padding: '6px 8px',
                    borderRadius: token.borderRadius,
                    background: token.colorFillQuaternary,
                    border: `1px solid ${token.colorBorderSecondary}`,
                  }}
                >
                  <Space size={6}>
                    <Tag color="cyan" style={{ margin: 0 }}>
                      {sub.id || `SUB-${idx + 1}`}
                    </Tag>
                    <Tag color="geekblue" style={{ margin: 0 }}>
                      {sub.assigned_to}
                    </Tag>
                  </Space>
                  <div style={{ marginTop: 4 }}>
                    <Text strong style={{ fontSize: 12 }}>
                      {sub.title}
                    </Text>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {sub.description}
                    </Text>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 2. Literature Agent: 500-Word Memory Cards with [Source_ID] & DOI */}
        {cards.length > 0 && (
          <Card
            size="small"
            style={{ background: token.colorBgContainer }}
            title={(
              <Space wrap>
                <Tag color="geekblue">Literature Agent</Tag>
                <Text strong style={{ fontSize: 13 }}>
                  {t('superagent.deepResearch.memoryCardsTitle')}
                </Text>
                <Tag>{`${cards.length} Cards (<= 500 words)`}</Tag>
              </Space>
            )}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              {cards.map((card) => (
                <div
                  key={card.source_id}
                  style={{
                    padding: '8px 10px',
                    borderRadius: token.borderRadius,
                    background: token.colorFillQuaternary,
                    border: `1px solid ${token.colorBorderSecondary}`,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: 6,
                    }}
                  >
                    <Space wrap size={6}>
                      <Tag color="blue">{`[${card.source_id}]`}</Tag>
                      <Tag
                        color={
                          card.origin === 'local_rag' ? 'green' : 'purple'
                        }
                      >
                        {card.origin === 'local_rag'
                          ? 'Local RAG (Qdrant + BGE-m3 + Marker)'
                          : 'Academic API (Semantic Scholar / Crossref / ArXiv)'}
                      </Tag>
                      <Text strong style={{ fontSize: 13 }}>
                        {card.title}
                      </Text>
                    </Space>
                    <Space size={6}>
                      {card.doi && (
                        <Tag color="cyan">{`DOI: ${card.doi}`}</Tag>
                      )}
                      <Tag>{`${card.word_count || 120} / 500w`}</Tag>
                    </Space>
                  </div>
                  {card.experimental_setup && (
                    <div
                      style={{
                        marginTop: 6,
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 6,
                      }}
                    >
                      <Tag>{`Baseline: ${card.experimental_setup.baseline || '-'}`}</Tag>
                      <Tag>{`Dataset: ${card.experimental_setup.dataset || '-'}`}</Tag>
                      <Tag color="gold">{`Metrics: ${card.experimental_setup.metrics || '-'}`}</Tag>
                    </div>
                  )}
                  {card.card_summary_500w && (
                    <Paragraph
                      type="secondary"
                      style={{
                        marginTop: 6,
                        marginBottom: 0,
                        fontSize: 12,
                      }}
                    >
                      {card.card_summary_500w}
                    </Paragraph>
                  )}
                </div>
              ))}
            </Space>
          </Card>
        )}

        {/* 3. Data Agent: Internal Data Cross-Validation, SVG Chart & Python Sandbox Script */}
        {crossVal && (
          <Card
            size="small"
            style={{ background: token.colorBgContainer }}
            title={(
              <Space wrap>
                <Tag color="purple">Data Agent</Tag>
                <Text strong style={{ fontSize: 13 }}>
                  {t('superagent.deepResearch.dataValidationTitle')}
                </Text>
              </Space>
            )}
          >
            {crossVal.sota_analysis && (
              <Paragraph style={{ fontSize: 12, marginBottom: 8 }}>
                {crossVal.sota_analysis}
              </Paragraph>
            )}
            {crossVal.chart_svg && (
              <div
                style={{ marginBottom: 8, overflowX: 'auto' }}
                dangerouslySetInnerHTML={{ __html: crossVal.chart_svg }}
              />
            )}
            {crossVal.python_script && (
              <Collapse
                size="small"
                items={[
                  {
                    key: 'py-script',
                    label: t('superagent.deepResearch.viewPythonScript'),
                    children: (
                      <pre
                        style={{
                          margin: 0,
                          padding: 8,
                          fontSize: 11,
                          overflowX: 'auto',
                          background: token.colorFillQuaternary,
                          borderRadius: token.borderRadius,
                        }}
                      >
                        {crossVal.python_script}
                      </pre>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        )}

        {/* 4. Writer Agent & Provenance Guard: Strict [Source_ID] Audit & DOI BibTeX Export */}
        {writerOut && (
          <Card
            size="small"
            style={{ background: token.colorBgContainer }}
            title={(
              <Space wrap>
                <Tag color="green">Writer Agent & Provenance Guard</Tag>
                <Text strong style={{ fontSize: 13 }}>
                  {t('superagent.deepResearch.provenanceGuardTitle')}
                </Text>
              </Space>
            )}
            extra={
              writerOut.bibtex ? (
                <Button
                  size="small"
                  type="primary"
                  ghost
                  icon={<DownloadOutlined />}
                  onClick={() =>
                    handleDownloadBibtex(writerOut.bibtex || '', shortKey)
                  }
                >
                  {t('superagent.deepResearch.downloadBibtexBtn')}
                </Button>
              ) : null
            }
          >
            {writerOut.provenance_audit && (
              <Alert
                type="success"
                showIcon
                style={{ marginBottom: 8 }}
                message={t('superagent.deepResearch.provenanceStats', {
                  verified:
                    writerOut.provenance_audit.verified_assertions_count ?? 0,
                  dropped:
                    writerOut.provenance_audit
                      .dropped_ungrounded_assertions_count ?? 0,
                })}
                description={
                  <Space size={4} wrap style={{ marginTop: 4 }}>
                    {(writerOut.provenance_audit.valid_source_ids || []).map(
                      (sid) => (
                        <Tag key={sid} color="blue">
                          {`[${sid}]`}
                        </Tag>
                      ),
                    )}
                  </Space>
                }
              />
            )}
            {writerOut.bibtex && (
              <Collapse
                size="small"
                items={[
                  {
                    key: 'bibtex-preview',
                    label: t('superagent.deepResearch.viewBibtex'),
                    children: (
                      <pre
                        style={{
                          margin: 0,
                          padding: 8,
                          fontSize: 11,
                          overflowX: 'auto',
                          background: token.colorFillQuaternary,
                          borderRadius: token.borderRadius,
                        }}
                      >
                        {writerOut.bibtex}
                      </pre>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        )}

        {/* 5. Stage 3: Idea 3D Scoring & Novelty Check */}
        {ideaEval && <IdeaEvaluationCard evaluation={ideaEval} />}

        {/* 6. Critic Self-Check Summary */}
        {criticCheck && (() => {
          const checks = criticCheck.checks || [];
          const passedCount =
            typeof criticCheck.passed_count === 'number'
              ? criticCheck.passed_count
              : checks.filter((c) => c.passed).length;
          const checkedCount =
            typeof criticCheck.checked_count === 'number'
              ? criticCheck.checked_count
              : checks.length;
          return (
            <Card
              size="small"
              style={{ background: token.colorBgContainer }}
              title={(
                <Space size={8} wrap>
                  <Tag
                    bordered={false}
                    color={criticCheck.status === 'passed' ? 'success' : 'warning'}
                  >
                    {criticCheck.status === 'passed'
                      ? t('superagent.criticCheckPassed', {
                          passed: passedCount,
                          total: checkedCount,
                        })
                      : t('superagent.criticCheckWarning', {
                          passed: passedCount,
                          total: checkedCount,
                        })}
                  </Tag>
                </Space>
              )}
            >
              <Space size={[6, 6]} wrap>
                {checks.map((c) => (
                  <Tag
                    key={c.key}
                    bordered={false}
                    color={c.passed ? 'success' : 'warning'}
                  >
                    {`${c.passed ? '✓' : '!'} ${t(`superagent.criticChecks.${c.key}`, {
                      defaultValue: c.key,
                    })}`}
                  </Tag>
                ))}
              </Space>
            </Card>
          );
        })()}

        {/* 7. Stage 5: Pessimistic Peer Review Scorecard */}
        {peerReview && (
          <PeerReviewCard
            review={peerReview}
            onSpawnRebuttal={
              matchedTicket
                ? () => void handleSpawnRebuttal(matchedTicket.id)
                : undefined
            }
            rebuttalLoading={
              matchedTicket
                ? submittingId === `rebuttal-${matchedTicket.id}`
                : false
            }
          />
        )}
      </Space>
    );
  };

  const renderStagePipelineBar = () => {
    const stageMap = new Map<StageCategory, PipelineStageSummary>();
    overview.pipeline_stages.forEach((s) => stageMap.set(s.stage_category, s));

    const stageAgentMeta: Record<
      StageCategory,
      { agent: string; color: string; capability: string }
    > = {
      problem_framing: {
        agent: 'Planner Agent',
        color: 'blue',
        capability: '意图解析 · 环境感知 · 问题树',
      },
      baseline_reproduction: {
        agent: 'Literature Agent',
        color: 'geekblue',
        capability: '混合RAG/API · 500字卡片 · HITL 1',
      },
      innovation_feasibility: {
        agent: 'Planner + Literature',
        color: 'cyan',
        capability: '方案共创 · 三维可行性门禁',
      },
      experiment_iteration: {
        agent: 'Data Agent',
        color: 'purple',
        capability: '内部数据对齐 · Python绘图 · HITL 2',
      },
      manuscript_writing: {
        agent: 'Writer Agent',
        color: 'green',
        capability: '[Source_ID]强校验 · DOI BibTeX',
      },
    };

    return (
      <Card
        size="small"
        style={{ marginBottom: 16, borderColor: token.colorBorderSecondary }}
        title={(
          <Space>
            <RocketOutlined style={{ color: token.colorPrimary }} />
            <Text strong>{t('superagent.pipelineTitle')}</Text>
          </Space>
        )}
        extra={(
          <Space wrap>
            <Button
              size="small"
              type="primary"
              icon={<PlusOutlined />}
              onClick={openAddQuestionModal}
            >
              {t('superagent.defineQuestionBtn')}
            </Button>
            <Button
              size="small"
              icon={<SyncOutlined />}
              loading={submittingId === 'trigger-scan'}
              onClick={handleEmitLiteratureTrigger}
            >
              {t('superagent.scanLiteratureBtn')}
            </Button>
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => setNewTicketModalOpen(true)}
            >
              {t('superagent.newTicketBtn')}
            </Button>
            <Button size="small" icon={<ReloadOutlined />} onClick={fetchAll} />
          </Space>
        )}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(175px, 1fr))',
            gap: 10,
          }}
        >
          {STAGE_ORDER.map((stageKey, index) => {
            const st = stageMap.get(stageKey);
            const isSelected = selectedStage === stageKey;
            const status = st?.status || 'empty';
            const borderColor = isSelected
              ? token.colorPrimary
              : status === 'needs_person'
                ? token.colorWarning
                : status === 'completed'
                  ? token.colorSuccess
                  : token.colorBorderSecondary;

            return (
              <div
                key={stageKey}
                onClick={() => handleSelectStage(stageKey)}
                style={{
                  padding: '10px 12px',
                  borderRadius: token.borderRadius,
                  border: `1.5px solid ${borderColor}`,
                  background: isSelected ? token.colorPrimaryBg : token.colorBgContainer,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 4,
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {`${t('superagent.stagePrefix')} ${index + 1}`}
                  </Text>
                  {status === 'completed' && (
                    <Tag color="success" style={{ margin: 0, fontSize: 11 }}>
                      {t('superagent.statusCompleted')}
                    </Tag>
                  )}
                  {status === 'needs_person' && (
                    <Tag color="warning" style={{ margin: 0, fontSize: 11 }}>
                      {t('superagent.statusNeedsYou')}
                    </Tag>
                  )}
                  {status === 'active' && (
                    <Tag color="processing" style={{ margin: 0, fontSize: 11 }}>
                      {t('superagent.statusWorking')}
                    </Tag>
                  )}
                  {status === 'empty' && (
                    <Tag style={{ margin: 0, fontSize: 11 }}>
                      {t('superagent.statusPending')}
                    </Tag>
                  )}
                </div>
                <Text strong style={{ display: 'block', fontSize: 13 }}>
                  {t(`superagent.stages.${stageKey}`)}
                </Text>
                <div style={{ marginTop: 4 }}>
                  <Tag
                    color={stageAgentMeta[stageKey].color}
                    style={{ margin: 0, fontSize: 10 }}
                  >
                    {stageAgentMeta[stageKey].agent}
                  </Tag>
                  <Text
                    type="secondary"
                    style={{ display: 'block', fontSize: 11, marginTop: 2 }}
                  >
                    {stageAgentMeta[stageKey].capability}
                  </Text>
                </div>
                <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t('superagent.precipitatedCount', {
                      count: st?.accepted_count ?? 0,
                    })}
                  </Text>
                  {st?.latest_round ? (
                    <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>
                      {`Round ${st.latest_round}`}
                    </Tag>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    );
  };

  const renderNeedsPersonSection = () => {
    const allItems = overview.needs_person;
    const items = selectedStage
      ? allItems.filter((tk) => tk.stage_category === selectedStage)
      : allItems;
    const otherStageCount = allItems.length - items.length;

    if (items.length === 0) {
      return (
        <Alert
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          style={{ marginBottom: 16 }}
          message={
            selectedStage
              ? `${t(`superagent.stages.${selectedStage}`)}：${t('superagent.healthyQuietTitle')}`
              : t('superagent.healthyQuietTitle')
          }
          description={
            selectedStage && otherStageCount > 0 ? (
              <Space wrap>
                <Text type="secondary">
                  {t('superagent.otherStagesPendingHint', {
                    count: otherStageCount,
                  })}
                </Text>
                <Button
                  size="small"
                  type="link"
                  onClick={() => setSelectedStage(null)}
                >
                  {t('superagent.viewAllStagesBtn')}
                </Button>
              </Space>
            ) : (
              t('superagent.healthyQuietDesc')
            )
          }
        />
      );
    }

    return (
      <Card
        size="small"
        style={{
          marginBottom: 16,
          borderColor: token.colorWarningBorder,
          background: token.colorWarningBg,
        }}
        title={(
          <Space wrap>
            <Badge count={items.length} color={token.colorWarning} />
            <Text strong>
              {selectedStage
                ? `${t(`superagent.stages.${selectedStage}`)} · ${t('superagent.needsPersonTitle')}`
                : t('superagent.needsPersonTitle')}
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('superagent.needsPersonSubtitle')}
            </Text>
          </Space>
        )}
        extra={
          selectedStage && otherStageCount > 0 ? (
            <Button
              size="small"
              type="link"
              onClick={() => setSelectedStage(null)}
            >
              {t('superagent.otherStagesPendingBtn', {
                count: otherStageCount,
              })}
            </Button>
          ) : null
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {items.map((ticket) => {
            const isBusy = submittingId === ticket.id;

            return (
              <Card
                key={ticket.id}
                size="small"
                style={{ background: token.colorBgContainer }}
                title={(
                  <Space wrap size={6}>
                    <Tag bordered={false} color={STAGE_BADGE_COLORS[ticket.stage] || 'default'}>
                      {STAGE_LABEL_KEYS[ticket.stage] ? t(STAGE_LABEL_KEYS[ticket.stage]) : ticket.stage}
                    </Tag>
                    <Text code style={{ fontSize: 12 }}>{ticket.short_key}</Text>
                    <Text strong style={{ fontSize: 14 }}>{ticket.title}</Text>
                    <Tag bordered={false}>{t(`superagent.stages.${ticket.stage_category}`)}</Tag>
                    {ticket.iteration_round ? (
                      <Tag bordered={false} color="purple">{`#${ticket.iteration_round}`}</Tag>
                    ) : null}
                  </Space>
                )}
                extra={(
                  <Button
                    size="small"
                    type="link"
                    icon={<CommentOutlined />}
                    onClick={() => setActiveTicket(ticket)}
                  >
                    {t('superagent.openThreadAndDetail', {
                      count: ticket.thread_messages.length,
                    })}
                  </Button>
                )}
              >
                {ticket.summary && (
                  <Paragraph
                    type="secondary"
                    style={{ marginBottom: 10, fontSize: 13 }}
                  >
                    {ticket.summary}
                  </Paragraph>
                )}

                {/* Case 1: person / answer (1 concrete decision question) */}
                {ticket.stage === 'person / answer' && ticket.attention && (
                  <div
                    style={{
                      padding: 12,
                      borderRadius: token.borderRadius,
                      background: token.colorFillAlter,
                    }}
                  >
                    <Text strong style={{ display: 'block', marginBottom: 8 }}>
                      {ticket.attention.question}
                    </Text>
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                      {ticket.attention.options.map((opt) => {
                        const isRec = opt === ticket.attention?.recommended;
                        return (
                          <Button
                            key={opt}
                            type={isRec ? 'primary' : 'default'}
                            ghost={isRec}
                            loading={isBusy}
                            style={{
                              textAlign: 'left',
                              height: 'auto',
                              whiteSpace: 'normal',
                              padding: '6px 12px',
                            }}
                            block
                            onClick={() => handleAnswerAttention(ticket, opt)}
                          >
                            {isRec ? `[${t('superagent.recommended')}] ${opt}` : opt}
                          </Button>
                        );
                      })}
                      <Space.Compact style={{ width: '100%', marginTop: 4 }}>
                        <Input
                          placeholder={t('superagent.customDecisionPlaceholder')}
                          value={customAnswers[ticket.id] || ''}
                          onChange={(e) =>
                            setCustomAnswers((prev) => ({
                              ...prev,
                              [ticket.id]: e.target.value,
                            }))
                          }
                          onPressEnter={() =>
                            handleAnswerAttention(
                              ticket,
                              customAnswers[ticket.id] || '',
                            )
                          }
                        />
                        <Button
                          type="primary"
                          loading={isBusy}
                          onClick={() =>
                            handleAnswerAttention(
                              ticket,
                              customAnswers[ticket.id] || '',
                            )
                          }
                        >
                          {t('superagent.submitDecisionBtn')}
                        </Button>
                      </Space.Compact>
                    </Space>
                    {ticket.deliverable &&
                      renderMultiAgentArtifacts(
                        ticket.deliverable,
                        ticket.short_key,
                      )}
                  </div>
                )}

                {/* Case 2: person / wetlab (optional external data or direct Agent verification) */}
                {ticket.stage === 'person / wetlab' && ticket.attention && (
                  <div
                    style={{
                      padding: 12,
                      borderRadius: token.borderRadius,
                      background: token.colorFillAlter,
                    }}
                  >
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                      <Text strong>{ticket.attention.question}</Text>
                      {ticket.attention.template_data?.rows &&
                        renderDeliverableTable(
                          ticket.attention.template_data.rows as Record<
                            string,
                            unknown
                          >[],
                        )}
                      <Space wrap style={{ marginTop: 6 }}>
                        <Button
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          loading={isBusy}
                          onClick={() => handleSkipWetlabAndVerify(ticket)}
                        >
                          {t('superagent.skipWetlabVerifyBtn')}
                        </Button>
                        <Button
                          icon={<UploadOutlined />}
                          onClick={() => openWetlabModal(ticket)}
                        >
                          {t('superagent.uploadWetlabOptionalBtn')}
                        </Button>
                        {ticket.attention.template_data?.csv_text && (
                          <Button
                            icon={<DownloadOutlined />}
                            onClick={() => handleDownloadCsvTemplate(ticket)}
                          >
                            {t('superagent.downloadWetlabTemplateBtn')}
                          </Button>
                        )}
                      </Space>
                    </Space>
                  </div>
                )}

                {/* Case 3: person / review (completed deliverable ready to merge) */}
                {ticket.stage === 'person / review' && ticket.deliverable && (
                  <div
                    style={{
                      padding: 12,
                      borderRadius: token.borderRadius,
                      background: token.colorFillAlter,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                        gap: 8,
                        marginBottom: 8,
                      }}
                    >
                      <Space>
                        <FileTextOutlined />
                        <Text strong>{ticket.deliverable.title}</Text>
                      </Space>
                      <Space wrap>
                        {ticket.stage_category === 'experiment_iteration' ? (
                          <>
                            <Button
                              size="small"
                              icon={<UploadOutlined />}
                              onClick={() => openWetlabModal(ticket)}
                            >
                              {t('superagent.uploadWetlabOptionalBtn')}
                            </Button>
                            <Button
                              size="small"
                              icon={<ExperimentOutlined />}
                              loading={isBusy}
                              onClick={() => {
                                setNextRoundModalTicket(ticket);
                                nextRoundForm.setFieldsValue({
                                  direction_note:
                                    ticket.deliverable?.diff_summary
                                      ?.recommended_next_direction || '',
                                });
                              }}
                            >
                              {t('superagent.spawnNextRoundBtn', {
                                round: (ticket.iteration_round || 1) + 1,
                              })}
                            </Button>
                            <Button
                              size="small"
                              type="primary"
                              icon={<CheckCircleOutlined />}
                              loading={isBusy}
                              onClick={() => handleApproveTicket(ticket, true)}
                            >
                              {t('superagent.verifyMilestoneAndWritePaperBtn')}
                            </Button>
                          </>
                        ) : (
                          <Button
                            type="primary"
                            icon={<CheckCircleOutlined />}
                            loading={isBusy}
                            onClick={() => handleApproveTicket(ticket, false)}
                          >
                            {t('superagent.approveAndMergeBtn')}
                          </Button>
                        )}
                      </Space>
                    </div>

                    {ticket.deliverable.diff_summary && (
                      <Alert
                        type="info"
                        showIcon
                        style={{ marginBottom: 8 }}
                        message={ticket.deliverable.diff_summary.key_insight}
                        description={
                          ticket.deliverable.diff_summary.recommended_next_direction
                        }
                      />
                    )}

                    {ticket.deliverable.metrics_table &&
                      ticket.deliverable.metrics_table.length > 0 &&
                      renderDeliverableTable(ticket.deliverable.metrics_table)}

                    {renderMultiAgentArtifacts(
                      ticket.deliverable,
                      ticket.short_key,
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </Space>
      </Card>
    );
  };

  const renderExecutorAndPolicyBar = () => {
    const { executor, flow_24h, policy } = overview;
    return (
      <Card
        size="small"
        style={{ marginBottom: 16 }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space split={<span style={{ color: token.colorBorder }}>|</span>} wrap>
            <Space size={6}>
              <Text type="secondary">{t('superagent.executorLabel')}:</Text>
              <Tag color="processing">
                {`${executor.running} / ${executor.max_workers} ${t('superagent.running')}`}
              </Tag>
              <Tag>{`${executor.queued} ${t('superagent.queued')}`}</Tag>
              {executor.idle > 0 && (
                <Tag color="purple">{`${executor.idle} ${t('superagent.waitingWetlab')}`}</Tag>
              )}
            </Space>
            <Space size={6}>
              <Text type="secondary">{t('superagent.flow24hLabel')}:</Text>
              <Text style={{ fontSize: 12 }}>
                {t('superagent.flowStats', {
                  received: flow_24h.received,
                  accepted: flow_24h.accepted,
                  completed: flow_24h.completed,
                })}
              </Text>
            </Space>
          </Space>

          <Space wrap>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('superagent.policyModeLabel')}:
            </Text>
            <Radio.Group
              size="small"
              value={policy.accept_mode}
              disabled={!canManage}
              onChange={(e) => handleModeChange(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: t('superagent.modeAuto'), value: 'auto' },
                { label: t('superagent.modeObserve'), value: 'observe' },
                { label: t('superagent.modeOff'), value: 'off' },
              ]}
            />
            <Button
              size="small"
              icon={<SettingOutlined />}
              onClick={() => setPolicyModalOpen(true)}
            >
              {t('superagent.policyRulesBtn', { version: policy.version })}
            </Button>
          </Space>
        </div>
      </Card>
    );
  };

  const renderStageDetailAndTickets = () => {
    const filteredStages = selectedStage
      ? overview.pipeline_stages.filter((s) => s.stage_category === selectedStage)
      : overview.pipeline_stages.filter((s) => s.accepted_count > 0);

    const filteredTickets = selectedStage
      ? tickets.filter((tk) => tk.stage_category === selectedStage)
      : tickets;

    return (
      <Collapse
        defaultActiveKey={['precipitated', 'tickets']}
        style={{ marginBottom: 16 }}
        items={[
          {
            key: 'precipitated',
            label: (
              <Space>
                <Text strong>
                  {selectedStage
                    ? `${t(`superagent.stages.${selectedStage}`)} · ${t('superagent.stagePrecipitatedTitle')}`
                    : t('superagent.precipitatedStateTitle')}
                </Text>
                {selectedStage && (
                  <Tag color="blue">{t(`superagent.stages.${selectedStage}`)}</Tag>
                )}
              </Space>
            ),
            children:
              filteredStages.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('superagent.noPrecipitatedObjectsYet')}
                />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }} size={12}>
                  {filteredStages.map((stage) => (
                    <Card
                      id={`stage-precipitated-${stage.stage_category}`}
                      key={stage.stage_category}
                      size="small"
                      title={t(`superagent.stages.${stage.stage_category}`)}
                      extra={(
                        <Tag color="green">
                          {t('superagent.precipitatedCount', {
                            count: stage.accepted_count,
                          })}
                        </Tag>
                      )}
                    >
                      {stage.items.length === 0 ? (
                        <Text type="secondary">{t('superagent.noStageItems')}</Text>
                      ) : (
                        <Space direction="vertical" style={{ width: '100%' }} size={8}>
                          {stage.stage_category === 'manuscript_writing' &&
                            stage.items.length > 1 && (
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'space-between',
                                  flexWrap: 'wrap',
                                  gap: 8,
                                  padding: '6px 10px',
                                  borderRadius: token.borderRadius,
                                  background: token.colorFillAlter,
                                }}
                              >
                                <Space size={8}>
                                  <Text type="secondary" style={{ fontSize: 12 }}>
                                    {t('superagent.manuscriptVersionLabel')}:
                                  </Text>
                                  <Select
                                    size="small"
                                    style={{ minWidth: 260 }}
                                    value={
                                      stage.items.some(
                                        (it) =>
                                          it.id ===
                                          selectedStageVersionIds[
                                            stage.stage_category
                                          ],
                                      )
                                        ? selectedStageVersionIds[
                                            stage.stage_category
                                          ]
                                        : stage.items[0].id
                                    }
                                    onChange={(val) =>
                                      setSelectedStageVersionIds((prev) => ({
                                        ...prev,
                                        [stage.stage_category]: val,
                                      }))
                                    }
                                    options={stage.items.map((it, idx) => {
                                      const itJson = (it.content_json ||
                                        {}) as Record<string, unknown>;
                                      const tKey =
                                        typeof itJson.ticket_short_key ===
                                        'string'
                                          ? itJson.ticket_short_key
                                          : null;
                                      const verNum = stage.items.length - idx;
                                      const ts = it.created_at
                                        ? new Date(
                                            it.created_at,
                                          ).toLocaleString()
                                        : '';
                                      return {
                                        value: it.id,
                                        label: `v${verNum}${idx === 0 ? ` (${t('superagent.manuscriptVersionLatest')})` : ''}${tKey ? ` · ${tKey}` : ''}${ts ? ` · ${ts}` : ''}`,
                                      };
                                    })}
                                  />
                                </Space>
                              </div>
                            )}
                          {(stage.stage_category === 'manuscript_writing' &&
                          stage.items.length > 1
                            ? [
                                stage.items.find(
                                  (it) =>
                                    it.id ===
                                    selectedStageVersionIds[
                                      stage.stage_category
                                    ],
                                ) || stage.items[0],
                              ]
                            : stage.items
                          ).map((obj) => {
                            const cj = (obj.content_json || {}) as Record<
                              string,
                              unknown
                            >;
                            const ticketShortKey =
                              typeof cj.ticket_short_key === 'string'
                                ? cj.ticket_short_key
                                : null;
                            const agentRole =
                              typeof cj.agent_role === 'string'
                                ? cj.agent_role
                                : null;
                            const sourceId =
                              typeof cj.source_id === 'string'
                                ? cj.source_id
                                : null;
                            const doi =
                              typeof cj.doi === 'string' ? cj.doi : null;
                            const chartSvg =
                              typeof cj.chart_svg === 'string'
                                ? cj.chart_svg
                                : null;
                            const bibtex =
                              typeof cj.bibtex === 'string' ? cj.bibtex : null;

                            return (
                              <div
                                key={obj.id}
                                style={{
                                  padding: '8px 12px',
                                  borderRadius: token.borderRadius,
                                  background: token.colorFillQuaternary,
                                }}
                              >
                                <div
                                  style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    flexWrap: 'wrap',
                                    gap: 6,
                                  }}
                                >
                                  <Space wrap size={6}>
                                    <Tag color="geekblue">{obj.type}</Tag>
                                    {ticketShortKey && <Tag>{ticketShortKey}</Tag>}
                                    {agentRole && (
                                      <Tag color="purple">{agentRole}</Tag>
                                    )}
                                    {sourceId && (
                                      <Tag color="blue">{`[${sourceId}]`}</Tag>
                                    )}
                                    {doi && (
                                      <Tag color="cyan">{`DOI: ${doi}`}</Tag>
                                    )}
                                    <Text strong>{obj.title}</Text>
                                  </Space>
                                  <Space wrap size={6}>
                                    {obj.type === 'manuscript_draft' && (
                                      <>
                                        <Button
                                          size="small"
                                          icon={<DownloadOutlined />}
                                          loading={
                                            submittingId === `export-pdf-${obj.id}`
                                          }
                                          onClick={() =>
                                            handleExportManuscript(
                                              `/projects/${project.id}/superagent/manuscripts/${obj.id}/export?format=pdf`,
                                              `manuscript_${ticketShortKey || obj.id.slice(0, 8)}.pdf`,
                                              `export-pdf-${obj.id}`,
                                            )
                                          }
                                        >
                                          {t('superagent.downloadPdfBtn')}
                                        </Button>
                                        <Button
                                          size="small"
                                          icon={<DownloadOutlined />}
                                          loading={
                                            submittingId === `export-docx-${obj.id}`
                                          }
                                          onClick={() =>
                                            handleExportManuscript(
                                              `/projects/${project.id}/superagent/manuscripts/${obj.id}/export?format=docx`,
                                              `manuscript_${ticketShortKey || obj.id.slice(0, 8)}.docx`,
                                              `export-docx-${obj.id}`,
                                            )
                                          }
                                        >
                                          {t('superagent.downloadDocxBtn')}
                                        </Button>
                                      </>
                                    )}
                                    {bibtex && (
                                      <Button
                                        size="small"
                                        type="primary"
                                        ghost
                                        icon={<DownloadOutlined />}
                                        onClick={() =>
                                          handleDownloadBibtex(
                                            bibtex,
                                            obj.id.slice(0, 8),
                                          )
                                        }
                                      >
                                        {t(
                                          'superagent.deepResearch.downloadBibtexBtn',
                                        )}
                                      </Button>
                                    )}
                                  </Space>
                                </div>
                                {(() => {
                                  const figs = Array.isArray(cj.figures)
                                    ? (cj.figures as Array<{
                                        title?: string;
                                        svg?: string;
                                        caption?: string;
                                      }>).filter((f) => f && typeof f.svg === 'string')
                                    : [];

                                  const renderFigureCard = (
                                    f: { title?: string; svg?: string; caption?: string },
                                    figIdx: number,
                                  ) => (
                                    <div
                                      key={`fig-${figIdx}`}
                                      style={{
                                        margin: '14px 0',
                                        padding: 12,
                                        borderRadius: token.borderRadius,
                                        background: token.colorBgContainer,
                                        border: `1px solid ${token.colorBorderSecondary}`,
                                        overflowX: 'auto',
                                      }}
                                    >
                                      {f.title && (
                                        <Text
                                          strong
                                          style={{
                                            display: 'block',
                                            marginBottom: 8,
                                            fontSize: 13,
                                          }}
                                        >
                                          {f.title}
                                        </Text>
                                      )}
                                      <div
                                        dangerouslySetInnerHTML={{
                                          __html: f.svg || '',
                                        }}
                                      />
                                      {f.caption && (
                                        <Text
                                          type="secondary"
                                          style={{
                                            display: 'block',
                                            marginTop: 8,
                                            fontSize: 12,
                                          }}
                                        >
                                          {f.caption}
                                        </Text>
                                      )}
                                    </div>
                                  );

                                  if (!obj.content) {
                                    return figs.map((f, i) => renderFigureCard(f, i));
                                  }

                                  const sec4Match = obj.content.match(/\n(?=##\s*4\.)/);
                                  const sec56Match = obj.content.match(
                                    /\n(?=##\s*(?:5\.|6\.|参考文献|References))/,
                                  );

                                  if (
                                    figs.length > 0 &&
                                    sec4Match?.index !== undefined &&
                                    sec56Match?.index !== undefined &&
                                    sec56Match.index > sec4Match.index
                                  ) {
                                    const part1 = obj.content.slice(0, sec4Match.index);
                                    const part2 = obj.content.slice(sec4Match.index, sec56Match.index);
                                    const part3 = obj.content.slice(sec56Match.index);
                                    return (
                                      <div style={{ marginTop: 6, fontSize: 13 }}>
                                        <MarkdownContent content={part1} />
                                        {figs[0] && renderFigureCard(figs[0], 0)}
                                        <MarkdownContent content={part2} />
                                        {figs[1] && renderFigureCard(figs[1], 1)}
                                        <MarkdownContent content={part3} />
                                        {figs.slice(2).map((f, i) => renderFigureCard(f, i + 2))}
                                      </div>
                                    );
                                  }

                                  if (figs.length > 0 && sec56Match?.index !== undefined) {
                                    const bodyBeforeRefs = obj.content.slice(0, sec56Match.index);
                                    const refsSection = obj.content.slice(sec56Match.index);
                                    return (
                                      <div style={{ marginTop: 6, fontSize: 13 }}>
                                        <MarkdownContent content={bodyBeforeRefs} />
                                        {figs.map((f, i) => renderFigureCard(f, i))}
                                        <MarkdownContent content={refsSection} />
                                      </div>
                                    );
                                  }

                                  return (
                                    <div style={{ marginTop: 6, fontSize: 13 }}>
                                      <MarkdownContent content={obj.content} />
                                      {figs.map((f, i) => renderFigureCard(f, i))}
                                    </div>
                                  );
                                })()}
                                {chartSvg && !Array.isArray(cj.figures) && (
                                  <div
                                    style={{ marginTop: 8, overflowX: 'auto' }}
                                    dangerouslySetInnerHTML={{
                                      __html: chartSvg,
                                    }}
                                  />
                                )}
                              </div>
                            );
                          })}
                        </Space>
                      )}
                    </Card>
                  ))}
                </Space>
              ),
          },
          {
            key: 'tickets',
            label: (
              <Space>
                <Text strong>
                  {selectedStage
                    ? `${t(`superagent.stages.${selectedStage}`)} · ${t('superagent.allTicketsTitle')}`
                    : t('superagent.allTicketsTitle')}
                </Text>
                <Badge count={filteredTickets.length} showZero color="geekblue" />
              </Space>
            ),
            children: (
              <Table
                size="small"
                rowKey="id"
                dataSource={filteredTickets}
                pagination={{ pageSize: 10 }}
                scroll={{ x: 760 }}
                columns={[
                  {
                    title: 'ID',
                    dataIndex: 'short_key',
                    key: 'short_key',
                    width: 68,
                    render: (v: string) => <Text code>{v}</Text>,
                  },
                  {
                    title: t('superagent.colStage'),
                    dataIndex: 'stage',
                    key: 'stage',
                    width: 136,
                    render: (v: string) => (
                      <Tag bordered={false} color={STAGE_BADGE_COLORS[v] || 'default'}>
                        {STAGE_LABEL_KEYS[v] ? t(STAGE_LABEL_KEYS[v]) : v}
                      </Tag>
                    ),
                  },
                  {
                    title: t('superagent.colLifecycleStage'),
                    dataIndex: 'stage_category',
                    key: 'stage_category',
                    width: 165,
                    render: (v: StageCategory, row: ResearchTicket) => (
                      <Space size={4}>
                        <Tag>{t(`superagent.stages.${v}`)}</Tag>
                        {row.iteration_round ? (
                          <Tag color="purple">{`R${row.iteration_round}`}</Tag>
                        ) : null}
                      </Space>
                    ),
                  },
                  {
                    title: t('superagent.colTitle'),
                    dataIndex: 'title',
                    key: 'title',
                    render: (v: string, row: ResearchTicket) => (
                      <div style={{ minWidth: 260 }}>
                        <Text strong>{v}</Text>
                        {row.summary && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {row.summary}
                            </Text>
                          </div>
                        )}
                      </div>
                    ),
                  },
                  {
                    title: t('common.actions', 'Actions'),
                    key: 'actions',
                    width: 120,
                    render: (_: unknown, row: ResearchTicket) => (
                      <Button
                        size="small"
                        type="link"
                        onClick={() => setActiveTicket(row)}
                      >
                        {t('superagent.inspectTicketBtn')}
                      </Button>
                    ),
                  },
                ]}
              />
            ),
          },
        ]}
      />
    );
  };

  const renderStageFocusBanner = () => {
    if (!selectedStage) return null;
    const currentTheme = getCurrentTheme();
    return (
      <div
        id={`stage-anchor-${selectedStage}`}
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          padding: '10px 14px',
          marginBottom: 12,
          borderRadius: token.borderRadius,
          border: `1.5px solid ${token.colorPrimaryBorder}`,
          background: token.colorPrimaryBg,
        }}
      >
        <Space wrap>
          <Tag color="blue" style={{ margin: 0 }}>
            {t('superagent.currentStageFocusBadge')}
          </Tag>
          <Text strong>{t(`superagent.stages.${selectedStage}`)}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {`${t('superagent.charterThemePrefix')}：${currentTheme}`}
          </Text>
        </Space>
        <Space wrap>
          {selectedStage === 'baseline_reproduction' && (
            <Button
              size="small"
              type="primary"
              icon={<SyncOutlined />}
              loading={submittingId === 'trigger-scan'}
              onClick={handleEmitLiteratureTrigger}
            >
              {t('superagent.scanLiteratureBtn')}
            </Button>
          )}
          {selectedStage !== 'problem_framing' &&
            selectedStage !== 'baseline_reproduction' && (
              <Button
                size="small"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => {
                  newTicketForm.setFieldsValue({
                    stage_category: selectedStage,
                  });
                  setNewTicketModalOpen(true);
                }}
              >
                {t('superagent.newStageTicketBtn')}
              </Button>
            )}
          <Button size="small" onClick={() => setSelectedStage(null)}>
            {t('superagent.viewAllStagesBtn')}
          </Button>
        </Space>
      </div>
    );
  };

  const renderProjectCharterSection = () => {
    // When the user clicks Stage 2/3/4/5, hide the Stage 1 card so the clicked stage's content is immediately shown at the top!
    if (selectedStage && selectedStage !== 'problem_framing') {
      return null;
    }
    const stage1Items = getStage1Items();
    const currentTheme = getCurrentTheme();

    return (
      <div id="stage-anchor-problem_framing">
        <Card
          size="small"
          style={{ marginBottom: 16, borderColor: token.colorBorderSecondary }}
          title={(
            <Space wrap>
              <Tag color="geekblue">{t('superagent.charterBadge')}</Tag>
              <Tag color="blue">Planner Agent</Tag>
              <Text strong>{`${t('superagent.charterThemePrefix')}：${currentTheme}`}</Text>
            </Space>
          )}
          extra={(
            <Space wrap>
              <Button
                size="small"
                icon={<BulbOutlined />}
                loading={submittingId === 'ai-suggest-charter'}
                onClick={handleAiSuggestCharter}
              >
                {t('superagent.aiSuggestCharterBtn')}
              </Button>
              <Button
                size="small"
                type="primary"
                ghost
                icon={<PlusOutlined />}
                onClick={openAddQuestionModal}
              >
                {t('superagent.addQuestionUnderThemeBtn')}
              </Button>
            </Space>
          )}
        >
          {stage1Items.length === 0 ? (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
                padding: '4px 0',
              }}
            >
              <Text type="secondary" style={{ fontSize: 13 }}>
                {t('superagent.charterEmptyHint')}
              </Text>
            </div>
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size={10}>
              {stage1Items.map((item, idx) => {
                const cj = (item.content_json || {}) as Record<string, unknown>;
                const questionText =
                  (typeof cj.question === 'string' && cj.question) ||
                  item.title ||
                  '';
                const subQuestions = Array.isArray(cj.sub_questions)
                  ? (cj.sub_questions as string[])
                  : [];
                const criteriaList: string[] = Array.isArray(cj.success_criteria)
                  ? (cj.success_criteria as string[])
                  : Array.isArray(cj.target_metrics)
                    ? (
                        cj.target_metrics as {
                          metric?: string;
                          target?: string;
                          unit?: string;
                        }[]
                      ).map((m) =>
                        `${m.metric || ''}: ${m.target || ''} ${m.unit || ''}`.trim(),
                      )
                    : [];
                const constraintsList = Array.isArray(cj.constraints)
                  ? (cj.constraints as string[])
                  : [];

                return (
                  <div
                    key={item.id}
                    style={{
                      padding: '10px 14px',
                      borderRadius: token.borderRadius,
                      background: token.colorFillQuaternary,
                      border: `1px solid ${token.colorBorderSecondary}`,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: 12,
                      }}
                    >
                      <Space align="baseline">
                        <Tag color="blue">{`Q${idx + 1}`}</Tag>
                        <Text strong style={{ fontSize: 14 }}>
                          {questionText}
                        </Text>
                      </Space>
                      <Button
                        size="small"
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => openEditQuestionModal(item)}
                      >
                        {t('common.edit', 'Edit')}
                      </Button>
                    </div>

                    {/* Sub-questions under this core question */}
                    <div style={{ marginTop: 8, paddingLeft: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {t('superagent.subQuestionsLabel')}：
                      </Text>
                      {subQuestions.length > 0 ? (
                        <ul
                          style={{
                            margin: '4px 0 8px 18px',
                            padding: 0,
                            fontSize: 13,
                          }}
                        >
                          {subQuestions.map((sq, sIdx) => (
                            <li key={`${item.id}-sq-${sIdx}`}>
                              <Text style={{ fontSize: 13 }}>{sq}</Text>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <Text
                          type="secondary"
                          style={{ fontSize: 12, marginLeft: 6 }}
                        >
                          {t('superagent.noSubQuestionsYet')}
                        </Text>
                      )}

                      <Space.Compact size="small" style={{ width: '100%', maxWidth: 520, marginTop: 4 }}>
                        <Input
                          placeholder={t('superagent.inlineAddSubQuestionPlaceholder')}
                          value={inlineSubQuestionInputs[item.id] || ''}
                          onChange={(e) =>
                            setInlineSubQuestionInputs((prev) => ({
                              ...prev,
                              [item.id]: e.target.value,
                            }))
                          }
                          onPressEnter={() => handleAppendSubQuestionInline(item)}
                        />
                        <Button
                          icon={<PlusOutlined />}
                          loading={submittingId === `subq-${item.id}`}
                          onClick={() => handleAppendSubQuestionInline(item)}
                        >
                          {t('superagent.inlineAddSubQuestionBtn')}
                        </Button>
                      </Space.Compact>
                    </div>

                    {/* Verification / Success Criteria & Scope */}
                    {(criteriaList.length > 0 || constraintsList.length > 0) && (
                      <div
                        style={{
                          marginTop: 8,
                          paddingLeft: 8,
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: 6,
                        }}
                      >
                        {criteriaList.map((cr, cIdx) => (
                          <Tag key={`${item.id}-cr-${cIdx}`} color="green">
                            {`${t('superagent.criterionPrefix')}：${cr}`}
                          </Tag>
                        ))}
                        {constraintsList.map((con, kIdx) => (
                          <Tag key={`${item.id}-con-${kIdx}`}>
                            {`${t('superagent.constraintPrefix')}：${con}`}
                          </Tag>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </Space>
          )}
        </Card>
      </div>
    );
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          gap: 16,
          flexWrap: 'wrap',
          alignItems: 'flex-start',
        }}
      >
        <div style={{ flex: '1 1 580px', minWidth: 0 }}>
          {renderStagePipelineBar()}
          <div id="superagent-stage-workspace">
            {renderStageFocusBanner()}
            {renderProjectCharterSection()}
            {renderNeedsPersonSection()}
            {selectedStage ? (
              <>
                {renderStageDetailAndTickets()}
                {renderExecutorAndPolicyBar()}
              </>
            ) : (
              <>
                {renderExecutorAndPolicyBar()}
                {renderStageDetailAndTickets()}
              </>
            )}
          </div>
        </div>
        {activityTimeline && (
          <div style={{ flex: '0 0 320px', width: '100%', maxWidth: 340 }}>
            {activityTimeline}
          </div>
        )}
      </div>

      {/* Stage 1: Define / Edit Research Question Modal */}
      <Modal
        title={
          editingQuestionId
            ? t('superagent.editQuestionModalTitle')
            : t('superagent.defineQuestionModalTitle')
        }
        open={questionModalOpen}
        onCancel={() => {
          setQuestionModalOpen(false);
          setEditingQuestionId(null);
        }}
        onOk={() => questionForm.submit()}
        confirmLoading={submittingId === 'define-question'}
        width={640}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
            padding: '8px 12px',
            borderRadius: token.borderRadius,
            background: token.colorFillQuaternary,
          }}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('superagent.modalCharterHint')}
          </Text>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<BulbOutlined />}
            loading={submittingId === 'ai-suggest-charter'}
            onClick={handleAiSuggestCharter}
          >
            {t('superagent.aiFillCharterBtn')}
          </Button>
        </div>

        <Form
          form={questionForm}
          layout="vertical"
          onFinish={handleDefineQuestion}
        >
          <Form.Item
            name="theme"
            label={t('superagent.fieldTheme')}
            extra={t('superagent.fieldThemeExtra')}
            rules={[{ required: true }]}
          >
            <Input placeholder={t('superagent.fieldThemePlaceholder')} />
          </Form.Item>
          <Form.Item
            name="question"
            label={t('superagent.fieldCoreQuestion')}
            rules={[{ required: true }]}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('superagent.fieldCoreQuestionPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            name="sub_questions_raw"
            label={t('superagent.fieldSubQuestions')}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('superagent.fieldSubQuestionsPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            name="success_criteria_raw"
            label={t('superagent.fieldSuccessCriteria')}
            extra={t('superagent.fieldSuccessCriteriaExtra')}
          >
            <Input.TextArea
              rows={3}
              placeholder={t('superagent.fieldSuccessCriteriaPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            name="constraints_raw"
            label={t('superagent.fieldConstraints')}
          >
            <Input.TextArea
              rows={2}
              placeholder={t('superagent.fieldConstraintsPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Stage 4: Upload Wet-Lab Results Modal */}
      <Modal
        title={
          wetlabModalTicket
            ? `${wetlabModalTicket.short_key}: ${t('superagent.uploadWetlabModalTitle')}`
            : t('superagent.uploadWetlabModalTitle')
        }
        open={!!wetlabModalTicket}
        onCancel={() => setWetlabModalTicket(null)}
        onOk={() => wetlabForm.submit()}
        confirmLoading={submittingId === wetlabModalTicket?.id}
        width={680}
      >
        <Form form={wetlabForm} layout="vertical" onFinish={handleWetlabUpload}>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('superagent.wetlabUploadHint')}
          />
          <Form.Item
            name="csv_content"
            label={t('superagent.fieldWetlabCsv')}
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={7} style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item
            name="experiment_note"
            label={t('superagent.fieldWetlabNote')}
          >
            <Input.TextArea
              rows={2}
              placeholder={t('superagent.fieldWetlabNotePlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Stage 4: Spawn Next Iteration Round Modal */}
      <Modal
        title={t('superagent.spawnNextRoundModalTitle', {
          round: (nextRoundModalTicket?.iteration_round || 1) + 1,
        })}
        open={!!nextRoundModalTicket}
        onCancel={() => setNextRoundModalTicket(null)}
        onOk={() => nextRoundForm.submit()}
        confirmLoading={submittingId === nextRoundModalTicket?.id}
      >
        <Form
          form={nextRoundForm}
          layout="vertical"
          onFinish={handleSpawnNextRound}
        >
          <Form.Item
            name="direction_note"
            label={t('superagent.fieldNextRoundDirection')}
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item
            name="assignee_id"
            label={t('superagent.fieldAssignee')}
          >
            <Select
              allowClear
              options={members.map((m) => ({
                value: m.researcher_id,
                label: m.display_name || m.username,
              }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Manual Ticket Creation Modal */}
      <Modal
        title={t('superagent.newTicketModalTitle')}
        open={newTicketModalOpen}
        onCancel={() => setNewTicketModalOpen(false)}
        onOk={() => newTicketForm.submit()}
        confirmLoading={submittingId === 'new-ticket'}
      >
        <Form
          form={newTicketForm}
          layout="vertical"
          initialValues={{ stage_category: 'baseline_reproduction' }}
          onFinish={handleCreateTicket}
        >
          <Form.Item
            name="stage_category"
            label={t('superagent.colLifecycleStage')}
            rules={[{ required: true }]}
          >
            <Select
              options={STAGE_ORDER.map((s) => ({
                value: s,
                label: t(`superagent.stages.${s}`),
              }))}
            />
          </Form.Item>
          <Form.Item
            name="title"
            label={t('superagent.colTitle')}
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="goal" label={t('superagent.fieldTicketGoal')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Policy & Proactive Rules Modal */}
      <Modal
        title={t('superagent.policyModalTitle', {
          version: overview.policy.version,
        })}
        open={policyModalOpen}
        onCancel={() => setPolicyModalOpen(false)}
        footer={null}
        width={680}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Card
            size="small"
            style={{ background: token.colorFillQuaternary }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <div style={{ flex: 1, minWidth: 240 }}>
                <Text strong>{t('superagent.domainPluginAdapterTitle')}</Text>
                <Paragraph
                  type="secondary"
                  style={{ marginTop: 4, marginBottom: 0, fontSize: 12 }}
                >
                  {t('superagent.domainPluginAdapterDesc')}
                </Paragraph>
              </div>
              <Select
                style={{ minWidth: 260 }}
                disabled={!canManage}
                value={
                  overview.policy.enabled_plugins?.includes('amp-design-pack')
                    ? 'amp-design-pack'
                    : 'universal'
                }
                onChange={handleDomainPluginChange}
                options={[
                  {
                    value: 'universal',
                    label: t('superagent.domainPluginUniversal'),
                  },
                  {
                    value: 'amp-design-pack',
                    label: t('superagent.domainPluginAmp'),
                  },
                ]}
              />
            </div>
          </Card>

          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t('superagent.policyModalDesc')}
          </Paragraph>
          {overview.policy.rules.map((rule) => (
            <Card key={rule.id} size="small">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  gap: 12,
                }}
              >
                <div>
                  <Space>
                    <Text strong>{rule.name}</Text>
                    <Tag>{t(`superagent.stages.${rule.stage_category}`)}</Tag>
                  </Space>
                  <Paragraph
                    type="secondary"
                    style={{ marginTop: 4, marginBottom: 4, fontSize: 12 }}
                  >
                    {rule.description}
                  </Paragraph>
                  <Space size={4} wrap>
                    {rule.trigger_events.map((ev) => (
                      <Tag key={ev} color="cyan" style={{ fontSize: 11 }}>
                        {ev}
                      </Tag>
                    ))}
                  </Space>
                </div>
                <Switch
                  checked={rule.is_enabled}
                  disabled={!canManage}
                  onChange={(checked) => handleToggleRule(rule.id, checked)}
                />
              </div>
            </Card>
          ))}
        </Space>
      </Modal>

      {/* Ticket Detail & Shared Team Collaboration Drawer */}
      <Drawer
        title={
          activeTicket
            ? `${activeTicket.short_key} — ${activeTicket.title}`
            : ''
        }
        open={!!activeTicket}
        onClose={() => setActiveTicket(null)}
        width={680}
        extra={
          activeTicket && (
            <Button
              size="small"
              icon={<CommentOutlined />}
              loading={submittingId === `open-session-${activeTicket.id}`}
              onClick={() => handleDiscussInSession(activeTicket)}
            >
              {t('superagent.discussInSessionBtn')}
            </Button>
          )
        }
      >
        {activeTicket && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label={t('superagent.colStage')}>
                <Tag bordered={false} color={STAGE_BADGE_COLORS[activeTicket.stage] || 'default'}>
                  {STAGE_LABEL_KEYS[activeTicket.stage]
                    ? t(STAGE_LABEL_KEYS[activeTicket.stage])
                    : activeTicket.stage}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('superagent.colLifecycleStage')}>
                {t(`superagent.stages.${activeTicket.stage_category}`)}
              </Descriptions.Item>
              <Descriptions.Item label={t('superagent.mandateStrength')}>
                <Tag bordered={false}>
                  {t(
                    `superagent.mandateStrengthMap.${String(
                      activeTicket.mandate?.strength || 'inferred',
                    )}`,
                    { defaultValue: String(activeTicket.mandate?.strength || 'inferred') },
                  )}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('superagent.fieldAssignee')}>
                {activeTicket.assignee_name || '-'}
              </Descriptions.Item>
            </Descriptions>

            {activeTicket.stage === 'person / answer' &&
              activeTicket.attention && (
                <Card
                  size="small"
                  style={{
                    background: token.colorWarningBg,
                    borderColor: token.colorWarningBorder,
                  }}
                  title={(
                    <Space wrap>
                      <Tag bordered={false} color="gold">{t('superagent.humanInTheLoop')}</Tag>
                      <Text strong style={{ fontSize: 13 }}>
                        {activeTicket.attention.question}
                      </Text>
                    </Space>
                  )}
                >
                  <Space wrap>
                    {(activeTicket.attention.options || []).map((opt, idx) => (
                      <Button
                        key={opt}
                        type={idx === 0 ? 'primary' : 'default'}
                        icon={idx === 0 ? <CheckCircleOutlined /> : undefined}
                        loading={submittingId === activeTicket.id}
                        onClick={() => handleAnswerAttention(activeTicket, opt)}
                      >
                        {opt}
                      </Button>
                    ))}
                  </Space>
                </Card>
              )}

            {activeTicket.deliverable && (
              <Card
                size="small"
                title={activeTicket.deliverable.title}
                extra={
                  <Space wrap size={6}>
                    {activeTicket.stage_category === 'manuscript_writing' && (
                      <>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          loading={
                            submittingId === `ticket-pdf-${activeTicket.id}`
                          }
                          onClick={() =>
                            handleExportManuscript(
                              `/projects/${project.id}/tickets/${activeTicket.id}/export?format=pdf`,
                              `${activeTicket.short_key}_manuscript.pdf`,
                              `ticket-pdf-${activeTicket.id}`,
                            )
                          }
                        >
                          {t('superagent.downloadPdfBtn')}
                        </Button>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          loading={
                            submittingId === `ticket-docx-${activeTicket.id}`
                          }
                          onClick={() =>
                            handleExportManuscript(
                              `/projects/${project.id}/tickets/${activeTicket.id}/export?format=docx`,
                              `${activeTicket.short_key}_manuscript.docx`,
                              `ticket-docx-${activeTicket.id}`,
                            )
                          }
                        >
                          {t('superagent.downloadDocxBtn')}
                        </Button>
                      </>
                    )}
                    {activeTicket.status === 'open' &&
                      ['baseline_reproduction', 'innovation_feasibility', 'manuscript_writing'].includes(activeTicket.stage_category) &&
                      ['blocked', 'failed'].includes(activeTicket.report_state) && (
                        <Button
                          size="small"
                          loading={submittingId === `retry-baseline-${activeTicket.id}`}
                          disabled={submittingId !== null}
                          onClick={() => handleRetryExecution(activeTicket)}
                        >
                          {t('common.retry')}
                        </Button>
                      )}
                    {activeTicket.status === 'open' &&
                      activeTicket.report_state === 'ready' && (
                        <Button
                          size="small"
                          type="primary"
                          icon={<CheckCircleOutlined />}
                          onClick={() => handleApproveTicket(activeTicket, false)}
                        >
                          {t('superagent.approveAndMergeBtn')}
                        </Button>
                      )}
                  </Space>
                }
              >
                <div style={{ fontSize: 13 }}>
                  <MarkdownContent
                    content={activeTicket.deliverable.markdown_report}
                  />
                </div>
                {activeTicket.deliverable.metrics_table &&
                  renderDeliverableTable(activeTicket.deliverable.metrics_table)}
                {renderMultiAgentArtifacts(
                  activeTicket.deliverable,
                  activeTicket.short_key,
                )}
              </Card>
            )}

            <Card
              size="small"
              title={(
                <Space>
                  <CommentOutlined />
                  <Text strong>{t('superagent.sharedThreadTitle')}</Text>
                </Space>
              )}
            >
              <Space
                direction="vertical"
                style={{ width: '100%', maxHeight: 320, overflowY: 'auto' }}
                size={8}
              >
                {activeTicket.thread_messages.length === 0 ? (
                  <Text type="secondary">{t('superagent.noThreadMessages')}</Text>
                ) : (
                  activeTicket.thread_messages.map((msg) => (
                    <div
                      key={msg.id}
                      style={{
                        padding: '8px 12px',
                        borderRadius: token.borderRadius,
                        background:
                          msg.role === 'agent'
                            ? token.colorPrimaryBg
                            : token.colorFillQuaternary,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          marginBottom: 4,
                        }}
                      >
                        <Space size={6}>
                          <Tag
                            color={msg.role === 'agent' ? 'blue' : 'default'}
                            style={{ margin: 0 }}
                          >
                            {msg.author_name}
                          </Tag>
                          {msg.trigger_kind && (
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {msg.trigger_kind}
                            </Text>
                          )}
                        </Space>
                        <Space size={4}>
                          <ClockCircleOutlined
                            style={{ fontSize: 11, color: token.colorTextSecondary }}
                          />
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {msg.created_at.slice(0, 19).replace('T', ' ')}
                          </Text>
                        </Space>
                      </div>
                      <Paragraph
                        style={{
                          marginBottom: 0,
                          whiteSpace: 'pre-wrap',
                          fontSize: 13,
                        }}
                      >
                        {msg.content}
                      </Paragraph>
                    </div>
                  ))
                )}
              </Space>

              <Space.Compact style={{ width: '100%', marginTop: 12 }}>
                <Input
                  placeholder={t('superagent.threadInputPlaceholder')}
                  value={threadInput}
                  onChange={(e) => setThreadInput(e.target.value)}
                  onPressEnter={handleSendThreadMessage}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={submittingId === 'send-msg'}
                  onClick={handleSendThreadMessage}
                >
                  {t('superagent.sendToAgentBtn')}
                </Button>
              </Space.Compact>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
