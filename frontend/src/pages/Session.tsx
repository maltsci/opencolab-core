import {
  BookOutlined,
  CommentOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EllipsisOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  FileSearchOutlined,
  FolderOutlined,
  LinkOutlined,
  LoadingOutlined,
  RedoOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  ShareAltOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import { Breadcrumb, Button, Card, Checkbox, Dropdown, Empty, Form, Input, Layout, List, Modal, Popover, Select, Space, Spin, Tabs, Tag, Tooltip, Upload, message, notification, theme } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { ProcessingStatusTag } from '../components/library/AssetTags';
import PdfPreviewModal from '../components/library/PdfPreviewModal';
import SourceThumbnail from '../components/library/SourceThumbnail';
import { formatDateTime } from '../components/library/library-utils';
import ChatContainer from '../components/ui/ChatContainer';
import ChatInput from '../components/ui/ChatInput';
import ChatMessage, { MarkdownContent, type ChatMessageAction } from '../components/ui/ChatMessage';
import EmptyState from '../components/ui/EmptyState';
import { ResearchObjectDetails } from '../components/research/ResearchObjectDetails';
import { ResearchObjectDirectionSuggestion } from '../components/research/ResearchObjectDirectionSuggestion';
import { getStructuredResearchPreview } from '../components/research/research-object-content';
import type {
  ResearchRelationSubmitPayload,
  SessionResearchObject,
  SessionResearchObjectRelation,
} from '../components/research/types';
import { isAcceptedUploadFile, useFileDrop } from '../hooks/use-file-drop';
import { type CitationItem, type ResearchTraceMeta, useWebSocket } from '../hooks/useWebSocket';
import apiClient from '../services/api-client';
import {
  BUILT_IN_AGENTS,
  type AgentRunResponse,
  type AgentRunSaveMemoryRequest,
  type AgentRunSaveMemoryResponse,
  type BuiltInAgentName,
} from '../types/agent';
import { getTaskRuntimeKind, type TaskDefinition } from '../types/task';
import type { StepRunResponse, WorkflowRunCreateRequest, WorkflowRunResponse } from '../types/workflow';
import type { DuplicateUploadInfo } from '../types/upload';
import { getDuplicateUploadInfo, showDuplicateUploadModal } from '../utils/duplicate-upload';

const { Sider, Content } = Layout;
const { TextArea } = Input;
const PROJECT_QA_TASK_ID = 'project-qa';

const composeSessionRecommendedTasks = (tasks: TaskDefinition[]) => {
  // Defensive filter: never offer a disabled task, even if an API path
  // or cached state lets one through.
  const enabled = tasks.filter((task) => task.is_enabled);
  const projectQa = enabled.find((task) => task.id === PROJECT_QA_TASK_ID);
  if (!projectQa) return enabled;
  return [projectQa, ...enabled.filter((task) => task.id !== PROJECT_QA_TASK_ID)];
};

interface SourceMemberItem {
  id: string;
  child_id: string;
  child: { id: string; name: string; type: string } | null;
}

function GroupMemberPreview({ groupId }: { groupId: string }) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [memberNames, setMemberNames] = useState<string[] | null>(null);

  useEffect(() => {
    apiClient.get(`/sources/${groupId}/members`).then((r) => {
      setMemberNames(r.data.map((m: SourceMemberItem) => m.child?.name || m.child_id));
    });
  }, [groupId]);

  if (memberNames === null) {
    return <Spin size="small" />;
  }
  if (memberNames.length === 0) {
    return <span style={{ color: token.colorTextSecondary }}>{t('group.emptyGroup')}</span>;
  }
  return (
    <List
      size="small"
      dataSource={memberNames}
      renderItem={(name) => (
        <List.Item style={{ padding: '4px 0' }}>
          <FilePdfOutlined style={{ marginRight: 6, color: token.colorError }} />
          {name}
        </List.Item>
      )}
      style={{ maxHeight: 300, overflow: 'auto' }}
    />
  );
}

interface Message {
  id: string;
  role: string;
  content: string;
  created_at: string;
  agentRun?: AgentRunResponse;
}

interface MessageApiResponse {
  id: string;
  role: string;
  content: string;
  created_at: string;
  agent_run?: AgentRunResponse | null;
}

const TERMINAL_STATES = new Set(['ready', 'failed']);

function isSourceSelectable(source: Source): boolean {
  return !source.processing_state || source.processing_state === 'ready';
}

interface ShareInfo {
  shared_by: string | null;
  shared_by_name: string | null;
  scope: string;
  project_id: string | null;
  permission: string;
  shared_at: string;
}

interface Source {
  id: string;
  name: string;
  type: string;
  processing_state?: string;
  progress?: number;
  error_message?: string | null;
  owner_id?: string | null;
  owner_name?: string | null;
  share?: ShareInfo | null;
  is_shared?: boolean;
  can_edit?: boolean;
  duplicate_info?: DuplicateUploadInfo | null;
}

interface AvailableSource {
  category: 'project' | 'lab_public' | 'my_materials';
  source: Source;
}

interface SessionInfo {
  id: string;
  title: string | null;
  project_id: string | null;
  task_id?: string | null;
}

interface ProjectInfo {
  id: string;
  name: string;
}

interface CitationCardItem extends CitationItem {
  sourceName: string;
}

interface TraceResponse {
  id: string;
  message_id?: string | null;
  workflow_run_id?: string | null;
  inputs: {
    query?: string;
    source_ids?: string[];
  };
  retrieval: Array<Record<string, unknown>>;
  citations: CitationItem[];
  summary_steps: string[];
}

function getRequiredInputKeys(inputSchema: Record<string, unknown>): string[] {
  const required = inputSchema.required;
  return Array.isArray(required)
    ? required.filter((item): item is string => typeof item === 'string')
    : [];
}

function getSchemaPropertyKeys(inputSchema: Record<string, unknown>): string[] {
  const properties = inputSchema.properties;
  if (!properties || typeof properties !== 'object' || Array.isArray(properties)) {
    return [];
  }
  return Object.keys(properties);
}

function buildTaskQuery(task: TaskDefinition, requestText: string): string {
  const hypothesisGuardrails = task.id === 'hypothesis-generator'
    ? [
        '',
        'Hypothesis generation guardrails:',
        '- Separate observed evidence from testable prediction.',
        '- Do not infer statistical significance from repeated experiments unless the retrieved content explicitly reports statistical tests, p-values, confidence intervals, or effect sizes.',
        '- Do not infer antibody validation, specificity, detection limits, or endogenous detection from “antibody generation” alone.',
        '- If induction stimulus, controls, dosage, timepoint, or assay conditions are missing, state them as missing variables to be filled before testing.',
        '- Phrase unsupported parts as pending verification, not as established findings.',
      ].join('\n')
    : '';
  return [
    `Task: ${task.name}`,
    task.description ? `Task description: ${task.description}` : '',
    `User request: ${requestText}`,
    hypothesisGuardrails,
  ].filter(Boolean).join('\n');
}

function buildSessionWorkflowInputPayload(
  task: TaskDefinition,
  requestText: string,
  locale: string,
  sourceIds: string[],
): Record<string, unknown> {
  const inputSchema = task.input_schema;
  const requiredKeys = getRequiredInputKeys(inputSchema);
  const propertyKeys = getSchemaPropertyKeys(inputSchema);
  const payload: Record<string, unknown> = { locale };
  const textKeys = ['query', 'prompt', 'review_comments', 'question'];
  const candidateKeys = requiredKeys.length > 0 ? requiredKeys : propertyKeys;
  const taskQuery = buildTaskQuery(task, requestText);

  candidateKeys.forEach((key) => {
    if (key === 'source_ids') {
      payload[key] = sourceIds;
      return;
    }

    if (key === 'locale') {
      payload[key] = locale;
      return;
    }

    if (key === 'query') {
      payload[key] = taskQuery;
      return;
    }

    if (textKeys.includes(key)) {
      payload[key] = requestText;
      return;
    }

    payload[key] = requestText;
  });

  if (!('source_ids' in payload)) {
    payload.source_ids = sourceIds;
  }

  if (Object.keys(payload).length === 2 && payload.locale && Array.isArray(payload.source_ids)) {
    payload.prompt = requestText;
  }

  return payload;
}

type MemoryTabKey = 'timeline' | 'graph' | 'objects';

interface WorkflowStepDisplayItem {
  key: string;
  name: string;
  status: string;
  summary: string;
  runtime?: string;
}

interface WorkflowCardState {
  status: string;
  stepCount: number;
  steps: WorkflowStepDisplayItem[];
  source: 'workflow' | 'legacy';
  outputPayload?: Record<string, unknown>;
}

type WorkflowRequestState = 'loading' | 'loaded';

interface NormalizedAgentOutput {
  overview: string;
  keyPoints: string[];
  contradictions: string[];
  gaps: string[];
  actionItems: string[];
  responseOutline: string[];
  validationNotes: string[];
}

interface NormalizedWorkflowOutput {
  overview: string;
  summary: string;
  draft: string;
  keyPoints: string[];
  contradictions: string[];
  gaps: string[];
  validationNotes: string[];
  rawSections: Array<{ key: string; value: string }>;
}

function truncateLabel(value: string, maxLength = 72): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength).trimEnd()}...`;
}

function looksLikeUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function unwrapJsonCodeFence(value: string): string {
  const trimmed = value.trim();
  const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match ? match[1].trim() : trimmed;
}

function looksLikeJsonText(value: string): boolean {
  const trimmed = unwrapJsonCodeFence(value);
  return (
    (trimmed.startsWith('{') && trimmed.endsWith('}'))
    || (trimmed.startsWith('[') && trimmed.endsWith(']'))
  );
}

function parseJsonObjectFromText(value: string): Record<string, unknown> | null {
  const trimmed = unwrapJsonCodeFence(value);
  if (!looksLikeJsonText(trimmed)) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function recoverPartialJsonObjectFromText(value: string): Record<string, unknown> | null {
  const trimmed = unwrapJsonCodeFence(value);
  if (!trimmed.startsWith('{')) {
    return null;
  }

  const recovered: Record<string, unknown> = {};
  const readString = (key: string) => {
    const match = trimmed.match(new RegExp(`"${key}"\\s*:\\s*"((?:\\\\.|[^"\\\\])*)"`));
    if (!match) return '';
    try {
      return JSON.parse(`"${match[1]}"`) as string;
    } catch {
      return '';
    }
  };
  const readStringArray = (key: string) => {
    const fieldMatch = trimmed.match(new RegExp(`"${key}"\\s*:\\s*\\[([\\s\\S]*)`));
    if (!fieldMatch) return [];
    const arrayText = fieldMatch[1].split(']')[0];
    return Array.from(arrayText.matchAll(/"((?:\\.|[^"\\])*)"/g))
      .map((match) => {
        try {
          return JSON.parse(`"${match[1]}"`) as string;
        } catch {
          return '';
        }
      })
      .filter(Boolean);
  };

  const overview = readString('overview');
  if (overview) recovered.overview = overview;

  for (const key of ['key_points', 'contradictions', 'gaps']) {
    const items = readStringArray(key);
    if (items.length > 0) recovered[key] = items;
  }

  return Object.keys(recovered).length > 0 ? recovered : null;
}

function toTrimmedString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function readValidationNotes(value: unknown): string[] {
  if (!value || typeof value !== 'object') {
    return [];
  }

  return toStringArray((value as { notes?: unknown }).notes);
}

function withoutEmptyStructuredFields(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(value).filter(([, entryValue]) => {
      if (typeof entryValue === 'string') {
        return entryValue.trim().length > 0;
      }
      if (Array.isArray(entryValue)) {
        return entryValue.length > 0;
      }
      return entryValue !== undefined && entryValue !== null;
    }),
  );
}

function normalizeAgentOutput(run: AgentRunResponse, fallbackContent: string): NormalizedAgentOutput {
  const baseOutput =
    run.output && typeof run.output === 'object' && !Array.isArray(run.output)
      ? { ...run.output }
      : {};
  const fallbackObject = parseJsonObjectFromText(fallbackContent) || recoverPartialJsonObjectFromText(fallbackContent);
  const rawSynthesisObject =
    typeof baseOutput.raw_synthesis === 'string'
      ? parseJsonObjectFromText(baseOutput.raw_synthesis)
        || recoverPartialJsonObjectFromText(baseOutput.raw_synthesis)
      : null;
  const overviewCandidate =
    run.agent_name === 'literature_synthesizer'
      ? baseOutput.overview
      : baseOutput.summary;

  const parsedOverviewObject =
    typeof overviewCandidate === 'string'
      ? parseJsonObjectFromText(overviewCandidate)
        || recoverPartialJsonObjectFromText(overviewCandidate)
      : null;

  const merged = {
    ...(fallbackObject || {}),
    ...(rawSynthesisObject || {}),
    ...withoutEmptyStructuredFields(baseOutput),
    ...(parsedOverviewObject || {}),
  } as Record<string, unknown>;

  const overview = toTrimmedString(
    run.agent_name === 'literature_synthesizer'
      ? merged.overview
      : merged.summary,
  );

  return {
    overview: overview || (!fallbackObject && !looksLikeJsonText(fallbackContent) ? fallbackContent.trim() : ''),
    keyPoints: toStringArray(merged.key_points),
    contradictions: toStringArray(merged.contradictions),
    gaps: toStringArray(merged.gaps),
    actionItems: toStringArray(merged.action_items),
    responseOutline: toStringArray(merged.response_outline),
    validationNotes: readValidationNotes(merged.validation),
  };
}

function stringifyWorkflowValue(value: unknown): string {
  if (typeof value === 'string') {
    return value.trim();
  }
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function normalizeWorkflowOutput(
  outputPayload: Record<string, unknown> | undefined,
  fallbackContent: string,
): NormalizedWorkflowOutput {
  const fallbackObject = parseJsonObjectFromText(fallbackContent) || recoverPartialJsonObjectFromText(fallbackContent);
  const rawPayload =
    outputPayload && typeof outputPayload === 'object' && !Array.isArray(outputPayload)
      ? outputPayload
      : {};
  const rawSynthesisObject =
    typeof rawPayload.raw_synthesis === 'string'
      ? parseJsonObjectFromText(rawPayload.raw_synthesis)
        || recoverPartialJsonObjectFromText(rawPayload.raw_synthesis)
      : null;
  const parsedOverviewObject =
    typeof rawPayload.overview === 'string'
      ? parseJsonObjectFromText(rawPayload.overview)
        || recoverPartialJsonObjectFromText(rawPayload.overview)
      : null;
  const parsedSummaryObject =
    typeof rawPayload.summary === 'string'
      ? parseJsonObjectFromText(rawPayload.summary)
        || recoverPartialJsonObjectFromText(rawPayload.summary)
      : null;
  const merged = {
    ...(fallbackObject || {}),
    ...withoutEmptyStructuredFields(rawPayload),
    ...(rawSynthesisObject || {}),
    ...(parsedOverviewObject || {}),
    ...(parsedSummaryObject || {}),
  } as Record<string, unknown>;

  const preferredKeys = new Set([
    'overview',
    'summary',
    'draft',
    'key_points',
    'contradictions',
    'gaps',
    'validation',
    'raw_synthesis',
    'citations',
    'agent',
  ]);
  const internalKeys = new Set([
    'source_ids',
    'locale',
    'query',
    'prompt',
    'question',
    'review_comments',
    'input',
    'inputs',
  ]);
  const rawSections = Object.entries(merged)
    .filter(([key, value]) => !preferredKeys.has(key) && !internalKeys.has(key) && stringifyWorkflowValue(value))
    .slice(0, 4)
    .map(([key, value]) => ({ key, value: stringifyWorkflowValue(value) }));

  return {
    overview: toTrimmedString(merged.overview),
    summary: toTrimmedString(merged.summary),
    draft: toTrimmedString(merged.draft),
    keyPoints: toStringArray(merged.key_points),
    contradictions: toStringArray(merged.contradictions),
    gaps: toStringArray(merged.gaps),
    validationNotes: readValidationNotes(merged.validation),
    rawSections,
  };
}

function getAgentDefinition(agentName: BuiltInAgentName) {
  return BUILT_IN_AGENTS.find((agent) => agent.name === agentName) || BUILT_IN_AGENTS[0];
}

function findRegeneratePrompt(messages: Message[], messageId: string): string | null {
  const targetIndex = messages.findIndex((message) => message.id === messageId);
  if (targetIndex <= 0) return null;

  for (let index = targetIndex - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') {
      return messages[index].content;
    }
  }

  return null;
}

function getAgentSummary(run: AgentRunResponse): string {
  const output = run.output || {};

  if (run.agent_name === 'literature_synthesizer') {
    const overview = output.overview;
    if (typeof overview === 'string' && overview.trim()) return overview.trim();
    const rawSynthesis = output.raw_synthesis;
    if (typeof rawSynthesis === 'string' && rawSynthesis.trim()) {
      const parsedRaw = parseJsonObjectFromText(rawSynthesis);
      const parsedOverview = parsedRaw?.overview;
      if (typeof parsedOverview === 'string' && parsedOverview.trim()) {
        return parsedOverview.trim();
      }
    }
  }

  if (run.agent_name === 'reviewer_assistant') {
    const summary = output.summary;
    if (typeof summary === 'string' && summary.trim()) return summary.trim();
    const rawSynthesis = output.raw_synthesis;
    if (typeof rawSynthesis === 'string' && rawSynthesis.trim()) {
      const parsedRaw = parseJsonObjectFromText(rawSynthesis);
      const parsedSummary = parsedRaw?.summary;
      if (typeof parsedSummary === 'string' && parsedSummary.trim()) {
        return parsedSummary.trim();
      }
    }
  }

  const errorMessage = run.error_message;
  if (typeof errorMessage === 'string' && errorMessage.trim()) return errorMessage.trim();

  return '';
}

function formatAgentOutputForMemory(
  run: AgentRunResponse,
  fallbackContent: string,
  t: (key: string) => string,
): { title: string; content: string } {
  const normalized = normalizeAgentOutput(run, fallbackContent);
  const sections: string[] = [];

  if (normalized.overview) {
    sections.push(`${t('agent.overview')}\n${normalized.overview}`);
  }
  if (normalized.keyPoints.length > 0) {
    sections.push(`${t('agent.keyPoints')}\n${normalized.keyPoints.map((item) => `- ${item}`).join('\n')}`);
  }
  if (normalized.contradictions.length > 0) {
    sections.push(`${t('agent.contradictions')}\n${normalized.contradictions.map((item) => `- ${item}`).join('\n')}`);
  }
  if (normalized.gaps.length > 0) {
    sections.push(`${t('agent.gaps')}\n${normalized.gaps.map((item) => `- ${item}`).join('\n')}`);
  }
  if (normalized.actionItems.length > 0) {
    sections.push(`${t('agent.actionItems')}\n${normalized.actionItems.map((item) => `- ${item}`).join('\n')}`);
  }
  if (normalized.responseOutline.length > 0) {
    sections.push(`${t('agent.responseOutline')}\n${normalized.responseOutline.map((item) => `- ${item}`).join('\n')}`);
  }
  if (normalized.validationNotes.length > 0) {
    sections.push(`${t('agent.validationNotes')}\n${normalized.validationNotes.map((item) => `- ${item}`).join('\n')}`);
  }

  const content = sections.join('\n\n').trim();
  const summary = getAgentSummary(run).trim();
  const compactTitle = truncateLabel(summary, 96);

  return {
    title: compactTitle || t('researchObject.defaultHypothesisTitle'),
    content: content || fallbackContent.trim(),
  };
}

function normalizeResearchObjectTitle(
  title: string | null | undefined,
  type: 'hypothesis' | 'discussion',
  t: (key: string) => string,
): string {
  const trimmed = title?.trim() || '';
  if (!trimmed) return t('timeline.untitled');

  const englishDefaults = {
    hypothesis: 'Saved hypothesis',
    discussion: 'Saved discussion',
  };
  const localizedDefaults = {
    hypothesis: t('researchObject.defaultHypothesisTitle'),
    discussion: t('researchObject.defaultDiscussionTitle'),
  };

  if (trimmed === englishDefaults[type] || trimmed === localizedDefaults[type]) {
    return localizedDefaults[type];
  }

  return trimmed;
}

function buildResearchObjectOptionLabel(
  item: SessionResearchObject,
  t: (key: string) => string,
): string {
  const normalizedType: 'hypothesis' | 'discussion' = item.type === 'hypothesis'
    ? 'hypothesis'
    : 'discussion';
  const typeLabel = normalizedType === 'hypothesis'
    ? t('researchObject.typeHypothesis')
    : t('researchObject.typeDiscussion');
  const title = normalizeResearchObjectTitle(item.title, normalizedType, t);
  return `[${typeLabel}] ${truncateLabel(title)}`;
}

function buildResearchObjectPreview(item: SessionResearchObject, t: (key: string) => string): string {
  const preview = getStructuredResearchPreview(item.content);
  return truncateLabel(preview || t('timeline.emptyContent'), 180);
}

function normalizeLoadedMessage(item: MessageApiResponse): Message {
  return {
    id: item.id,
    role: item.role,
    content: item.content,
    created_at: item.created_at,
    agentRun: item.agent_run || undefined,
  };
}

function compareMessagesByTimeline(left: Message, right: Message): number {
  const leftTime = new Date(left.created_at).getTime();
  const rightTime = new Date(right.created_at).getTime();

  if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime;
  }

  if (left.role !== right.role) {
    if (left.role === 'user') return -1;
    if (right.role === 'user') return 1;
  }

  return left.id.localeCompare(right.id);
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (item === null || item === undefined) return '';
      return String(item).trim();
    })
    .filter(Boolean);
}

function normalizeWorkflowStepName(
  step: StepRunResponse,
  t: (key: string) => string,
): string {
  const rawName = typeof step.output_payload.name === 'string' ? step.output_payload.name.trim() : '';
  const candidateName = rawName || step.step_id;
  if (!candidateName) {
    return step.step_id;
  }

  const localizedStepName = t(`workflow.stepName.${candidateName}`);
  return localizedStepName === `workflow.stepName.${candidateName}`
    ? candidateName
    : localizedStepName;
}

function normalizeWorkflowStepSummary(
  step: StepRunResponse,
): string {
  const outputSummary = typeof step.output_payload.summary === 'string' ? step.output_payload.summary.trim() : '';
  return outputSummary;
}

function buildLegacyWorkflowCard(
  run: AgentRunResponse,
): WorkflowCardState | null {
  if (!run.steps.length) return null;

  return {
    status: run.status,
    stepCount: run.steps.length,
    source: 'legacy',
    outputPayload: run.output && typeof run.output === 'object' && !Array.isArray(run.output)
      ? run.output as Record<string, unknown>
      : undefined,
    steps: run.steps.map((step, index) => ({
      key: `${run.id}-legacy-${index}`,
      name: step.name.trim() || `step-${index + 1}`,
      status: step.status,
      summary: step.summary.trim(),
    })),
  };
}

async function loadWorkflowCard(
  runId: string,
  t: (key: string) => string,
): Promise<WorkflowCardState> {
  const [runResponse, stepsResponse] = await Promise.all([
    apiClient.get<WorkflowRunResponse>(`/workflow-runs/${runId}`),
    apiClient.get<StepRunResponse[]>(`/workflow-runs/${runId}/steps`),
  ]);

  return {
    status: runResponse.data.status,
    stepCount: stepsResponse.data.length,
    source: 'workflow',
    outputPayload: runResponse.data.output_payload,
    steps: stepsResponse.data.map((step) => ({
      key: step.id,
      name: normalizeWorkflowStepName(step, t),
      status: step.status,
      summary: normalizeWorkflowStepSummary(step),
      runtime: typeof step.output_payload.runtime === 'string' ? step.output_payload.runtime : undefined,
    })),
  };
}

function mergeWorkflowCardState(
  current: WorkflowCardState | undefined,
  incoming: WorkflowCardState,
): WorkflowCardState {
  if (!current) {
    return incoming;
  }

  const preferIncomingSteps =
    incoming.steps.length > current.steps.length
    || (incoming.steps.length === current.steps.length && incoming.source === 'workflow');
  const primarySteps = preferIncomingSteps ? incoming.steps : current.steps;
  const secondarySteps = preferIncomingSteps ? current.steps : incoming.steps;

  return {
    status: incoming.status || current.status,
    stepCount: Math.max(
      current.stepCount,
      incoming.stepCount,
      current.steps.length,
      incoming.steps.length,
    ),
    source: preferIncomingSteps ? incoming.source : current.source,
    outputPayload: incoming.outputPayload || current.outputPayload,
    steps: primarySteps.map((step, index) => {
      const fallbackStep = secondarySteps[index];
      return {
        key: step.key || fallbackStep?.key || `workflow-step-${index + 1}`,
        name: step.name || fallbackStep?.name || `step-${index + 1}`,
        status: step.status || fallbackStep?.status || incoming.status || current.status,
        summary: step.summary || fallbackStep?.summary || '',
        runtime: step.runtime || fallbackStep?.runtime,
      };
    }),
  };
}

function getWorkflowStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'running':
      return 'processing';
    case 'waiting_for_checkpoint':
      return 'warning';
    default:
      return 'default';
  }
}

function getWorkflowStatusLabel(
  status: string,
  t: (key: string) => string,
): string {
  return t(`workflow.status.${status}`);
}

function shouldShowWorkflowExpand(workflowCard: WorkflowCardState): boolean {
  return workflowCard.steps.length > 3 || workflowCard.steps.some((step) => step.summary.length > 140);
}

function summarizeRunProgressEvent(event: unknown): string | null {
  if (!event || typeof event !== 'object') return null;
  const record = event as Record<string, unknown>;
  const item = record.item as Record<string, unknown> | undefined;
  const candidate = item?.text ?? item?.content ?? record.message ?? record.content ?? record.text ?? record.last_message;
  if (typeof candidate !== 'string' || !candidate.trim()) return null;
  const text = candidate.trim().replace(/\s+/g, ' ');
  return text.length > 160 ? `${text.slice(0, 160)}...` : text;
}

function formatTokenCount(value: number): string {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return `${value}`;
}

export default function SessionPage() {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [input, setInput] = useState('');
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const selectableSourceIds = sources.filter(isSourceSelectable).map((source) => source.id);
  const selectedContextSourceIds = selectableSourceIds.filter((id) => selectedSourceIds.includes(id));
  const allSourcesSelected = selectableSourceIds.length > 0
    && selectedContextSourceIds.length === selectableSourceIds.length;
  const [sourcePanelCollapsed, setSourcePanelCollapsed] = useState(false);
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [projectInfo, setProjectInfo] = useState<ProjectInfo | null>(null);
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [availableSources, setAvailableSources] = useState<AvailableSource[]>([]);
  const [pdfViewerSource, setPdfViewerSource] = useState<Source | null>(null);
  const [uploading, setUploading] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [renameTarget, setRenameTarget] = useState<Source | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [traceByMessageId, setTraceByMessageId] = useState<Record<string, ResearchTraceMeta>>({});
  const [traceSourceNameById, setTraceSourceNameById] = useState<Record<string, string>>({});
  const [selectedTraceMessageId, setSelectedTraceMessageId] = useState<string | null>(null);
  const [researchObjects, setResearchObjects] = useState<SessionResearchObject[]>([]);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [memoryActiveTab, setMemoryActiveTab] = useState<MemoryTabKey>('timeline');
  const [activeResearchObjectId, setActiveResearchObjectId] = useState<string | null>(null);
  const [relationsByObjectId, setRelationsByObjectId] = useState<Record<string, SessionResearchObjectRelation[]>>({});
  const [editingResearchObject, setEditingResearchObject] = useState<SessionResearchObject | null>(null);
  const [researchObjectTitleDraft, setResearchObjectTitleDraft] = useState('');
  const [researchObjectContentDraft, setResearchObjectContentDraft] = useState('');
  const [saveMemoryModalOpen, setSaveMemoryModalOpen] = useState(false);
  const [selectedAgentMessage, setSelectedAgentMessage] = useState<Message | null>(null);
  const [saveMemoryType, setSaveMemoryType] = useState<'hypothesis' | 'discussion'>('hypothesis');
  const [saveMemoryTitleDraft, setSaveMemoryTitleDraft] = useState('');
  const [saveMemoryContentDraft, setSaveMemoryContentDraft] = useState('');
  const [saveMemoryRelationEnabled, setSaveMemoryRelationEnabled] = useState(false);
  const [saveMemoryRelationType, setSaveMemoryRelationType] = useState<'supports' | 'contradicts'>('supports');
  const [saveMemoryRelationTargetId, setSaveMemoryRelationTargetId] = useState<string | null>(null);
  const [saveMemoryRelationNote, setSaveMemoryRelationNote] = useState('');
  const [isSavingAgentMemory, setIsSavingAgentMemory] = useState(false);
  const [workflowByRunId, setWorkflowByRunId] = useState<Record<string, WorkflowCardState>>({});
  const [expandedWorkflowRunIds, setExpandedWorkflowRunIds] = useState<Record<string, boolean>>({});
  const [sessionRecommendedTasks, setSessionRecommendedTasks] = useState<TaskDefinition[]>([]);
  const [sessionTasksLoading, setSessionTasksLoading] = useState(false);
  const [selectedSessionTask, setSelectedSessionTask] = useState<TaskDefinition | null>(null);
  const [sessionRuns, setSessionRuns] = useState<Array<{ task_id?: string | null; status?: string | null }>>([]);
  const [isStartingSessionTask, setIsStartingSessionTask] = useState(false);
  const [runProgressActive, setRunProgressActive] = useState(false);
  const [runProgressLines, setRunProgressLines] = useState<string[]>([]);
  const [runUsageByMessageId, setRunUsageByMessageId] = useState<Record<string, Record<string, number>>>({});
  const [regeneratingTaskMessageId, setRegeneratingTaskMessageId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const handledCompletionRef = useRef(0);
  const replacingMessageIdRef = useRef<string | null>(null);
  const replacingMessageSnapshotRef = useRef<Message | null>(null);
  const tracePanelRef = useRef<HTMLDivElement>(null);
  const requestedWorkflowRunIdsRef = useRef<Record<string, WorkflowRequestState>>({});
  const sortedMessages = useMemo(
    () => [...messages].sort(compareMessagesByTimeline),
    [messages],
  );
  // Stable callback so memoized ChatMessage/MarkdownContent instances are not
  // invalidated on every streamed token.
  const handleMessageSourceClick = useCallback(
    (sourceId: string, label?: string) => {
      setPdfViewerSource({
        id: sourceId,
        name: label || t('chat.viewSource'),
        type: 'pdf',
      });
    },
    [t],
  );
  const {
    isConnected,
    streamingContent,
    isStreaming,
    sendMessage,
    sessionTitle,
    latestTrace,
    streamError,
    completedAssistantMessage,
  } = useWebSocket(sessionId);

  useEffect(() => {
    if (!sessionId) return;
    setMessages([]);
    setSources([]);
    setSelectedSourceIds([]);
    setSessionInfo(null);
    setProjectInfo(null);
    setTraceByMessageId({});
    setTraceSourceNameById({});
    setSelectedTraceMessageId(null);
    setResearchObjects([]);
    setTimelineOpen(false);
    setMemoryActiveTab('timeline');
    setActiveResearchObjectId(null);
    setRelationsByObjectId({});
    setWorkflowByRunId({});
    setExpandedWorkflowRunIds({});
    setSelectedSessionTask(null);
    setSessionRuns([]);
    setIsStartingSessionTask(false);
    setRegeneratingTaskMessageId(null);
    requestedWorkflowRunIdsRef.current = {};
    setPageLoading(true);

    const loadSession = apiClient.get(`/sessions/${sessionId}`).then((r) => {
      setSessionInfo(r.data);
      return r.data as SessionInfo;
    });

    // Critical path: render the workspace as soon as these finish.
    Promise.all([
      loadSession,
      apiClient.get(`/sessions/${sessionId}/messages`).then((r) => {
        const loadedMessages = (r.data as MessageApiResponse[]).map(normalizeLoadedMessage);
        setMessages(loadedMessages);
      }),
      apiClient.get(`/sessions/${sessionId}/sources`).then((r) => {
        const loaded: Source[] = r.data;
        setSources(loaded);
        setSelectedSourceIds(loaded.filter(isSourceSelectable).map((source) => source.id));
      }),
    ])
      .catch(() => {
        message.error(t('session.loadFailed'));
      })
      .finally(() => setPageLoading(false));

    // Project info depends on session info but should not block the workspace.
    loadSession.then((sessionData) => {
      if (sessionData.project_id) {
        apiClient.get(`/projects/${sessionData.project_id}`).then((pr) => setProjectInfo(pr.data));
      }
    });

    // Background data for the memory panel; loaded after the workspace is interactive.
    apiClient.get(`/sessions/${sessionId}/trace`).then((r) => {
      const traces: TraceResponse[] = r.data;
      const nextTraceMap: Record<string, ResearchTraceMeta> = {};
      traces.forEach((trace) => {
        if (!trace.message_id) return;
        nextTraceMap[trace.message_id] = {
          traceId: trace.id,
          messageId: trace.message_id,
          workflowRunId: trace.workflow_run_id || null,
          inputs: trace.inputs || {},
          retrieval: Array.isArray(trace.retrieval) ? trace.retrieval : [],
          citations: trace.citations || [],
          summarySteps: trace.summary_steps || [],
        };
      });
      setTraceByMessageId(nextTraceMap);
    }).catch(() => {
      setTraceByMessageId({});
    });

    apiClient.get(`/sessions/${sessionId}/research-objects`).then((r) => {
      setResearchObjects(r.data);
    }).catch(() => {
      setResearchObjects([]);
    });

    // Track orchestration runs so the origin task is only pinned until it completes.
    apiClient.get(`/sessions/${sessionId}/orchestration-runs`).then((r) => {
      setSessionRuns(r.data as Array<{ task_id?: string | null; status?: string | null }>);
    }).catch(() => {
      setSessionRuns([]);
    });
  }, [sessionId]);

  useEffect(() => {
    const projectId = sessionInfo?.project_id;
    if (!projectId) {
      setSessionRecommendedTasks([]);
      return;
    }

    let cancelled = false;

    const fetchTasks = async (showLoading: boolean) => {
      if (showLoading) setSessionTasksLoading(true);
      let globalTasks: TaskDefinition[] = [];
      try {
        const globalResponse = await apiClient.get<TaskDefinition[]>('/tasks');
        globalTasks = globalResponse.data;
      } catch {
        if (!cancelled) {
          setSessionRecommendedTasks([]);
          setSessionTasksLoading(false);
        }
        return;
      }

      try {
        const projectResponse = await apiClient.get<TaskDefinition[]>('/tasks', {
          params: { project_id: projectId },
        });
        if (!cancelled) {
          const merged = new Map<string, TaskDefinition>();
          [...globalTasks, ...projectResponse.data].forEach((task) => merged.set(task.id, task));
          setSessionRecommendedTasks(composeSessionRecommendedTasks(Array.from(merged.values())));
        }
      } catch {
        if (!cancelled) {
          setSessionRecommendedTasks(composeSessionRecommendedTasks(globalTasks));
        }
      } finally {
        if (!cancelled) {
          setSessionTasksLoading(false);
        }
      }
    };

    void fetchTasks(true);

    // Refresh on window focus so tasks disabled in Admin (e.g. in another
    // tab) disappear without a full page reload, matching the home page.
    const handleWindowFocus = () => {
      void fetchTasks(false);
    };
    window.addEventListener('focus', handleWindowFocus);

    return () => {
      cancelled = true;
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, [sessionInfo?.project_id]);

  useEffect(() => {
    if (!sessionInfo?.task_id || sessionRecommendedTasks.length === 0) return;
    // Once the session's origin task has completed, follow-up messages go
    // through normal chat; the task is only re-pinned when it never ran.
    const originTaskCompleted = sessionRuns.some(
      (run) => run.task_id === sessionInfo.task_id && run.status === 'completed',
    );
    if (originTaskCompleted) {
      setSelectedSessionTask((prev) =>
        prev && prev.id === sessionInfo.task_id ? null : prev,
      );
      return;
    }
    const task = sessionRecommendedTasks.find((item) => item.id === sessionInfo.task_id);
    if (task) {
      setSelectedSessionTask(task);
    }
  }, [sessionInfo?.task_id, sessionRecommendedTasks, sessionRuns]);

  useEffect(() => {
    // Drop the pinned task if it was disabled or removed since selection.
    if (!selectedSessionTask || sessionRecommendedTasks.length === 0) return;
    const stillAvailable = sessionRecommendedTasks.some(
      (task) => task.id === selectedSessionTask.id,
    );
    if (!stillAvailable) {
      setSelectedSessionTask(null);
    }
  }, [selectedSessionTask, sessionRecommendedTasks]);

  useEffect(() => {
    if (sessionTitle && sessionInfo) {
      setSessionInfo((prev) => prev ? { ...prev, title: sessionTitle } : prev);
    }
  }, [sessionTitle]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const reloadMessagesAndTrace = async () => {
    if (!sessionId) return;
    const [messagesResponse, traceResponse, runsResponse] = await Promise.all([
      apiClient.get(`/sessions/${sessionId}/messages`),
      apiClient.get(`/sessions/${sessionId}/trace`),
      apiClient.get(`/sessions/${sessionId}/orchestration-runs`),
    ]);

    const loadedMessages = (messagesResponse.data as MessageApiResponse[]).map(normalizeLoadedMessage);
    setMessages(loadedMessages);

    const traces: TraceResponse[] = traceResponse.data;
    const nextTraceMap: Record<string, ResearchTraceMeta> = {};
    traces.forEach((trace) => {
      if (!trace.message_id) return;
      nextTraceMap[trace.message_id] = {
        traceId: trace.id,
        messageId: trace.message_id,
        workflowRunId: trace.workflow_run_id || null,
        inputs: trace.inputs || {},
        retrieval: Array.isArray(trace.retrieval) ? trace.retrieval : [],
        citations: trace.citations || [],
        summarySteps: trace.summary_steps || [],
      };
    });
    setTraceByMessageId(nextTraceMap);

    const nextUsageMap: Record<string, Record<string, number>> = {};
    (runsResponse.data as Array<{ final_message_id?: string | null; budget_usage?: Record<string, number> }>)
      .forEach((run) => {
        if (run.final_message_id && run.budget_usage && Object.keys(run.budget_usage).length > 0) {
          nextUsageMap[run.final_message_id] = run.budget_usage;
        }
      });
    setRunUsageByMessageId(nextUsageMap);
    setSessionRuns(runsResponse.data as Array<{ task_id?: string | null; status?: string | null }>);
  };

  const handleStartSelectedSessionTask = async (task: TaskDefinition, requestText: string) => {
    if (!sessionId) return;

    setIsStartingSessionTask(true);
    const optimisticUserMessage: Message = {
      id: `task-user-${Date.now()}`,
      role: 'user',
      content: requestText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMessage]);
    setInput('');

    try {
      await apiClient.post(`/sessions/${sessionId}/messages`, {
        content: requestText,
      });

      if (task.id === 'project-qa') {
        await apiClient.post(
          `/sessions/${sessionId}/orchestration-runs/project-qa`,
          {
            goal: requestText,
            source_ids: selectedContextSourceIds,
          },
          // Codex sandbox runs can take up to 30 minutes; wait past the backend timeout.
          { timeout: 1860000 },
        );
        await reloadMessagesAndTrace();
        setSelectedSessionTask(null);
        message.success(t('task.workspaceRunStarted'));
        return;
      }

      if (task.skill_pack_id) {
        setRunProgressActive(true);
        setRunProgressLines([]);
        const pollRunProgress = async () => {
          try {
            const { data } = await apiClient.get(
              `/sessions/${sessionId}/orchestration-runs/progress`,
            );
            // The endpoint returns the session's latest run; until the new
            // run is created and running, ignore events from previous runs.
            if (data?.status !== 'running') {
              return;
            }
            const events: unknown[] = Array.isArray(data?.events) ? data.events : [];
            const lines = events
              .map(summarizeRunProgressEvent)
              .filter((line): line is string => Boolean(line));
            setRunProgressLines(lines.slice(-6));
          } catch {
            // Transient poll failures are fine; the POST below is the source of truth.
          }
        };
        void pollRunProgress();
        const progressPoller = window.setInterval(() => {
          void pollRunProgress();
        }, 3000);
        try {
          await apiClient.post(
            `/sessions/${sessionId}/orchestration-runs/skill-pack`,
            {
              goal: requestText,
              task_id: task.id,
              source_ids: selectedContextSourceIds,
            },
            // Codex sandbox runs can take up to 30 minutes; wait past the backend timeout.
            { timeout: 1860000 },
          );
          await reloadMessagesAndTrace();
          setSelectedSessionTask(null);
          message.success(t('task.workspaceRunStarted'));
        } finally {
          window.clearInterval(progressPoller);
          setRunProgressActive(false);
          setRunProgressLines([]);
        }
        return;
      }

      const payload: WorkflowRunCreateRequest = {
        session_id: sessionId,
        input: buildSessionWorkflowInputPayload(
          task,
          requestText,
          i18n.language,
          selectedContextSourceIds,
        ),
      };

      const { data: createdRun } = await apiClient.post<WorkflowRunResponse>(
        `/workflows/${task.workflow_id}/run`,
        payload,
      );
      requestedWorkflowRunIdsRef.current[createdRun.id] = 'loading';
      const workflowCard = await loadWorkflowCard(createdRun.id, t);
      requestedWorkflowRunIdsRef.current[createdRun.id] = 'loaded';
      setWorkflowByRunId((prev) => ({
        ...prev,
        [createdRun.id]: mergeWorkflowCardState(prev[createdRun.id], workflowCard),
      }));
      await reloadMessagesAndTrace();
      setSelectedSessionTask(null);
      message.success(t('task.workspaceRunStarted'));
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error({
        content: detail || t('task.workspaceRunFailed'),
        duration: 6,
      });
      await reloadMessagesAndTrace().catch(() => {});
    } finally {
      setIsStartingSessionTask(false);
    }
  };

  const handleSend = () => {
    const trimmedInput = input.trim();
    if (!trimmedInput || !isConnected || isStartingSessionTask) return;
    if (selectedSessionTask) {
      void handleStartSelectedSessionTask(selectedSessionTask, trimmedInput);
      return;
    }
    // Project sessions always talk to the codex runtime: follow-ups after a
    // task run go through project-qa instead of the plain streaming chat, so
    // the whole conversation keeps document access and one consistent engine.
    if (sessionInfo?.project_id) {
      void handleStartSelectedSessionTask(
        { id: PROJECT_QA_TASK_ID } as TaskDefinition,
        trimmedInput,
      );
      return;
    }
    replacingMessageIdRef.current = null;
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: trimmedInput,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    sendMessage(trimmedInput, selectedContextSourceIds);
    setInput('');
  };

  const startTaskFromCurrentSession = (task: TaskDefinition) => {
    if (!sessionId || !sessionInfo?.project_id) {
      message.info(t('task.selectProjectFirst'));
      return;
    }

    setSelectedSessionTask(task);
  };

  const handleCopyAnswer = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;

    await navigator.clipboard.writeText(trimmed);
    message.success(t('chat.copied'));
  };

  const handleRegenerate = async (messageId: string) => {
    if (!isConnected || isStreaming || regeneratingTaskMessageId) return;

    const workflowRunId = traceByMessageId[messageId]?.workflowRunId || null;
    if (workflowRunId) {
      const targetMessage = messages.find((messageItem) => messageItem.id === messageId) || null;
      replacingMessageSnapshotRef.current = targetMessage;
      setRegeneratingTaskMessageId(messageId);
      try {
        const { data: previousRun } = await apiClient.get<WorkflowRunResponse>(`/workflow-runs/${workflowRunId}`);
        const payload: WorkflowRunCreateRequest = {
          session_id: previousRun.session_id,
          input: previousRun.input_payload,
          replace_message_id: messageId,
        };
        const { data: createdRun } = await apiClient.post<WorkflowRunResponse>(
          `/workflows/${previousRun.workflow_id}/run`,
          payload,
        );
        requestedWorkflowRunIdsRef.current[createdRun.id] = 'loading';
        const workflowCard = await loadWorkflowCard(createdRun.id, t);
        requestedWorkflowRunIdsRef.current[createdRun.id] = 'loaded';
        setWorkflowByRunId((prev) => ({
          ...prev,
          [createdRun.id]: mergeWorkflowCardState(prev[createdRun.id], workflowCard),
        }));
        await reloadMessagesAndTrace();
      } catch (error) {
        const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        if (targetMessage) {
          setMessages((prev) =>
            prev.map((messageItem) => messageItem.id === messageId ? targetMessage : messageItem)
          );
        }
        message.error(detail || t('task.workspaceRunFailed'));
      } finally {
        replacingMessageSnapshotRef.current = null;
        setRegeneratingTaskMessageId(null);
      }
      return;
    }

    const prompt = findRegeneratePrompt(messages, messageId);
    if (!prompt) {
      message.warning(t('chat.regenerateUnavailable'));
      return;
    }

    const targetMessage = messages.find((messageItem) => messageItem.id === messageId) || null;
    replacingMessageIdRef.current = messageId;
    replacingMessageSnapshotRef.current = targetMessage;
    setMessages((prev) =>
      prev.map((messageItem) =>
        messageItem.id === messageId
          ? { ...messageItem, content: '' }
          : messageItem
      )
    );
    sendMessage(prompt, selectedContextSourceIds, { replaceMessageId: messageId });
  };

  const handleOpenTrace = (
    messageId: string,
    options?: { preserveActiveResearchObject?: boolean },
  ) => {
    setSelectedTraceMessageId(messageId);
    setTimelineOpen(true);
    setMemoryActiveTab('timeline');
    if (!options?.preserveActiveResearchObject) {
      setActiveResearchObjectId(null);
    }
    window.setTimeout(() => {
      tracePanelRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
      document.getElementById(`message-${messageId}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, 0);
  };

  useEffect(() => {
    if (
      !isStreaming &&
      completedAssistantMessage.eventId > 0 &&
      handledCompletionRef.current !== completedAssistantMessage.eventId
    ) {
      handledCompletionRef.current = completedAssistantMessage.eventId;
      const assistantMessageId = completedAssistantMessage.messageId || Date.now().toString();
      const finalContent = (streamingContent || completedAssistantMessage.content || '').trim();
      if (!finalContent) return;
      const replacingMessageId = replacingMessageIdRef.current;
      if (replacingMessageId) {
        setMessages((prev) =>
          prev.map((messageItem) =>
            messageItem.id === replacingMessageId
              ? {
                  ...messageItem,
                  id: assistantMessageId,
                  content: finalContent,
                  created_at: new Date().toISOString(),
                }
              : messageItem
          )
        );
        replacingMessageIdRef.current = null;
        replacingMessageSnapshotRef.current = null;
      } else {
        setMessages((prev) => [
          ...prev,
          {
            id: assistantMessageId,
            role: 'assistant',
            content: finalContent,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    }
  }, [isStreaming, streamingContent, completedAssistantMessage]);

  useEffect(() => {
    if (!latestTrace.messageId || !latestTrace.traceId) return;
    setTraceByMessageId((prev) => ({
      ...prev,
      [latestTrace.messageId!]: latestTrace,
    }));
  }, [latestTrace]);

  useEffect(() => {
    const errorMessage = streamError.message;
    if (!errorMessage) return;
    const replacingMessageId = replacingMessageIdRef.current;
    const replacingSnapshot = replacingMessageSnapshotRef.current;
    if (replacingMessageId && replacingSnapshot) {
      setMessages((prev) =>
        prev.map((messageItem) =>
          messageItem.id === replacingMessageId ? replacingSnapshot : messageItem
        )
      );
      replacingMessageIdRef.current = null;
      replacingMessageSnapshotRef.current = null;
    }
    setMessages((prev) => [
      ...prev,
      {
        id: `error-${streamError.eventId}`,
        role: 'assistant',
        content: errorMessage,
        created_at: new Date().toISOString(),
      },
    ]);
  }, [streamError]);

  useEffect(() => {
    const workflowBindings = sortedMessages
      .map((messageItem) => ({
        runId: messageItem.agentRun?.workflow_run_id
          || traceByMessageId[messageItem.id]?.workflowRunId
          || null,
        agentRun: messageItem.agentRun,
      }))
      .filter((item): item is { runId: string; agentRun: AgentRunResponse | undefined } => Boolean(item.runId));

    workflowBindings.forEach(({ runId: workflowRunId, agentRun }) => {
      if (!workflowRunId || requestedWorkflowRunIdsRef.current[workflowRunId] === 'loading') {
        return;
      }

      const fallbackCard = agentRun ? buildLegacyWorkflowCard(agentRun) : null;
      if (fallbackCard) {
        setWorkflowByRunId((prev) => (
          ({ ...prev, [workflowRunId]: mergeWorkflowCardState(prev[workflowRunId], fallbackCard) })
        ));
      }

      if (requestedWorkflowRunIdsRef.current[workflowRunId] === 'loaded') {
        return;
      }

      requestedWorkflowRunIdsRef.current[workflowRunId] = 'loading';

      void loadWorkflowCard(workflowRunId, t)
        .then((workflowCard) => {
          requestedWorkflowRunIdsRef.current[workflowRunId] = 'loaded';
          setWorkflowByRunId((prev) => ({
            ...prev,
            [workflowRunId]: mergeWorkflowCardState(prev[workflowRunId], workflowCard),
          }));
        })
        .catch(() => {
          delete requestedWorkflowRunIdsRef.current[workflowRunId];
        });
    });
  }, [sortedMessages, t, traceByMessageId]);

  // Poll while any file source is still processing.
  useEffect(() => {
    if (!sessionId) return;
    const hasInFlight = sources.some(
      (s) => s.type === 'file' && s.processing_state && !TERMINAL_STATES.has(s.processing_state),
    );
    if (!hasInFlight) return;
    const handle = window.setInterval(() => {
      apiClient.get(`/sessions/${sessionId}/sources`).then((r) => setSources(r.data));
    }, 1000);
    return () => window.clearInterval(handle);
  }, [sources, sessionId]);

  const hasActiveRun = sessionRuns.some(
    (run) =>
      run.status === 'running' ||
      run.status === 'pending' ||
      run.status === 'planning',
  );

  // Follow in-flight runs no matter how this page was reached (started here,
  // from the home page, or before a refresh). The poll runs continuously;
  // runWasActiveRef ensures completion handling fires only once per run.
  const runWasActiveRef = useRef(false);
  useEffect(() => {
    if (!sessionId || isStartingSessionTask) return;
    const poll = async () => {
      try {
        const { data } = await apiClient.get(
          `/sessions/${sessionId}/orchestration-runs/progress`,
        );
        const runStatus = data?.status as string | null | undefined;
        if (
          runStatus === 'running' ||
          runStatus === 'pending' ||
          runStatus === 'planning'
        ) {
          runWasActiveRef.current = true;
          setRunProgressActive(true);
          const events: unknown[] = Array.isArray(data?.events) ? data.events : [];
          const lines = events
            .map(summarizeRunProgressEvent)
            .filter((line): line is string => Boolean(line));
          setRunProgressLines(lines.slice(-6));
          return;
        }
        if (runStatus && runWasActiveRef.current) {
          runWasActiveRef.current = false;
          setRunProgressActive(false);
          setRunProgressLines([]);
          if (runStatus === 'failed') {
            message.error(t('task.workspaceRunFailed'));
          }
          await reloadMessagesAndTrace().catch(() => {});
          const runs = await apiClient
            .get(`/sessions/${sessionId}/orchestration-runs`)
            .catch(() => null);
          if (runs) {
            setSessionRuns(
              runs.data as Array<{ task_id?: string | null; status?: string | null }>,
            );
          }
        }
      } catch {
        // Transient poll failures are fine; the next tick retries.
      }
    };
    void poll();
    const handle = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      window.clearInterval(handle);
      runWasActiveRef.current = false;
      setRunProgressActive(false);
      setRunProgressLines([]);
    };
  }, [sessionId, isStartingSessionTask]);

  const handleUpload = async (file: File) => {
    if (!isAcceptedUploadFile(file)) {
      notification.error({
        message: t('source.unsupportedFileType'),
        description: file.name,
        duration: 5,
      });
      return false;
    }
    setUploading(true);
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const isZip = file.name.toLowerCase().endsWith('.zip');
    const optimistic: Source = {
      id: tempId,
      type: 'file',
      name: file.name,
      processing_state: 'pending',
      progress: 0,
      error_message: null,
    };
    setSources((prev) => [...prev, optimistic]);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const { data } = await apiClient.post(`/sessions/${sessionId}/sources`, formData, { timeout: 300000 });
      if (isZip && data.sources) {
        // ZIP response: replace optimistic entry with all extracted sources
        setSources((prev) => {
          const withoutTemp = prev.filter((s) => s.id !== tempId);
          const existingIds = new Set(withoutTemp.map((s: Source) => s.id));
          const newSources = data.sources.filter(
            (s: Source) => !existingIds.has(s.id),
          );
          return [...withoutTemp, ...newSources];
        });
        setSelectedSourceIds((prev) => [
          ...prev,
          ...data.sources.map((s: Source) => s.id),
        ]);
        if (data.errors?.length) {
          data.errors.forEach((err: string) =>
            notification.warning({ message: err, duration: 0 }),
          );
        }
      } else {
        setSources((prev) => {
          const withoutTemp = prev.filter((s) => s.id !== tempId);
          const exists = withoutTemp.some((s) => s.id === data.id);
          return exists ? withoutTemp : [...withoutTemp, data];
        });
        setSelectedSourceIds((prev) => [...prev, data.id]);
        if (data.duplicate_info) {
          showDuplicateUploadModal({ info: data.duplicate_info, t });
        }
      }
      const refreshedSources = await apiClient.get<Source[]>(`/sessions/${sessionId}/sources`);
      setSources(refreshedSources.data);
      setSelectedSourceIds((prev) => prev.filter((id) => refreshedSources.data.some((source) => source.id === id)));
    } catch (err: unknown) {
      setSources((prev) => prev.filter((s) => s.id !== tempId));
      const duplicateInfo = getDuplicateUploadInfo(err);
      if (duplicateInfo) {
        showDuplicateUploadModal({
          info: duplicateInfo,
          t,
          onUseExisting: duplicateInfo.can_use_existing
            ? () => { void linkSource(duplicateInfo.existing_source_id); }
            : undefined,
        });
        return false;
      }
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      notification.error({
        message: t('source.uploadFailed'),
        description: typeof detail === 'string' ? detail : undefined,
        duration: 0,
      });
    } finally {
      setUploading(false);
    }
    return false;
  };

  const openLinkModal = () => {
    apiClient.get(`/sessions/${sessionId}/available-sources`)
      .then((r) => setAvailableSources(r.data))
      .catch(() => setAvailableSources([]));
    setShowLinkModal(true);
  };

  const linkSource = async (sourceId: string) => {
    try {
      const formData = new FormData();
      formData.append('source_id', sourceId);
      await apiClient.post(`/sessions/${sessionId}/sources`, formData);
      const refreshedSources = await apiClient.get<Source[]>(`/sessions/${sessionId}/sources`);
      setSources(refreshedSources.data);
      setSelectedSourceIds((prev) => Array.from(new Set([...prev, sourceId]))
        .filter((id) => refreshedSources.data.some((source) => source.id === id)));
      setShowLinkModal(false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : t('source.linkFailed'));
    }
  };

  const groupedAvailableSourceOptions = [
    {
      label: t('source.categoryProject'),
      options: availableSources
        .filter((item) => item.category === 'project')
        .map((item) => ({
          value: item.source.id,
          label: `${item.source.name} (${item.source.type})`,
        })),
    },
    {
      label: t('source.categoryLabPublic'),
      options: availableSources
        .filter((item) => item.category === 'lab_public')
        .map((item) => ({
          value: item.source.id,
          label: `${item.source.name} (${item.source.type})`,
        })),
    },
    {
      label: t('source.categoryMyMaterials'),
      options: availableSources
        .filter((item) => item.category === 'my_materials')
        .map((item) => ({
          value: item.source.id,
          label: `${item.source.name} (${item.source.type})`,
        })),
    },
  ].filter((group) => group.options.length > 0);

  const toggleSource = (sourceId: string) => {
    setSelectedSourceIds((prev) =>
      prev.includes(sourceId) ? prev.filter((id) => id !== sourceId) : [...prev, sourceId]
    );
  };

  const removeFromSession = async (sourceId: string) => {
    try {
      await apiClient.delete(`/sessions/${sessionId}/sources/${sourceId}`);
      setSources((prev) => prev.filter((s) => s.id !== sourceId));
      setSelectedSourceIds((prev) => prev.filter((id) => id !== sourceId));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : t('source.removeFailed'));
    }
  };

  const openRenameModal = (source: Source) => {
    setRenameTarget(source);
    setRenameValue(source.name);
  };

  const submitRename = async () => {
    if (!renameTarget || !renameValue.trim()) return;
    try {
      const { data } = await apiClient.patch(
        `/sessions/${sessionId}/sources/${renameTarget.id}`,
        { display_name: renameValue.trim() },
      );
      setSources((prev) => prev.map((s) => s.id === renameTarget.id ? { ...s, name: data.name } : s));
      message.success(t('source.renameSuccess'));
      setRenameTarget(null);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('source.renameFailed'));
    }
  };

  const retrySource = (sourceId: string) => {
    apiClient.post(`/sources/${sourceId}/retry`).then(() => {
      message.success(t('source.retrySuccess'));
      apiClient.get(`/sessions/${sessionId}/sources`).then((r) => setSources(r.data));
    });
  };

  const saveAsNote = async (msg: Message) => {
    await apiClient.post('/notes', {
      session_id: sessionId,
      message_id: msg.id,
      content: msg.content,
    });
    message.success(t('note.saved'));
  };

  const saveAsResearchObject = async (
    msg: Message,
    type: 'hypothesis' | 'discussion',
  ) => {
    if (!sessionId) return;

    const trace = traceByMessageId[msg.id];
    const title = type === 'hypothesis'
      ? t('researchObject.defaultHypothesisTitle')
      : t('researchObject.defaultDiscussionTitle');

    const { data } = await apiClient.post<SessionResearchObject>('/research-objects', {
      session_id: sessionId,
      message_id: msg.id,
      type,
      title,
      content: msg.content,
      content_json: {
        origin: msg.agentRun ? 'agent_run' : 'assistant_message',
        trace_id: trace?.traceId ?? null,
        source_ids: trace?.inputs.source_ids ?? [],
        agent_run_id: msg.agentRun?.id ?? null,
      },
    });

    setResearchObjects((prev) => [data, ...prev]);
    setSelectedTraceMessageId(msg.id);
    setTimelineOpen(true);
    setMemoryActiveTab('timeline');
    message.success(
      type === 'hypothesis'
        ? t('researchObject.savedHypothesis')
        : t('researchObject.savedDiscussion'),
    );
  };

  const activeResearchObject = activeResearchObjectId
    ? researchObjects.find((item) => item.id === activeResearchObjectId) || null
    : null;

  const loadResearchObjectRelations = async (objectId: string) => {
    try {
      const { data } = await apiClient.get<SessionResearchObjectRelation[]>(
        `/research-objects/${objectId}/relations`,
      );
      setRelationsByObjectId((prev) => ({ ...prev, [objectId]: data }));
    } catch {
      message.error(t('relations.loadFailed'));
    }
  };

  const handleSelectResearchObject = (item: SessionResearchObject) => {
    setActiveResearchObjectId(item.id);
    setTimelineOpen(true);
    void loadResearchObjectRelations(item.id);
    if (item.message_id) {
      handleOpenTrace(item.message_id, { preserveActiveResearchObject: true });
    }
  };

  const submitRelationCreate = async (
    sourceObjectId: string,
    payload: ResearchRelationSubmitPayload,
  ) => {
    const sourceObject = researchObjects.find((item) => item.id === sourceObjectId);
    if (!sourceObject) return;

    const trace = sourceObject.message_id
      ? traceByMessageId[sourceObject.message_id]
      : null;
    const payloadEvidence = payload.metadata_json.evidence;
    const mergedPayload: ResearchRelationSubmitPayload = {
      ...payload,
      metadata_json: {
        confidence: payload.metadata_json.confidence,
        evidence: {
          ...payloadEvidence,
          ...(trace?.traceId ? { trace_id: trace.traceId } : {}),
          citations: trace?.citations?.length
            ? trace.citations as Array<Record<string, unknown>>
            : payloadEvidence.citations,
        },
      },
    };

    try {
      const { data } = await apiClient.post<SessionResearchObjectRelation>(
        `/research-objects/${sourceObjectId}/relations`,
        mergedPayload,
      );
      setRelationsByObjectId((prev) => ({
        ...prev,
        [sourceObjectId]: [...(prev[sourceObjectId] || []), data],
      }));
      message.success(t('relations.created'));
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('relations.createFailed'));
    }
  };

  const deleteRelation = async (relationId: string) => {
    if (!activeResearchObjectId) return;
    try {
      await apiClient.delete(`/research-object-relations/${relationId}`);
      setRelationsByObjectId((prev) => ({
        ...prev,
        [activeResearchObjectId]: (prev[activeResearchObjectId] || []).filter((item) => item.id !== relationId),
      }));
      message.success(t('relations.deleted'));
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('relations.deleteFailed'));
    }
  };

  const openResearchObjectEditor = (item: SessionResearchObject) => {
    setEditingResearchObject(item);
    setResearchObjectTitleDraft(item.title || '');
    setResearchObjectContentDraft(item.content || '');
  };

  const submitResearchObjectUpdate = async () => {
    if (!editingResearchObject) return;

    const { data } = await apiClient.put<SessionResearchObject>(
      `/research-objects/${editingResearchObject.id}`,
      {
        title: researchObjectTitleDraft.trim() || null,
        content: researchObjectContentDraft.trim() || null,
      },
    );

    setResearchObjects((prev) => prev.map((item) => (
      item.id === data.id ? data : item
    )));
    setEditingResearchObject(null);
    message.success(t('researchObject.updated'));
  };

  const deleteResearchObject = async (item: SessionResearchObject) => {
    await apiClient.delete(`/research-objects/${item.id}`);
    setResearchObjects((prev) => prev.filter((entry) => entry.id !== item.id));
    message.success(t('researchObject.deleted'));
  };

  const { isDragOver, dropHandlers } = useFileDrop(
    (files) => { files.forEach((f) => handleUpload(f)); },
    (rejected) => {
      notification.error({
        message: t('source.unsupportedFileType'),
        description: rejected.map((f) => f.name).join(', '),
        duration: 5,
      });
    },
  );

  const displayTitle = sessionInfo?.title || (sessionId ? `Session ${sessionId.slice(0, 8)}` : '');
  const activeTrace = selectedTraceMessageId
    ? traceByMessageId[selectedTraceMessageId] || null
    : null;
  const isReplacingMessage = isStreaming && Boolean(replacingMessageIdRef.current);
  const activeTraceMessage = selectedTraceMessageId
    ? messages.find((message) => message.id === selectedTraceMessageId) || null
    : null;
  const sourceNameMap = new Map(sources.map((source) => [source.id, source.name]));
  Object.entries(traceSourceNameById).forEach(([sourceId, sourceName]) => {
    if (!sourceNameMap.has(sourceId)) {
      sourceNameMap.set(sourceId, sourceName);
    }
  });
  const getTraceSourceName = (sourceId: string | undefined) => {
    if (!sourceId) return t('session.traceUnknownSource');
    const sourceName = sourceNameMap.get(sourceId);
    if (sourceName) return sourceName;
    return looksLikeUuid(sourceId) ? t('session.traceUnknownSource') : sourceId;
  };
  const traceSourceNames = (activeTrace?.inputs.source_ids || []).map(
    (sourceId) => getTraceSourceName(sourceId),
  );
  const citationCards: CitationCardItem[] = (activeTrace?.citations || []).map((citation) => ({
    ...citation,
    sourceName: getTraceSourceName(citation.source_id),
  }));

  useEffect(() => {
    if (!activeTrace) return;

    const traceSourceIds = new Set<string>();
    (activeTrace.inputs.source_ids || []).forEach((sourceId) => traceSourceIds.add(sourceId));
    activeTrace.citations.forEach((citation) => {
      if (citation.source_id) {
        traceSourceIds.add(citation.source_id);
      }
    });
    activeTrace.retrieval.forEach((item) => {
      if (item.source_id) {
        traceSourceIds.add(item.source_id);
      }
    });

    const missingSourceIds = Array.from(traceSourceIds).filter(
      (sourceId) => !sourceNameMap.has(sourceId) && !traceSourceNameById[sourceId],
    );
    if (missingSourceIds.length === 0) return;

    let cancelled = false;
    Promise.all(
      missingSourceIds.map((sourceId) =>
        apiClient.get<Source>(`/sources/${sourceId}`)
          .then((response) => [sourceId, response.data.name] as const)
          .catch(() => [sourceId, sourceId] as const)
      )
    ).then((entries) => {
      if (cancelled) return;
      setTraceSourceNameById((prev) => ({
        ...prev,
        ...Object.fromEntries(entries),
      }));
    });

    return () => {
      cancelled = true;
    };
  }, [activeTrace, sourceNameMap, traceSourceNameById]);

  const openResearchObjectInMemory = (item: SessionResearchObject, tab: MemoryTabKey = memoryActiveTab) => {
    handleSelectResearchObject(item);
    setMemoryActiveTab(tab);
  };

  const renderResearchObjectCard = (item: SessionResearchObject, tab: MemoryTabKey) => (
    <Card
      size="small"
      style={{
        width: '100%',
        cursor: 'pointer',
        borderLeft: `4px solid ${item.type === 'hypothesis' ? token.purple4 : token.colorPrimary}`,
        background: item.type === 'hypothesis' ? token.purple1 : token.colorPrimaryBg,
      }}
      onClick={() => openResearchObjectInMemory(item, tab)}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openResearchObjectInMemory(item, tab);
        }
      }}
      extra={(
        <Space size={8}>
          <ResearchObjectDirectionSuggestion researchObject={item} compact />
          <Button
            type="link"
            size="small"
            onClick={(event) => {
              event.stopPropagation();
              openResearchObjectEditor(item);
            }}
            style={{ padding: 0 }}
          >
            {t('common.edit')}
          </Button>
          <Button
            type="link"
            size="small"
            danger
            onClick={(event) => {
              event.stopPropagation();
              Modal.confirm({
                title: t('researchObject.deleteConfirm'),
                onOk: () => deleteResearchObject(item),
              });
            }}
            style={{ padding: 0 }}
          >
            {t('common.delete')}
          </Button>
        </Space>
      )}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          <Tag color={item.type === 'hypothesis' ? 'purple' : 'blue'}>
            {item.type === 'hypothesis'
              ? t('researchObject.typeHypothesis')
              : t('researchObject.typeDiscussion')}
          </Tag>
          <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>
            {new Date(item.created_at).toLocaleString()}
          </span>
        </div>
        <div style={{ fontWeight: 500 }}>
          {item.title || t('timeline.untitled')}
        </div>
        <div style={{ whiteSpace: 'pre-wrap', color: token.colorTextSecondary, fontSize: 13 }}>
          {buildResearchObjectPreview(item, t)}
        </div>
        {item.message_id && (
          <div style={{ color: token.colorPrimary, fontSize: 12 }}>
            {t('timeline.openSourceAnswer')}
          </div>
        )}
      </div>
    </Card>
  );

  const renderResearchObjectList = (
    items: SessionResearchObject[],
    tab: MemoryTabKey,
    emptyText = t('timeline.empty'),
  ) => (
    items.length > 0 ? (
      <List
        split={false}
        dataSource={items}
        locale={{ emptyText }}
        renderItem={(item) => (
          <List.Item style={{ padding: 0, marginBottom: 12 }}>
            {renderResearchObjectCard(item, tab)}
          </List.Item>
        )}
      />
    ) : (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
    )
  );

  const renderTracePanel = () => (
    <>
      <div ref={tracePanelRef}>
        <Card
          size="small"
          title={t('session.tracePanelTitle')}
          styles={{ body: { display: 'flex', flexDirection: 'column', gap: 12 } }}
        >
          {activeTrace?.traceId ? (
            <>
              <div>
                <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 4 }}>
                  {t('session.traceForAnswer')}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', color: token.colorTextSecondary, fontSize: 13 }}>
                  {activeTraceMessage?.content || t('session.traceAnswerEmpty')}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 4 }}>
                  {t('session.traceQuestion')}
                </div>
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {activeTrace.inputs.query || t('session.traceQuestionEmpty')}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
                  {t('session.traceScope')}
                </div>
                {traceSourceNames.length > 0 ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {traceSourceNames.map((name) => (
                      <Tag key={name} color="blue">
                        {name}
                      </Tag>
                    ))}
                  </div>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('session.traceScopeEmpty')} />
                )}
              </div>

              <div>
                <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 8 }}>
                  {t('session.summarySteps')}
                </div>
                {activeTrace.summarySteps.length > 0 ? (
                  <List
                    size="small"
                    bordered
                    dataSource={activeTrace.summarySteps}
                    renderItem={(step, index) => (
                      <List.Item>
                        <span style={{ color: token.colorTextTertiary, marginRight: 8 }}>{index + 1}.</span>
                        <span>{step}</span>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('session.summaryStepsEmpty')} />
                )}
              </div>
            </>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('session.traceEmpty')} />
          )}
        </Card>
      </div>

      <Card
        size="small"
        title={t('session.citationsTitle')}
        extra={<Tag>{citationCards.length}</Tag>}
        styles={{ body: { padding: 12 } }}
      >
        {citationCards.length > 0 ? (
          <List
            split={false}
            dataSource={citationCards}
            renderItem={(citation) => (
              <List.Item style={{ padding: 0, marginBottom: 12 }}>
                <Card size="small" style={{ width: '100%' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    <Tag color="purple">{citation.sourceName}</Tag>
                    {typeof citation.score === 'number' && (
                      <Tag>{t('session.citationScore', { score: citation.score.toFixed(2) })}</Tag>
                    )}
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap', color: token.colorTextSecondary, fontSize: 13 }}>
                    {citation.snippet || t('session.citationSnippetEmpty')}
                  </div>
                </Card>
              </List.Item>
            )}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('session.citationsEmpty')} />
        )}
      </Card>
    </>
  );

  const renderActiveResearchObjectDetails = (viewMode: 'details' | 'graph' = 'details') => (
    activeResearchObject ? (
      <ResearchObjectDetails
        activeObject={activeResearchObject}
        relations={relationsByObjectId[activeResearchObject.id] || []}
        availableTargets={researchObjects}
        viewMode={viewMode}
        onSubmitRelation={submitRelationCreate}
        onDeleteRelation={deleteRelation}
        onSelectTargetObject={(targetObjectId) => {
          const targetObject = researchObjects.find((item) => item.id === targetObjectId);
          if (targetObject) {
            openResearchObjectInMemory(targetObject, viewMode === 'graph' ? 'graph' : memoryActiveTab);
          }
        }}
      />
    ) : (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('memory.selectObjectForGraph')} />
    )
  );

  const renderGraphTab = () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ color: token.colorTextTertiary, fontSize: 13 }}>
        {t('memory.graphHint')}
      </div>
      <Select
        value={activeResearchObjectId || undefined}
        options={researchObjects.map((item) => ({
          value: item.id,
          label: buildResearchObjectOptionLabel(item, t),
        }))}
        placeholder={t('memory.graphObjectPlaceholder')}
        onChange={(objectId: string) => {
          const targetObject = researchObjects.find((item) => item.id === objectId);
          if (targetObject) {
            openResearchObjectInMemory(targetObject, 'graph');
          }
        }}
        disabled={researchObjects.length === 0}
      />
      {researchObjects.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('memory.objectsEmpty')} />
      ) : (
        renderActiveResearchObjectDetails('graph')
      )}
    </div>
  );

  const renderObjectsByType = () => {
    const hypotheses = researchObjects.filter((item) => item.type === 'hypothesis');
    const discussions = researchObjects.filter((item) => item.type === 'discussion');

    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Card size="small" title={t('memory.objectsHypotheses')} extra={<Tag>{hypotheses.length}</Tag>}>
          {renderResearchObjectList(hypotheses, 'objects', t('memory.objectsEmpty'))}
        </Card>
        <Card size="small" title={t('memory.objectsDiscussions')} extra={<Tag>{discussions.length}</Tag>}>
          {renderResearchObjectList(discussions, 'objects', t('memory.objectsEmpty'))}
        </Card>
      </div>
    );
  };

  const resetSaveMemoryState = () => {
    setSaveMemoryModalOpen(false);
    setSelectedAgentMessage(null);
    setSaveMemoryType('hypothesis');
    setSaveMemoryTitleDraft('');
    setSaveMemoryContentDraft('');
    setSaveMemoryRelationEnabled(false);
    setSaveMemoryRelationType('supports');
    setSaveMemoryRelationTargetId(null);
    setSaveMemoryRelationNote('');
    setIsSavingAgentMemory(false);
  };

  const openSaveMemoryModal = (msg: Message) => {
    const defaultType: 'hypothesis' | 'discussion' = 'hypothesis';
    const formattedAgentOutput = msg.agentRun
      ? formatAgentOutputForMemory(msg.agentRun, msg.content, t)
      : null;
    const defaultTitle = formattedAgentOutput
      ? formattedAgentOutput.title.slice(0, 500)
      : '';
    setSelectedAgentMessage(msg);
    setSaveMemoryType(defaultType);
    setSaveMemoryTitleDraft(defaultTitle);
    setSaveMemoryContentDraft(formattedAgentOutput?.content || msg.content || '');
    setSaveMemoryRelationEnabled(false);
    setSaveMemoryRelationType('supports');
    setSaveMemoryRelationTargetId(null);
    setSaveMemoryRelationNote('');
    setSaveMemoryModalOpen(true);
  };

  const buildSaveMemoryPayload = (): AgentRunSaveMemoryRequest | null => {
    if (!selectedAgentMessage?.agentRun) return null;
    return {
      type: saveMemoryType,
      title: saveMemoryTitleDraft.trim(),
      content: saveMemoryContentDraft,
      relation: {
        enabled: saveMemoryRelationEnabled,
        ...(saveMemoryRelationEnabled ? {
          relation_type: saveMemoryRelationType,
          target_object_id: saveMemoryRelationTargetId || undefined,
          note: saveMemoryRelationNote.trim() || undefined,
        } : {}),
      },
    };
  };

  const submitSaveAgentMemory = async () => {
    if (!selectedAgentMessage?.agentRun) return;

    const payload = buildSaveMemoryPayload();
    if (!payload) return;
    if (!payload.content.trim()) {
      message.warning(t('timeline.emptyContent'));
      return;
    }
    if (payload.relation.enabled && !payload.relation.target_object_id) {
      message.warning(t('agent.memoryRelationTargetRequired'));
      return;
    }

    setIsSavingAgentMemory(true);
    try {
      const { data } = await apiClient.post<AgentRunSaveMemoryResponse>(
        `/agents/runs/${selectedAgentMessage.agentRun.id}/save-memory`,
        payload,
      );
      setResearchObjects((prev) => [data.research_object, ...prev]);
      const createdRelation = data.relation;
      if (createdRelation) {
        setRelationsByObjectId((prev) => ({
          ...prev,
          [data.research_object.id]: [createdRelation],
        }));
      }
      setActiveResearchObjectId(data.research_object.id);
      setTimelineOpen(true);
      setMemoryActiveTab('timeline');
      message.success(t('agent.memorySaved'));
      resetSaveMemoryState();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('agent.memorySaveFailed'));
    } finally {
      setIsSavingAgentMemory(false);
    }
  };

  return (
    <Layout style={{ height: 'calc(100vh - 64px)' }}>
      <Sider
        width={280}
        theme="light"
        breakpoint="lg"
        collapsedWidth={0}
        style={{
          display: sourcePanelCollapsed ? 'none' : undefined,
          padding: 16,
          overflow: 'auto',
          border: isDragOver ? `2px dashed ${token.colorPrimary}` : '2px dashed transparent',
          background: isDragOver ? token.colorPrimaryBg : undefined,
          transition: 'background 0.15s, border-color 0.15s',
        }}
        {...dropHandlers}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
          }}
        >
          <span style={{ fontWeight: 600 }}>{t('source.sessionTitle')}</span>
          <Space size={4}>
            <Upload beforeUpload={handleUpload} showUploadList={false} multiple accept=".pdf,.docx,.txt,.md,.zip">
              <Tooltip title={uploading ? t('source.uploading') : t('source.upload')}>
                <Button
                  type="text"
                  size="small"
                  icon={uploading ? <LoadingOutlined /> : <UploadOutlined />}
                  loading={uploading}
                  aria-label={uploading ? t('source.uploading') : t('source.upload')}
                />
              </Tooltip>
            </Upload>
            <Tooltip title={t('source.link')}>
              <Button
                type="text"
                size="small"
                icon={<LinkOutlined />}
                aria-label={t('source.link')}
                onClick={openLinkModal}
                disabled={uploading}
              />
            </Tooltip>
          </Space>
        </div>
        <div style={{ marginBottom: 12 }}>
          <Button
            size="small"
            block
            disabled={pageLoading || (selectableSourceIds.length === 0 && selectedSourceIds.length === 0)}
            onClick={() => setSelectedSourceIds(allSourcesSelected ? [] : selectableSourceIds)}
          >
            {t(allSourcesSelected ? 'source.deselectAll' : 'common.selectAll')}
          </Button>
          <div style={{ marginTop: 6, fontSize: 12, color: token.colorTextSecondary }}>
            {t('source.contextSelectionHint', { count: selectedContextSourceIds.length })}
          </div>
        </div>
        <Spin spinning={pageLoading} size="small">
          <List
            size="small"
            dataSource={sources}
            locale={{ emptyText: <Empty description={t('source.emptyInSession')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(source) => {
              const checked = selectedContextSourceIds.includes(source.id);
              const state = source.processing_state;
              const displayName = source.is_shared && source.owner_name
                ? `${source.name} (${source.owner_name})`
                : source.name;
              const sharedTooltip = source.is_shared
                ? `${t('share.sharedBy')} ${source.share?.shared_by_name || source.owner_name || ''}`
                : undefined;

              const label = source.type === 'file' ? (
                <Popover
                  content={
                    <SourceThumbnail
                      sourceId={source.id}
                      alt={t('source.preview')}
                      maxWidth={250}
                      maxHeight={350}
                    />
                  }
                  title={source.name}
                  trigger="hover"
                  placement="right"
                  mouseEnterDelay={0.3}
                >
                  <span
                    onClick={(e) => { e.stopPropagation(); setPdfViewerSource(source); }}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        e.stopPropagation();
                        setPdfViewerSource(source);
                      }
                    }}
                    style={{ cursor: 'pointer' }}
                  >
                    <FilePdfOutlined style={{ marginRight: 6, color: token.colorError }} />
                    {displayName}
                    {sharedTooltip ? (
                      <Tooltip title={sharedTooltip}>
                        <ShareAltOutlined style={{ marginLeft: 6, color: token.colorSuccess, fontSize: 12 }} />
                      </Tooltip>
                    ) : null}
                  </span>
                </Popover>
              ) : source.type === 'group' ? (
                <Popover
                  content={<GroupMemberPreview groupId={source.id} />}
                  title={source.name}
                  trigger="hover"
                  placement="right"
                  mouseEnterDelay={0.3}
                >
                  <span>
                    <FolderOutlined style={{ marginRight: 6, color: token.colorPrimary }} />
                    {displayName}
                    {sharedTooltip ? (
                      <Tooltip title={sharedTooltip}>
                        <ShareAltOutlined style={{ marginLeft: 6, color: token.colorSuccess, fontSize: 12 }} />
                      </Tooltip>
                    ) : null}
                  </span>
                </Popover>
              ) : (
                <span>{displayName}</span>
              );

              const menuItems = [
                {
                  key: 'rename',
                  label: t('source.renameInSession'),
                  icon: <EditOutlined />,
                  onClick: () => openRenameModal(source),
                },
                {
                  key: 'remove',
                  label: t('source.removeFromSession'),
                  icon: <DeleteOutlined />,
                  danger: true,
                  onClick: () => {
                    Modal.confirm({
                      title: t('source.removeConfirm'),
                      onOk: () => removeFromSession(source.id),
                    });
                  },
                },
              ];

              return (
                <List.Item
                  style={{ paddingRight: 4 }}
                  extra={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
                        <Button
                          type="text"
                          size="small"
                          icon={<EllipsisOutlined />}
                          aria-label={t('common.actions')}
                          onClick={(e) => e.stopPropagation()}
                          style={{ flexShrink: 0 }}
                        />
                      </Dropdown>
                      <Checkbox
                        checked={checked}
                        disabled={!isSourceSelectable(source)}
                        onChange={(e: CheckboxChangeEvent) => {
                          e.stopPropagation();
                          toggleSource(source.id);
                        }}
                      />
                    </div>
                  }
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      {label}
                      {state === 'failed' ? (
                        <Tooltip title={t('source.retry')}>
                          <Button
                            type="text"
                            size="small"
                            icon={<RedoOutlined />}
                            aria-label={t('source.retry')}
                            onClick={() => retrySource(source.id)}
                            style={{ color: token.colorPrimary, fontSize: 12, height: 18, width: 18 }}
                          />
                        </Tooltip>
                      ) : null}
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <ProcessingStatusTag
                        state={state}
                        progress={source.progress}
                        errorMessage={source.error_message}
                      />
                    </div>
                  </div>
                </List.Item>
              );
            }}
          />
        </Spin>
        <Modal
          title={t('source.link')}
          open={showLinkModal}
          onCancel={() => setShowLinkModal(false)}
          footer={null}
        >
          <Select
            showSearch
            style={{ width: '100%' }}
            placeholder={t('source.selectAvailableSource')}
            optionFilterProp="label"
            onSelect={(value: string) => linkSource(value)}
            options={groupedAvailableSourceOptions}
            notFoundContent={<Empty description={t('source.noAvailableSources')} />}
          />
        </Modal>
        <Modal
          title={t('source.renameTitle')}
          open={!!renameTarget}
          onCancel={() => setRenameTarget(null)}
          onOk={submitRename}
          okButtonProps={{ disabled: !renameValue.trim() }}
          destroyOnHidden
        >
          <Form layout="vertical" style={{ marginTop: 16 }}>
            <Form.Item label={t('source.renameLabel')}>
              <Input
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                placeholder={t('source.renamePlaceholder')}
                onPressEnter={submitRename}
                autoFocus
              />
            </Form.Item>
          </Form>
        </Modal>
        <PdfPreviewModal
          open={!!pdfViewerSource}
          sourceId={pdfViewerSource?.id || null}
          title={pdfViewerSource?.name}
          onClose={() => setPdfViewerSource(null)}
        />
      </Sider>

      <Content style={{ display: 'flex', flexDirection: 'column', padding: 16, overflow: 'hidden', minHeight: 0 }}>
        <ChatContainer
          topBar={(
            <div
              style={{
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <Breadcrumb
                  items={[
                    ...(projectInfo
                      ? [{
                        title: (
                          <Button
                            type="link"
                            size="small"
                            style={{ padding: 0, height: 'auto' }}
                            onClick={() => navigate(`/projects/${projectInfo.id}`)}
                          >
                            {projectInfo.name}
                          </Button>
                        ),
                      }]
                      : []),
                    { title: displayTitle },
                  ]}
                />
                <div style={{ flex: 1 }} />
                {!isConnected && !pageLoading && (
                  <Tag icon={<LoadingOutlined spin />} color="warning">
                    {t('chat.connecting')}
                  </Tag>
                )}
              </div>
              {sessionInfo?.project_id ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    marginTop: 10,
                    overflowX: 'auto',
                    paddingBottom: 2,
                  }}
                >
                  <span style={{ color: token.colorTextSecondary, whiteSpace: 'nowrap', fontSize: 13 }}>
                    {t('session.recommendedTasks')}
                  </span>
                  <Spin spinning={sessionTasksLoading} size="small">
                    <Space size={8} wrap>
                      {sessionRecommendedTasks.map((task) => (
                        <Button
                          key={task.id}
                          size="small"
                          type={selectedSessionTask?.id === task.id ? 'primary' : 'default'}
                          icon={<ExperimentOutlined />}
                          disabled={isStartingSessionTask}
                          onClick={() => startTaskFromCurrentSession(task)}
                        >
                          {task.name}
                          <span
                            style={{
                              marginLeft: 6,
                              color: selectedSessionTask?.id === task.id
                                ? token.colorTextLightSolid
                                : token.colorTextSecondary,
                              fontSize: 12,
                            }}
                          >
                            {getTaskRuntimeKind(task) === 'codex' ? t('task.modeCodex') : t('task.modeWorkflow')}
                          </span>
                        </Button>
                      ))}
                    </Space>
                  </Spin>
                </div>
              ) : null}
            </div>
          )}
          composer={(
            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={handleSend}
              placeholder={selectedSessionTask ? t('task.sessionTaskPlaceholder') : t('chat.placeholder')}
              disabled={!isConnected || isStreaming || isStartingSessionTask}
              loading={isStreaming || isStartingSessionTask}
              selectedSourcesCount={selectedContextSourceIds.length}
              onSourcesClick={() => setSourcePanelCollapsed((prev) => !prev)}
              sourcesCollapsed={sourcePanelCollapsed}
              extraActions={(
                <>
                  {selectedSessionTask ? (
                    <Tag
                      color="blue"
                      closable={!isStartingSessionTask}
                      onClose={() => setSelectedSessionTask(null)}
                      style={{ marginInlineEnd: 0 }}
                    >
                      {t('task.sessionTaskSelected', {
                        task: selectedSessionTask.name,
                        runtime: getTaskRuntimeKind(selectedSessionTask) === 'codex'
                          ? t('task.modeCodex')
                          : t('task.modeWorkflow'),
                      })}
                    </Tag>
                  ) : null}
                  <Tooltip title={timelineOpen ? t('memory.hide') : t('memory.show')}>
                    <Button
                      type={timelineOpen ? 'primary' : 'text'}
                      size="small"
                      icon={<BookOutlined />}
                      aria-label={timelineOpen ? t('memory.hide') : t('memory.show')}
                      onClick={() => setTimelineOpen((prev) => !prev)}
                    />
                  </Tooltip>
                </>
              )}
            />
          )}
        >
          <Spin spinning={pageLoading}>
            {sortedMessages.length === 0 && !isStreaming && (
              <EmptyState
                icon={<RobotOutlined />}
                title={t('chat.emptyTitle')}
                description={t('chat.emptyDescription')}
              />
            )}
            {sortedMessages.map((msg) => {
              const isTraceSelected = msg.role === 'assistant' && selectedTraceMessageId === msg.id;
              const isRegeneratingMessage = (
                msg.role === 'assistant'
                && isStreaming
                && replacingMessageIdRef.current === msg.id
              );
              const isRegeneratingTaskMessage = msg.role === 'assistant' && regeneratingTaskMessageId === msg.id;
              const normalizedAgentOutput = msg.agentRun
                ? normalizeAgentOutput(msg.agentRun, msg.content)
                : null;
              const workflowRunId = isRegeneratingTaskMessage
                ? null
                : msg.agentRun?.workflow_run_id
                || traceByMessageId[msg.id]?.workflowRunId
                || null;
              const workflowCard = workflowRunId ? workflowByRunId[workflowRunId] : null;
              const workflowRuntimeLabel = workflowCard?.steps.some((step) => step.runtime === 'codex')
                ? t('task.runtimeCodex')
                : workflowCard
                  ? t('task.runtimePlatform')
                  : null;
              const normalizedWorkflowOutput = workflowRunId
                ? normalizeWorkflowOutput(workflowCard?.outputPayload, msg.content)
                : null;
              const hasWorkflowOutput = Boolean(
                normalizedWorkflowOutput && (
                  normalizedWorkflowOutput.overview
                  || normalizedWorkflowOutput.summary
                  || normalizedWorkflowOutput.draft
                  || normalizedWorkflowOutput.keyPoints.length > 0
                  || normalizedWorkflowOutput.contradictions.length > 0
                  || normalizedWorkflowOutput.gaps.length > 0
                  || normalizedWorkflowOutput.validationNotes.length > 0
                  || normalizedWorkflowOutput.rawSections.length > 0
                ),
              );
              const isWorkflowExpanded = workflowRunId ? !!expandedWorkflowRunIds[workflowRunId] : false;
              const visibleWorkflowSteps = workflowCard
                ? (isWorkflowExpanded ? workflowCard.steps : workflowCard.steps.slice(0, 3))
                : [];
              const showWorkflowExpand = workflowCard ? shouldShowWorkflowExpand(workflowCard) : false;

              const actions: ChatMessageAction[] = [];
              if (msg.role === 'assistant' && !isRegeneratingMessage && !isRegeneratingTaskMessage) {
                if (msg.content.trim()) {
                  actions.push({
                    key: 'copy',
                    label: t('chat.copy'),
                    icon: <CopyOutlined />,
                    onClick: () => { void handleCopyAnswer(msg.content); },
                  });
                }
                if (!msg.agentRun) {
                  actions.push({
                    key: 'regenerate',
                    label: t('chat.regenerate'),
                    icon: <ReloadOutlined />,
                    onClick: () => handleRegenerate(msg.id),
                  });
                }
                if (msg.agentRun) {
                  actions.push({
                    key: 'saveMemory',
                    label: t('agent.saveToMemory'),
                    icon: <SaveOutlined />,
                    onClick: () => openSaveMemoryModal(msg),
                  });
                }
                if (traceByMessageId[msg.id]) {
                  actions.push({
                    key: 'trace',
                    label: workflowRunId ? t('workflow.traceCta') : t('session.viewTrace'),
                    icon: <FileSearchOutlined />,
                    onClick: () => handleOpenTrace(msg.id),
                  });
                }
                actions.push({
                  key: 'note',
                  label: t('note.save'),
                  icon: <BookOutlined />,
                  onClick: () => saveAsNote(msg),
                });
                if (msg.content.trim()) {
                  actions.push({
                    key: 'hypothesis',
                    label: t('researchObject.saveAsHypothesis'),
                    icon: <ExperimentOutlined />,
                    onClick: () => { void saveAsResearchObject(msg, 'hypothesis'); },
                  });
                  actions.push({
                    key: 'discussion',
                    label: t('researchObject.saveAsDiscussion'),
                    icon: <CommentOutlined />,
                    onClick: () => { void saveAsResearchObject(msg, 'discussion'); },
                  });
                }
              }

              const content = msg.role === 'user'
                ? msg.content
                : isRegeneratingTaskMessage
                  ? t('task.sessionTaskRunning', { task: t('task.workspaceTaskLabel') })
                : isRegeneratingMessage
                  ? (streamingContent || t('chat.thinking'))
                : msg.agentRun
                  ? (normalizedAgentOutput?.overview || t('agent.noStructuredOutput'))
                  : hasWorkflowOutput
                    ? ''
                  : msg.content;

              return (
                <ChatMessage
                  key={msg.id}
                  id={`message-${msg.id}`}
                  role={msg.role as 'user' | 'assistant'}
                  content={content}
                  renderMarkdown={msg.role === 'assistant' && !isRegeneratingMessage && !isRegeneratingTaskMessage}
                  timestamp={formatDateTime(msg.created_at, i18n.language)}
                  actions={actions}
                  selected={isTraceSelected}
                  hideContentBubble={msg.role === 'assistant' && hasWorkflowOutput}
                  onSourceClick={handleMessageSourceClick}
                >
                  {(msg.role === 'assistant' && hasWorkflowOutput && normalizedWorkflowOutput) || runUsageByMessageId[msg.id] ? (
                    <>
                      {msg.role === 'assistant' && hasWorkflowOutput && normalizedWorkflowOutput ? (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 16,
                        padding: '10px 14px',
                        borderRadius: token.borderRadius * 1.5,
                        background: token.colorFillTertiary,
                      }}
                    >
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                        <Tag color="geekblue">{t('task.resultCardTag')}</Tag>
                        {workflowRuntimeLabel ? (
                          <Tag color={workflowRuntimeLabel === t('task.runtimeCodex') ? 'purple' : 'geekblue'}>
                            {workflowRuntimeLabel}
                          </Tag>
                        ) : null}
                        {workflowCard ? (
                          <Tag color={getWorkflowStatusColor(workflowCard.status)}>
                            {getWorkflowStatusLabel(workflowCard.status, t)}
                          </Tag>
                        ) : null}
                      </div>

                      {(normalizedWorkflowOutput.overview || normalizedWorkflowOutput.summary || normalizedWorkflowOutput.draft) ? (
                        <div
                          style={{
                            padding: '12px 14px',
                            borderRadius: token.borderRadiusLG,
                            background: token.colorFillQuaternary,
                            border: `1px solid ${token.colorBorderSecondary}`,
                          }}
                        >
                          <MarkdownContent
                            content={normalizedWorkflowOutput.overview
                              || normalizedWorkflowOutput.summary
                              || normalizedWorkflowOutput.draft}
                          />
                        </div>
                      ) : null}

                      {normalizedWorkflowOutput.keyPoints.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                            {t('task.resultField.key_points')}
                          </div>
                          <List
                            size="small"
                            split={false}
                            dataSource={normalizedWorkflowOutput.keyPoints}
                            renderItem={(item) => (
                              <List.Item style={{ padding: '2px 0' }}>
                                <MarkdownContent content={item} />
                              </List.Item>
                            )}
                          />
                        </div>
                      )}

                      {normalizedWorkflowOutput.gaps.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                            {t('task.resultField.gaps')}
                          </div>
                          <List
                            size="small"
                            split={false}
                            dataSource={normalizedWorkflowOutput.gaps}
                            renderItem={(item) => (
                              <List.Item style={{ padding: '2px 0' }}>
                                <MarkdownContent content={item} />
                              </List.Item>
                            )}
                          />
                        </div>
                      )}

                      {normalizedWorkflowOutput.contradictions.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                            {t('task.resultField.contradictions')}
                          </div>
                          <List
                            size="small"
                            split={false}
                            dataSource={normalizedWorkflowOutput.contradictions}
                            renderItem={(item) => (
                              <List.Item style={{ padding: '2px 0' }}>
                                <MarkdownContent content={item} />
                              </List.Item>
                            )}
                          />
                        </div>
                      )}

                      {normalizedWorkflowOutput.validationNotes.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                            {t('task.validationNeedsReview')}
                          </div>
                          <List
                            size="small"
                            split={false}
                            dataSource={normalizedWorkflowOutput.validationNotes}
                            renderItem={(item) => (
                              <List.Item style={{ padding: '2px 0' }}>
                                <MarkdownContent content={item} />
                              </List.Item>
                            )}
                          />
                        </div>
                      )}

                      {normalizedWorkflowOutput.rawSections.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                          {normalizedWorkflowOutput.rawSections.map((section) => (
                            <div
                              key={section.key}
                              style={{
                                padding: '12px 14px',
                                border: `1px solid ${token.colorBorderSecondary}`,
                                borderRadius: token.borderRadius,
                                background: token.colorFillQuaternary,
                              }}
                            >
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {section.key}
                              </div>
                              <MarkdownContent content={section.value} />
                            </div>
                          ))}
                        </div>
                      )}

                    </div>
                  ) : msg.role === 'assistant' && msg.agentRun ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        <Tag color="blue">{t('agent.resultTag')}</Tag>
                        <Tag>{t(getAgentDefinition(msg.agentRun.agent_name).labelKey)}</Tag>
                      </div>

                      {msg.agentRun.agent_name === 'literature_synthesizer' && (
                        <>
                          {normalizedAgentOutput && normalizedAgentOutput.keyPoints.length > 0 && (
                            <div>
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {t('agent.keyPoints')}
                              </div>
                              <List
                                size="small"
                                split={false}
                                dataSource={normalizedAgentOutput.keyPoints}
                                renderItem={(item) => (
                                  <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                                )}
                              />
                            </div>
                          )}
                          {normalizedAgentOutput && normalizedAgentOutput.contradictions.length > 0 && (
                            <div>
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {t('agent.contradictions')}
                              </div>
                              <List
                                size="small"
                                split={false}
                                dataSource={normalizedAgentOutput.contradictions}
                                renderItem={(item) => (
                                  <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                                )}
                              />
                            </div>
                          )}
                          {normalizedAgentOutput && normalizedAgentOutput.gaps.length > 0 && (
                            <div>
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {t('agent.gaps')}
                              </div>
                              <List
                                size="small"
                                split={false}
                                dataSource={normalizedAgentOutput.gaps}
                                renderItem={(item) => (
                                  <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                                )}
                              />
                            </div>
                          )}
                        </>
                      )}

                      {msg.agentRun.agent_name === 'reviewer_assistant' && (
                        <>
                          {normalizedAgentOutput && normalizedAgentOutput.actionItems.length > 0 && (
                            <div>
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {t('agent.actionItems')}
                              </div>
                              <List
                                size="small"
                                split={false}
                                dataSource={normalizedAgentOutput.actionItems}
                                renderItem={(item) => (
                                  <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                                )}
                              />
                            </div>
                          )}
                          {normalizedAgentOutput && normalizedAgentOutput.responseOutline.length > 0 && (
                            <div>
                              <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                                {t('agent.responseOutline')}
                              </div>
                              <List
                                size="small"
                                split={false}
                                dataSource={normalizedAgentOutput.responseOutline}
                                renderItem={(item) => (
                                  <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                                )}
                              />
                            </div>
                          )}
                        </>
                      )}

                      {normalizedAgentOutput && normalizedAgentOutput.validationNotes.length > 0 && (
                        <div>
                          <div style={{ fontSize: 12, color: token.colorTextSecondary, marginBottom: 6 }}>
                            {t('agent.validationNotes')}
                          </div>
                          <List
                            size="small"
                            split={false}
                            dataSource={normalizedAgentOutput.validationNotes}
                            renderItem={(item) => (
                              <List.Item style={{ padding: '2px 0' }}>{item}</List.Item>
                            )}
                          />
                        </div>
                      )}

                      {workflowCard && (
                        <div
                          style={{
                            border: `1px solid ${token.colorBorder}`,
                            borderRadius: token.borderRadiusLG,
                            padding: 12,
                            background: token.colorFillQuaternary,
                          }}
                        >
                          <div
                            style={{
                              display: 'flex',
                              flexWrap: 'wrap',
                              alignItems: 'center',
                              gap: 8,
                              marginBottom: visibleWorkflowSteps.length > 0 ? 10 : 0,
                            }}
                          >
                            <Tag color="geekblue">{t('workflow.runCardTitle')}</Tag>
                            <Tag color={getWorkflowStatusColor(workflowCard.status)}>
                              {getWorkflowStatusLabel(workflowCard.status, t)}
                            </Tag>
                            <span style={{ fontSize: 12, color: token.colorTextSecondary }}>
                              {t('workflow.stepCount', { count: workflowCard.stepCount })}
                            </span>
                          </div>
                          <div style={{ fontSize: 13, color: token.colorText, marginBottom: visibleWorkflowSteps.length > 0 ? 10 : 0 }}>
                            {t(`workflow.runSummary.${workflowCard.status}`)}
                          </div>

                          {visibleWorkflowSteps.length > 0 && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                              {visibleWorkflowSteps.map((step) => (
                                <div
                                  key={step.key}
                                  style={{
                                    borderLeft: `2px solid ${token.colorBorder}`,
                                    paddingLeft: 10,
                                  }}
                                >
                                  <div
                                    style={{
                                      display: 'flex',
                                      flexWrap: 'wrap',
                                      alignItems: 'center',
                                      gap: 8,
                                      marginBottom: 4,
                                    }}
                                  >
                                    <span style={{ fontWeight: 500 }}>{step.name}</span>
                                    <Tag color={getWorkflowStatusColor(step.status)}>
                                      {getWorkflowStatusLabel(step.status, t)}
                                    </Tag>
                                  </div>
                                  <div style={{ fontSize: 13, color: token.colorText, whiteSpace: 'pre-wrap' }}>
                                    {step.summary || t('workflow.summaryEmpty')}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {visibleWorkflowSteps.length === 0 && (
                            <div style={{ fontSize: 13, color: token.colorTextSecondary }}>
                              {t('workflow.empty')}
                            </div>
                          )}

                          {showWorkflowExpand && workflowRunId && (
                            <Button
                              type="link"
                              size="small"
                              style={{ padding: 0, marginTop: 10 }}
                              onClick={() => {
                                setExpandedWorkflowRunIds((prev) => ({
                                  ...prev,
                                  [workflowRunId]: !prev[workflowRunId],
                                }));
                              }}
                            >
                              {isWorkflowExpanded ? t('workflow.showLess') : t('workflow.showMore')}
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                      ) : null}
                      {runUsageByMessageId[msg.id] ? (
                        <div style={{ marginTop: 6, fontSize: 12, color: token.colorTextSecondary }}>
                          {t('task.runTokenUsage', {
                            tokens: formatTokenCount(
                              (runUsageByMessageId[msg.id].input_tokens || 0)
                              + (runUsageByMessageId[msg.id].output_tokens || 0),
                            ),
                          })}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </ChatMessage>
              );
            })}

            {isStreaming && !isReplacingMessage && !streamingContent && (
              <ChatMessage
                role="assistant"
                content={t('chat.thinking')}
              />
            )}

            {isStreaming && !isReplacingMessage && streamingContent && (
              <ChatMessage
                role="assistant"
                content={streamingContent}
              />
            )}

            {(isStartingSessionTask || hasActiveRun || runProgressActive) && (
              <ChatMessage
                role="assistant"
                content={t('task.sessionTaskRunning', {
                  task: selectedSessionTask?.name || t('task.workspaceTaskLabel'),
                })}
              />
            )}

            {runProgressActive && (
              <Card
                size="small"
                style={{ margin: '8px 0', background: token.colorFillQuaternary }}
              >
                <div style={{ fontSize: 12, color: token.colorTextSecondary }}>
                  <div style={{ marginBottom: runProgressLines.length > 0 ? 6 : 0 }}>
                    {t('task.runProgressTitle')}
                  </div>
                  {runProgressLines.map((line, index) => (
                    <div
                      key={`${index}-${line.slice(0, 24)}`}
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        opacity: index === runProgressLines.length - 1 ? 1 : 0.65,
                      }}
                    >
                      {line}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            <div ref={messagesEndRef} />
          </Spin>
        </ChatContainer>
      </Content>

      <Modal
        title={t('researchObject.editTitle')}
        open={!!editingResearchObject}
        onCancel={() => setEditingResearchObject(null)}
        onOk={submitResearchObjectUpdate}
        okText={t('common.save')}
        destroyOnHidden
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label={t('researchObject.title')}>
            <Input
              value={researchObjectTitleDraft}
              onChange={(event) => setResearchObjectTitleDraft(event.target.value)}
              placeholder={t('timeline.untitled')}
            />
          </Form.Item>
          <Form.Item label={t('researchObject.content')}>
            <TextArea
              value={researchObjectContentDraft}
              onChange={(event) => setResearchObjectContentDraft(event.target.value)}
              rows={6}
              placeholder={t('timeline.emptyContent')}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('agent.saveToMemoryTitle')}
        open={saveMemoryModalOpen}
        onCancel={resetSaveMemoryState}
        onOk={submitSaveAgentMemory}
        okText={t('common.save')}
        okButtonProps={{ loading: isSavingAgentMemory }}
        destroyOnHidden
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label={t('agent.memoryObjectType')}>
            <Select
              value={saveMemoryType}
              onChange={(value: 'hypothesis' | 'discussion') => setSaveMemoryType(value)}
              options={[
                { value: 'hypothesis', label: t('researchObject.typeHypothesis') },
                { value: 'discussion', label: t('researchObject.typeDiscussion') },
              ]}
            />
          </Form.Item>
          <Form.Item label={t('researchObject.title')}>
            <Input
              value={saveMemoryTitleDraft}
              onChange={(event) => setSaveMemoryTitleDraft(event.target.value)}
              placeholder={t('timeline.untitled')}
            />
          </Form.Item>
          <Form.Item label={t('researchObject.content')}>
            <TextArea
              value={saveMemoryContentDraft}
              onChange={(event) => setSaveMemoryContentDraft(event.target.value)}
              rows={6}
              placeholder={t('timeline.emptyContent')}
            />
          </Form.Item>
          <Form.Item>
            <Checkbox
              checked={saveMemoryRelationEnabled}
              onChange={(event) => setSaveMemoryRelationEnabled(event.target.checked)}
            >
              {t('agent.memoryRelationToggle')}
            </Checkbox>
          </Form.Item>
          {saveMemoryRelationEnabled && (
            <>
              <Form.Item label={t('agent.memoryRelationType')}>
                <Select
                  value={saveMemoryRelationType}
                  onChange={(value: 'supports' | 'contradicts') => setSaveMemoryRelationType(value)}
                  options={[
                    { value: 'supports', label: t('relations.supports') },
                    { value: 'contradicts', label: t('relations.contradicts') },
                  ]}
                />
              </Form.Item>
              <Form.Item label={t('agent.memoryRelationTarget')}>
                <Select
                  value={saveMemoryRelationTargetId}
                  onChange={(value: string) => setSaveMemoryRelationTargetId(value)}
                  options={researchObjects.map((item) => ({
                    value: item.id,
                    label: buildResearchObjectOptionLabel(item, t),
                  }))}
                  placeholder={t('agent.memoryRelationTarget')}
                />
              </Form.Item>
              <Form.Item label={t('agent.memoryEvidenceNote')}>
                <TextArea
                  value={saveMemoryRelationNote}
                  onChange={(event) => setSaveMemoryRelationNote(event.target.value)}
                  rows={3}
                  placeholder={t('relations.evidenceNotePlaceholder')}
                />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>

      {timelineOpen && (
        <Sider
          width={380}
          theme="light"
          breakpoint="lg"
          collapsedWidth={0}
          style={{
            padding: 16,
            overflow: 'auto',
            borderLeft: `1px solid ${token.colorBorderSecondary}`,
            background: token.colorBgLayout,
          }}
        >
          <Card
            size="small"
            title={t('memory.title')}
            extra={(
              <Button type="link" size="small" onClick={() => setTimelineOpen(false)} style={{ padding: 0 }}>
                {t('memory.hide')}
              </Button>
            )}
            styles={{ body: { paddingTop: 12 } }}
          >
            <Tabs
              size="small"
              activeKey={memoryActiveTab}
              onChange={(key) => setMemoryActiveTab(key as MemoryTabKey)}
              items={[
                {
                  key: 'timeline',
                  label: t('memory.timelineTab'),
                  children: (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {renderResearchObjectList(researchObjects, 'timeline')}
                      {activeResearchObject && renderActiveResearchObjectDetails('details')}
                      {renderTracePanel()}
                    </div>
                  ),
                },
                {
                  key: 'graph',
                  label: t('memory.graphTab'),
                  children: renderGraphTab(),
                },
                {
                  key: 'objects',
                  label: t('memory.objectsTab'),
                  children: renderObjectsByType(),
                },
              ]}
            />
          </Card>
        </Sider>
      )}
    </Layout>
  );
}
