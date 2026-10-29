import {
  ClockCircleOutlined,
  CopyOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  MessageOutlined,
  PlayCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Input,
  Layout,
  Radio,
  Result,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import TaskSidebar from '../components/tasks/TaskSidebar';
import ChatMessage from '../components/ui/ChatMessage';
import apiClient from '../services/api-client';
import type { OrchestrationRun } from '../types/orchestration';
import type { TaskDefinition } from '../types/task';
import type {
  StepRunResponse,
  WorkflowRunCreateRequest,
  WorkflowRunResponse,
  WorkflowRunSaveMemoryResponse,
} from '../types/workflow';

const { Content, Sider } = Layout;
const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

const TASK_DRAFT_STORAGE_PREFIX = 'task-draft:';
const TASK_SESSION_STORAGE_PREFIX = 'task-session:';
const TASK_RUN_STORAGE_PREFIX = 'task-run:';
const TASK_REQUEST_STORAGE_PREFIX = 'task-request:';
const TERMINAL_WORKFLOW_STATUSES = new Set(['completed', 'failed', 'cancelled']);
const PROJECT_QA_TASK_ID = 'project-qa';

interface WorkspaceRouteState {
  draftStorageKey?: string;
  hasDraft?: boolean;
  sessionId?: string;
  fromSession?: boolean;
}

interface ProjectInfo {
  id: string;
  name: string;
  description: string | null;
}

interface SessionInfo {
  id: string;
  project_id: string | null;
  title: string | null;
  task_id?: string | null;
  created_at?: string;
  message_count?: number;
}

interface MessageApiResponse {
  id: string;
  role: string;
  content: string;
  created_at: string;
  agent_run?: {
    workflow_run_id?: string | null;
  } | null;
}

interface DraftPayload {
  prompt: string;
  saved_at?: string;
}

interface RequestSnapshot {
  requestText: string;
  sessionId: string;
  runId: string;
  saved_at?: string;
}

function parseDraftPayload(raw: string | null): DraftPayload | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as DraftPayload;
    if (typeof parsed.prompt !== 'string') {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function parseRequestSnapshot(raw: string | null): RequestSnapshot | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as RequestSnapshot;
    if (
      typeof parsed.requestText !== 'string'
      || typeof parsed.sessionId !== 'string'
      || typeof parsed.runId !== 'string'
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
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

function summarizeTaskPolicy(value: Record<string, unknown>, emptyLabel: string): string {
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== '');
  if (entries.length === 0) {
    return emptyLabel;
  }

  return entries
    .slice(0, 3)
    .map(([key, item]) => `${key}: ${Array.isArray(item) ? item.join(', ') : String(item)}`)
    .join(' | ');
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

function buildWorkflowInputPayload(
  task: TaskDefinition,
  requestText: string,
  locale: string,
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
      payload[key] = [];
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

  if (!('source_ids' in payload) && candidateKeys.includes('source_ids')) {
    payload.source_ids = [];
  }

  if (Object.keys(payload).length === 1 && payload.locale) {
    payload.prompt = requestText;
  }

  return payload;
}

function normalizeWorkflowStepName(step: StepRunResponse, t: (key: string) => string): string {
  const rawName = typeof step.output_payload.name === 'string' ? step.output_payload.name.trim() : '';
  const candidateName = rawName || step.step_id;
  const localized = t(`workflow.stepName.${candidateName}`);
  return localized === `workflow.stepName.${candidateName}` ? candidateName : localized;
}

function normalizeWorkflowStepSummary(step: StepRunResponse): string {
  return typeof step.output_payload.summary === 'string'
    ? step.output_payload.summary.trim()
    : '';
}

function getWorkflowStatusColor(status: string): 'default' | 'success' | 'processing' | 'error' | 'warning' {
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

function isTaskRunTerminal(status: string | undefined): boolean {
  return status ? TERMINAL_WORKFLOW_STATUSES.has(status) : false;
}

function toProjectQaWorkspaceRun(run: OrchestrationRun): WorkflowRunResponse {
  return {
    id: run.id,
    workflow_id: PROJECT_QA_TASK_ID,
    workflow_version: 1,
    session_id: run.session_id,
    status: run.status === 'waiting_for_approval'
      ? 'waiting_for_checkpoint'
      : run.status === 'planning'
        ? 'running'
        : run.status,
    input_payload: {},
    output_payload: {},
    error_message: run.error_message,
    created_by_type: 'human',
    created_at: run.created_at,
    updated_at: run.updated_at,
  };
}

function sanitizeFilename(value: string): string {
  const normalized = value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

  return normalized || 'research-note';
}

function formatWorkflowOutputValue(value: unknown, t: (key: string) => string): string {
  if (typeof value === 'string') {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => formatWorkflowOutputValue(item, t))
      .filter(Boolean)
      .map((item) => `- ${item}`)
      .join('\n');
  }

  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const formatted = formatWorkflowOutputValue(item, t);
        if (!formatted) {
          return '';
        }
        const label = t(`task.resultField.${key}`);
        return `${label === `task.resultField.${key}` ? key : label}: ${formatted}`;
      })
      .filter(Boolean)
      .join('\n');
  }

  if (value === null || value === undefined) {
    return '';
  }

  return String(value);
}

function formatWorkflowOutputForDisplay(
  output: Record<string, unknown> | undefined,
  t: (key: string) => string,
): string {
  if (!output || Object.keys(output).length === 0) {
    return '';
  }

  const preferredKeys = [
    'overview',
    'summary',
    'draft',
    'key_points',
    'contradictions',
    'gaps',
    'raw_synthesis',
  ];
  const sections = preferredKeys
    .map((key) => {
      const formatted = formatWorkflowOutputValue(output[key], t);
      if (!formatted) {
        return '';
      }
      if (['overview', 'summary', 'draft', 'raw_synthesis'].includes(key)) {
        return formatted;
      }
      const label = t(`task.resultField.${key}`);
      return `${label === `task.resultField.${key}` ? key : label}\n${formatted}`;
    })
    .filter(Boolean);

  if (sections.length > 0) {
    return sections.join('\n\n');
  }

  return Object.entries(output)
    .filter(([key]) => !['agent', 'citations', 'validation'].includes(key))
    .map(([key, value]) => {
      const formatted = formatWorkflowOutputValue(value, t);
      if (!formatted) {
        return '';
      }
      const label = t(`task.resultField.${key}`);
      return `${label === `task.resultField.${key}` ? key : label}\n${formatted}`;
    })
    .filter(Boolean)
    .join('\n\n');
}

function formatWorkflowValidationForDisplay(
  output: Record<string, unknown> | undefined,
  t: (key: string) => string,
): { isValid: boolean | null; detail: string } | null {
  const validation = output?.validation;
  if (!validation || typeof validation !== 'object' || Array.isArray(validation)) {
    return null;
  }

  const payload = validation as Record<string, unknown>;
  const isValid = typeof payload.is_valid === 'boolean' ? payload.is_valid : null;
  const detail = formatWorkflowOutputValue(payload, t);
  if (!detail) {
    return null;
  }

  return { isValid, detail };
}

export default function TaskWorkspace() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { projectId, taskId } = useParams<{ projectId: string; taskId: string }>();
  const routeState = (location.state as WorkspaceRouteState | null) ?? null;

  const [pageLoading, setPageLoading] = useState(true);
  const [task, setTask] = useState<TaskDefinition | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [messages, setMessages] = useState<MessageApiResponse[]>([]);
  const [requestDraft, setRequestDraft] = useState('');
  const [followUpDraft, setFollowUpDraft] = useState('');
  const [submittedRequest, setSubmittedRequest] = useState('');
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRunResponse | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRunResponse[]>([]);
  const [workflowSteps, setWorkflowSteps] = useState<StepRunResponse[]>([]);
  const [isStartingRun, setIsStartingRun] = useState(false);
  const [isSavingMemory, setIsSavingMemory] = useState(false);
  const [memoryObjectId, setMemoryObjectId] = useState<string | null>(null);
  const [memorySaveType, setMemorySaveType] = useState<'discussion' | 'hypothesis'>('discussion');
  const [memoryTitleDraft, setMemoryTitleDraft] = useState('');
  const [sessionEnsuring, setSessionEnsuring] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const sessionMessagesLoadedRef = useRef(false);

  const derivedDraftStorageKey = projectId && taskId
    ? `${TASK_DRAFT_STORAGE_PREFIX}${projectId}:${taskId}`
    : null;
  const draftStorageKey = routeState?.draftStorageKey || derivedDraftStorageKey;
  const routeSessionId = routeState?.sessionId || null;
  const sessionStorageKey = projectId && taskId
    ? `${TASK_SESSION_STORAGE_PREFIX}${projectId}:${taskId}`
    : null;
  const runStorageKey = projectId && taskId
    ? `${TASK_RUN_STORAGE_PREFIX}${projectId}:${taskId}`
    : null;
  const requestStorageKey = projectId && taskId
    ? `${TASK_REQUEST_STORAGE_PREFIX}${projectId}:${taskId}`
    : null;
  const ensureSessionPromiseRef = useRef<Promise<SessionInfo> | null>(null);
  const startInFlightRef = useRef(false);
  const sessionInfoRef = useRef<SessionInfo | null>(null);
  const activeRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    sessionInfoRef.current = sessionInfo;
  }, [sessionInfo]);

  useEffect(() => {
    activeRunIdRef.current = workflowRun?.id || null;
  }, [workflowRun?.id]);

  const persistRequestSnapshot = useCallback((snapshot: RequestSnapshot | null) => {
    if (!requestStorageKey) {
      return;
    }

    if (!snapshot) {
      sessionStorage.removeItem(requestStorageKey);
      return;
    }

    sessionStorage.setItem(requestStorageKey, JSON.stringify({
      ...snapshot,
      saved_at: new Date().toISOString(),
    }));
  }, [requestStorageKey]);

  const loadMessages = useCallback(async (targetSessionId: string) => {
    const { data } = await apiClient.get<MessageApiResponse[]>(`/sessions/${targetSessionId}/messages`);
    if (sessionInfoRef.current?.id !== targetSessionId) {
      return data;
    }
    setMessages(data);
    sessionMessagesLoadedRef.current = true;
    return data;
  }, []);

  const ensureSession = useCallback(async (sessionTitle: string): Promise<SessionInfo> => {
    const existingSession = sessionInfoRef.current;
    if (
      existingSession
      && existingSession.project_id === projectId
      && (taskId !== PROJECT_QA_TASK_ID || existingSession.task_id === PROJECT_QA_TASK_ID)
    ) {
      return existingSession;
    }

    if (ensureSessionPromiseRef.current) {
      return ensureSessionPromiseRef.current;
    }

    const promise = (async () => {
      setSessionEnsuring(true);

      if (routeSessionId) {
        try {
          const sessionResponse = await apiClient.get<SessionInfo>(`/sessions/${routeSessionId}`);
          if (
            sessionResponse.data.project_id === projectId
            && (taskId !== PROJECT_QA_TASK_ID || sessionResponse.data.task_id === PROJECT_QA_TASK_ID)
          ) {
            setSessionInfo(sessionResponse.data);
            if (sessionStorageKey) {
              sessionStorage.setItem(sessionStorageKey, sessionResponse.data.id);
            }
            return sessionResponse.data;
          }
        } catch {
          // Ignore invalid route state and continue with the regular task session lookup.
        }
      }

      const storedSessionId = sessionStorageKey ? sessionStorage.getItem(sessionStorageKey) : null;
      if (storedSessionId) {
        try {
          const sessionResponse = await apiClient.get<SessionInfo>(`/sessions/${storedSessionId}`);
          if (
            sessionResponse.data.project_id === projectId
            && (taskId !== PROJECT_QA_TASK_ID || sessionResponse.data.task_id === PROJECT_QA_TASK_ID)
          ) {
            setSessionInfo(sessionResponse.data);
            return sessionResponse.data;
          }
        } catch {
          // Ignore and create a new session below.
        }

        if (sessionStorageKey) {
          sessionStorage.removeItem(sessionStorageKey);
        }
      }

      const sessionResponse = await apiClient.post<SessionInfo>('/sessions', {
        project_id: projectId,
        title: sessionTitle,
        ...(taskId === PROJECT_QA_TASK_ID ? { task_id: taskId } : {}),
      });
      setSessionInfo(sessionResponse.data);
      if (sessionStorageKey) {
        sessionStorage.setItem(sessionStorageKey, sessionResponse.data.id);
      }
      return sessionResponse.data;
    })().finally(() => {
      ensureSessionPromiseRef.current = null;
      setSessionEnsuring(false);
    });

    ensureSessionPromiseRef.current = promise;
    return promise;
  }, [projectId, routeSessionId, sessionStorageKey, taskId]);

  useEffect(() => {
    if (!projectId || !taskId) {
      setLoadError(t('task.workspaceInvalidRoute'));
      setPageLoading(false);
      return;
    }

    let cancelled = false;

    const initialize = async () => {
      setPageLoading(true);
      setLoadError(null);

      if (draftStorageKey) {
        const savedDraft = parseDraftPayload(sessionStorage.getItem(draftStorageKey));
        if (savedDraft?.prompt) {
          setRequestDraft(savedDraft.prompt);
          setDraftSavedAt(savedDraft.saved_at || null);
        } else if (routeState?.hasDraft) {
          setDraftSavedAt(null);
        }
      }

      try {
        const [taskResponse, projectResponse] = await Promise.all([
          apiClient.get<TaskDefinition>(`/tasks/${taskId}`, { params: { project_id: projectId } }),
          apiClient.get<ProjectInfo>(`/projects/${projectId}`),
        ]);

        if (cancelled) {
          return;
        }

        setTask(taskResponse.data);
        setProject(projectResponse.data);

        const nextSession = await ensureSession(taskResponse.data.name);
        if (cancelled) {
          return;
        }
        setSessionInfo(nextSession);
        await loadMessages(nextSession.id);

        const storedSnapshot = parseRequestSnapshot(
          requestStorageKey ? sessionStorage.getItem(requestStorageKey) : null,
        );
        if (storedSnapshot?.sessionId === nextSession.id) {
          setSubmittedRequest(storedSnapshot.requestText);
        }

        const storedRunId = (
          storedSnapshot?.sessionId === nextSession.id
            ? storedSnapshot.runId
            : (runStorageKey ? sessionStorage.getItem(runStorageKey) : null)
        );
        let loadedStoredRun = false;
        const isProjectQa = taskResponse.data.id === PROJECT_QA_TASK_ID;
        if (storedRunId) {
          try {
            if (isProjectQa) {
              const { data: run } = await apiClient.get<OrchestrationRun>(`/orchestration-runs/${storedRunId}`);
              if (!cancelled && run.session_id === nextSession.id && run.task_id === PROJECT_QA_TASK_ID) {
                const workspaceRun = toProjectQaWorkspaceRun(run);
                setWorkflowRun(workspaceRun);
                setWorkflowSteps([]);
                activeRunIdRef.current = run.id;
                loadedStoredRun = true;
              }
            } else {
              const [runResponse, stepsResponse] = await Promise.all([
                apiClient.get<WorkflowRunResponse>(`/workflow-runs/${storedRunId}`),
                apiClient.get<StepRunResponse[]>(`/workflow-runs/${storedRunId}/steps`),
              ]);
              if (!cancelled && runResponse.data.session_id === nextSession.id) {
                setWorkflowRun(runResponse.data);
                setWorkflowSteps(stepsResponse.data);
                activeRunIdRef.current = runResponse.data.id;
                loadedStoredRun = true;
              }
            }
            if (!loadedStoredRun) {
              if (runStorageKey) {
                sessionStorage.removeItem(runStorageKey);
              }
              persistRequestSnapshot(null);
            }
          } catch {
            if (runStorageKey) {
              sessionStorage.removeItem(runStorageKey);
            }
            persistRequestSnapshot(null);
          }
        }

        try {
          const sessionRunsResponse = isProjectQa
            ? await apiClient.get<OrchestrationRun[]>(`/sessions/${nextSession.id}/orchestration-runs`)
            : await apiClient.get<WorkflowRunResponse[]>(`/sessions/${nextSession.id}/workflow-runs`);
          const taskRuns = isProjectQa
            ? (sessionRunsResponse.data as OrchestrationRun[])
              .filter((item) => item.task_id === PROJECT_QA_TASK_ID)
              .map(toProjectQaWorkspaceRun)
            : (sessionRunsResponse.data as WorkflowRunResponse[])
              .filter((item) => item.workflow_id === taskResponse.data.workflow_id);
          const latestRun = taskRuns[0];
          if (!cancelled) {
            setWorkflowRuns(taskRuns);
          }
          if (!loadedStoredRun && latestRun && !cancelled) {
            setWorkflowRun(latestRun);
            setWorkflowSteps([]);
            activeRunIdRef.current = latestRun.id;
            if (!isProjectQa) {
              const { data: steps } = await apiClient.get<StepRunResponse[]>(
                `/workflow-runs/${latestRun.id}/steps`,
              );
              setWorkflowSteps(steps);
            }
            if (runStorageKey) {
              sessionStorage.setItem(runStorageKey, latestRun.id);
            }
          }
        } catch {
          // The task workspace can still start a new run without historical runs.
        }
      } catch (error) {
        if (!cancelled) {
          const detail =
            typeof error === 'object' &&
            error !== null &&
            'response' in error &&
            typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
              ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
              : null;
          setLoadError(detail || t('task.workspaceLoadFailed'));
        }
      } finally {
        if (!cancelled) {
          setSessionEnsuring(false);
          setPageLoading(false);
        }
      }
    };

    void initialize();

    return () => {
      cancelled = true;
    };
  }, [draftStorageKey, ensureSession, loadMessages, persistRequestSnapshot, projectId, requestStorageKey, runStorageKey, t, taskId]);

  useEffect(() => {
    if (!draftStorageKey) {
      return;
    }

    const trimmedDraft = requestDraft.trim();
    if (!trimmedDraft || submittedRequest.trim()) {
      sessionStorage.removeItem(draftStorageKey);
      if (!trimmedDraft) {
        setDraftSavedAt(null);
      }
      return;
    }

    sessionStorage.setItem(draftStorageKey, JSON.stringify({
      prompt: trimmedDraft,
      saved_at: new Date().toISOString(),
    }));
  }, [draftStorageKey, requestDraft, submittedRequest]);

  useEffect(() => {
    if (!workflowRun?.id || isTaskRunTerminal(workflowRun.status) || !sessionInfo?.id) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;

    const poll = async () => {
      const currentRunId = workflowRun.id;
      const currentSessionId = sessionInfo.id;

      try {
        const isProjectQa = task?.id === PROJECT_QA_TASK_ID;
        const [runResponse, stepsResponse, messagesResponse, sessionResponse] = await Promise.all([
          isProjectQa
            ? apiClient.get<OrchestrationRun>(`/orchestration-runs/${currentRunId}`)
            : apiClient.get<WorkflowRunResponse>(`/workflow-runs/${currentRunId}`),
          isProjectQa
            ? Promise.resolve({ data: [] as StepRunResponse[] })
            : apiClient.get<StepRunResponse[]>(`/workflow-runs/${currentRunId}/steps`),
          apiClient.get<MessageApiResponse[]>(`/sessions/${currentSessionId}/messages`),
          apiClient.get<SessionInfo>(`/sessions/${currentSessionId}`),
        ]);
        const updatedRun = isProjectQa
          ? toProjectQaWorkspaceRun(runResponse.data as OrchestrationRun)
          : runResponse.data as WorkflowRunResponse;

        if (
          cancelled
          || activeRunIdRef.current !== currentRunId
          || updatedRun.session_id !== currentSessionId
          || sessionInfoRef.current?.id !== currentSessionId
        ) {
          return;
        }

        setWorkflowRun(updatedRun);
        setWorkflowRuns((prev) => prev.map((item) => (
          item.id === updatedRun.id ? updatedRun : item
        )));
        setWorkflowSteps(stepsResponse.data);
        setMessages(messagesResponse.data);
        setSessionInfo(sessionResponse.data);

        if (!isTaskRunTerminal(updatedRun.status)) {
          timeoutId = window.setTimeout(poll, 2000);
        }
      } catch {
        if (!cancelled && activeRunIdRef.current === currentRunId) {
          timeoutId = window.setTimeout(poll, 2000);
        }
      }
    };

    timeoutId = window.setTimeout(poll, 2000);

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [sessionInfo?.id, task?.id, workflowRun?.id, workflowRun?.status]);

  useEffect(() => {
    if (!workflowRun?.id || !isTaskRunTerminal(workflowRun.status) || !sessionInfo?.id) {
      return;
    }

    void Promise.all([
      apiClient.get<MessageApiResponse[]>(`/sessions/${sessionInfo.id}/messages`),
      apiClient.get<SessionInfo>(`/sessions/${sessionInfo.id}`),
    ]).then(([messagesResponse, sessionResponse]) => {
      if (
        activeRunIdRef.current === workflowRun.id
        && sessionInfoRef.current?.id === sessionInfo.id
      ) {
        setMessages(messagesResponse.data);
        setSessionInfo(sessionResponse.data);
      }
    }).catch(() => {});
  }, [sessionInfo?.id, workflowRun?.id, workflowRun?.status]);

  const handleStartTask = async (requestOverride?: string) => {
    if (startInFlightRef.current) {
      return;
    }

    const trimmedRequest = (requestOverride ?? requestDraft).trim();

    if (!trimmedRequest) {
      message.warning(t('task.promptRequired'));
      return;
    }

    if (!task || !projectId) {
      return;
    }

    startInFlightRef.current = true;
    setIsStartingRun(true);

    try {
      const activeSession = await ensureSession(task.name);
      const isProjectQa = task.id === PROJECT_QA_TASK_ID;
      const payload: WorkflowRunCreateRequest = {
        session_id: activeSession.id,
        input: buildWorkflowInputPayload(task, trimmedRequest, i18n.language),
      };

      let syncWarningShown = false;
      const showSyncWarning = (warningType: 'message' | 'general') => {
        if (syncWarningShown) {
          return;
        }
        syncWarningShown = true;
        message.warning(
          warningType === 'message'
            ? t('task.workspaceMessageSyncWarning')
            : t('task.workspaceSyncDelayed'),
        );
      };

      if (!isProjectQa) {
        try {
          await apiClient.post(`/sessions/${activeSession.id}/messages`, {
            content: trimmedRequest,
          });
        } catch {
          showSyncWarning('message');
        }
      }

      const createdRunResponse = isProjectQa
        ? await apiClient.post<OrchestrationRun>(
          `/sessions/${activeSession.id}/orchestration-runs/project-qa`,
          { goal: trimmedRequest },
        )
        : await apiClient.post<WorkflowRunResponse>(`/workflows/${task.workflow_id}/run`, payload);
      const createdRun = isProjectQa
        ? toProjectQaWorkspaceRun(createdRunResponse.data as OrchestrationRun)
        : createdRunResponse.data as WorkflowRunResponse;
      activeRunIdRef.current = createdRun.id;
      setSubmittedRequest(trimmedRequest);
      setWorkflowRun(createdRun);
      setWorkflowRuns((prev) => [createdRun, ...prev.filter((item) => item.id !== createdRun.id)]);
      setWorkflowSteps([]);
      setSessionInfo(activeSession);
      persistRequestSnapshot({
        requestText: trimmedRequest,
        sessionId: activeSession.id,
        runId: createdRun.id,
      });
      if (runStorageKey) {
        sessionStorage.setItem(runStorageKey, createdRun.id);
      }
      if (draftStorageKey) {
        sessionStorage.removeItem(draftStorageKey);
      }
      setRequestDraft('');
      setDraftSavedAt(null);
      message.success(t('task.workspaceRunStarted'));

      try {
        const [stepsResponse, sessionResponse] = await Promise.all([
          isProjectQa
            ? Promise.resolve({ data: [] as StepRunResponse[] })
            : apiClient.get<StepRunResponse[]>(`/workflow-runs/${createdRun.id}/steps`),
          apiClient.get<SessionInfo>(`/sessions/${activeSession.id}`),
        ]);

        if (activeRunIdRef.current === createdRun.id) {
          setWorkflowSteps(stepsResponse.data);
          setSessionInfo(sessionResponse.data);
        }
      } catch {
        showSyncWarning('general');
      }

      try {
        await loadMessages(activeSession.id);
      } catch {
        showSyncWarning('general');
      }
    } catch (error) {
      const detail =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      message.error(detail || t('task.workspaceRunFailed'));
    } finally {
      startInFlightRef.current = false;
      setIsStartingRun(false);
    }
  };

  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant' && item.content.trim()),
    [messages],
  );
  const visibleTaskMessages = useMemo(
    () => messages.filter((item) => item.role !== 'assistant'),
    [messages],
  );
  const structuredResultContent = useMemo(
    () => formatWorkflowOutputForDisplay(workflowRun?.output_payload, t),
    [t, workflowRun?.output_payload],
  );
  const validationDetail = useMemo(
    () => formatWorkflowValidationForDisplay(workflowRun?.output_payload, t),
    [t, workflowRun?.output_payload],
  );
  const latestResultContent = useMemo(() => (
    structuredResultContent
    || latestAssistantMessage?.content.trim()
    || ''
  ), [latestAssistantMessage?.content, structuredResultContent]);
  const runtimeLabel = useMemo(() => {
    if (workflowSteps.some((step) => step.output_payload?.runtime === 'codex')) {
      return t('task.runtimeCodex');
    }
    if (workflowRun) {
      return t('task.runtimePlatform');
    }
    return t('task.runtimePending');
  }, [t, workflowRun, workflowSteps]);

  const defaultMemoryTitle = useMemo(() => {
    const requestText = submittedRequest.trim();
    const requestSuffix = requestText
      ? ` - ${requestText.length > 48 ? `${requestText.slice(0, 48).trimEnd()}...` : requestText}`
      : '';
    return `${task?.name || t('task.workspaceTaskLabel')}${requestSuffix}`;
  }, [submittedRequest, task?.name, t]);

  useEffect(() => {
    if (!memoryTitleDraft.trim()) {
      setMemoryTitleDraft(defaultMemoryTitle);
    }
  }, [defaultMemoryTitle, memoryTitleDraft]);

  const buildMarkdownReport = useCallback(() => {
    const generatedAt = new Date().toLocaleString(i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US');
    const requestText = submittedRequest.trim() || requestDraft.trim() || t('task.workspaceRequestSummaryEmpty');
    const resultText = latestResultContent || t('task.workspaceMessagesEmpty');
    const stepLines = workflowSteps.length > 0
      ? workflowSteps.map((step) => {
        const name = normalizeWorkflowStepName(step, t);
        const status = t(`workflow.status.${step.status}`);
        const summary = normalizeWorkflowStepSummary(step) || t('workflow.summaryEmpty');
        return `- ${name} (${status}): ${summary}`;
      }).join('\n')
      : `- ${t('task.workspaceStepsEmpty')}`;

    return [
      `# ${task?.name || t('task.workspaceTaskLabel')}`,
      '',
      `- ${t('task.projectContextLabel')}: ${project?.name || ''}`,
      `- ${t('task.workspaceTaskLabel')}: ${task?.name || ''}`,
      `- ${t('task.workspaceRunLabel')}: ${workflowRun?.id || ''}`,
      `- ${t('task.reportGeneratedAt')}: ${generatedAt}`,
      '',
      `## ${t('task.workspaceRequestTitle')}`,
      '',
      requestText,
      '',
      `## ${t('task.workspaceResultsTitle')}`,
      '',
      resultText,
      '',
      `## ${t('task.workspaceStepsTitle')}`,
      '',
      stepLines,
      '',
    ].join('\n');
  }, [
    i18n.language,
    latestResultContent,
    project?.name,
    requestDraft,
    submittedRequest,
    t,
    task?.name,
    workflowRun?.id,
    workflowSteps,
  ]);

  const handleSaveToMemory = async () => {
    if (!workflowRun?.id || workflowRun.status !== 'completed' || !latestResultContent) {
      message.warning(t('task.deliverySaveUnavailable'));
      return;
    }

    const title = memoryTitleDraft.trim() || defaultMemoryTitle;
    setIsSavingMemory(true);

    try {
      const { data } = await apiClient.post<WorkflowRunSaveMemoryResponse>(
        `/workflow-runs/${workflowRun.id}/save-memory`,
        {
          type: memorySaveType,
          title,
          content: latestResultContent,
          relation: {
            enabled: false,
          },
        },
      );
      setMemoryObjectId(data.research_object.id);
      message.success(t('task.deliverySaveSuccess'));
    } catch (error) {
      const detail =
        typeof error === 'object' &&
        error !== null &&
        'response' in error &&
        typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
          ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      message.error(detail || t('task.deliverySaveFailed'));
    } finally {
      setIsSavingMemory(false);
    }
  };

  const handleCopyMarkdown = async () => {
    const markdown = buildMarkdownReport();
    try {
      await navigator.clipboard.writeText(markdown);
      message.success(t('task.deliveryCopySuccess'));
    } catch {
      message.error(t('task.deliveryCopyFailed'));
    }
  };

  const handleDownloadMarkdown = () => {
    const markdown = buildMarkdownReport();
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${sanitizeFilename(task?.name || 'research-note')}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    message.success(t('task.deliveryDownloadSuccess'));
  };

  const stepItems = workflowSteps.map((step) => ({
    key: step.id,
    color: getWorkflowStatusColor(step.status) === 'success'
      ? 'green'
      : getWorkflowStatusColor(step.status) === 'error'
        ? 'red'
        : getWorkflowStatusColor(step.status) === 'warning'
          ? 'orange'
          : 'blue',
    children: (
      <Space orientation="vertical" size={2}>
        <Space size={8} wrap>
          <Text strong>{normalizeWorkflowStepName(step, t)}</Text>
          <Tag color={getWorkflowStatusColor(step.status)}>
            {t(`workflow.status.${step.status}`)}
          </Tag>
        </Space>
        <Text type="secondary">
          {normalizeWorkflowStepSummary(step) || t('workflow.summaryEmpty')}
        </Text>
      </Space>
    ),
  }));

  if (pageLoading) {
    return <Spin size="large" style={{ display: 'block', margin: '120px auto' }} />;
  }

  if (loadError || !projectId || !taskId || !task || !project) {
    return (
      <div style={{ padding: 24 }}>
        <Result
          status="error"
          title={t('task.workspaceUnavailable')}
          subTitle={loadError || t('task.workspaceInvalidRoute')}
          extra={(
            <Button type="primary" onClick={() => navigate('/')}>
              {t('common.back')}
            </Button>
          )}
        />
      </div>
    );
  }

  const hasInitialRequest = submittedRequest.trim().length > 0;
  const hasStartedTask = hasInitialRequest;
  const activeRequestText = submittedRequest.trim() || requestDraft.trim();
  const requiredInputKeys = getRequiredInputKeys(task.input_schema);
  const workflowStatusLabel = workflowRun ? t(`workflow.status.${workflowRun.status}`) : null;
  const workflowStatusColor = workflowRun ? getWorkflowStatusColor(workflowRun.status) : undefined;
  const formattedDraftSavedAt = draftSavedAt
    ? new Date(draftSavedAt).toLocaleString(i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US')
    : null;
  const requestSummary = activeRequestText
    ? activeRequestText.length > 140
      ? `${activeRequestText.slice(0, 140).trimEnd()}...`
      : activeRequestText
    : t('task.workspaceRequestSummaryEmpty');
  const projectMaterialsSummary = summarizeTaskPolicy(
    task.project_context_policy,
    t('task.workspaceProjectMaterialsFallback'),
  );
  const outputTargetSummary = summarizeTaskPolicy(
    task.result_presentation,
    t('task.workspaceOutputTargetFallback'),
  );
  const progressDetailLabel = workflowRun
    ? t('task.workspaceProgressDetail', { steps: workflowSteps.length, messages: messages.length })
    : t('task.workspaceProgressDetailIdle');
  const canDeliverResult = task.id !== PROJECT_QA_TASK_ID
    && workflowRun?.status === 'completed'
    && Boolean(latestResultContent);
  const recentWorkflowRuns = workflowRuns.slice(0, 5);

  return (
    <Layout style={{ minHeight: '100%', background: '#f5f7fa' }}>
      <Content style={{ padding: 24 }}>
        <div style={{ maxWidth: 1360, margin: '0 auto' }}>
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Card>
              <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                <Space size={8} wrap>
                  <Tag>{project.name}</Tag>
                  <Tag color={task.project_ids.length > 0 ? 'blue' : 'default'}>
                    {task.project_ids.length > 0 ? t('task.scopeProject') : t('task.scopeGlobal')}
                  </Tag>
                  {hasStartedTask && workflowStatusLabel ? (
                    <Tag color={workflowStatusColor}>
                      {t('task.workspaceProgressBadge')}: {workflowStatusLabel}
                    </Tag>
                  ) : null}
                  {hasStartedTask ? <Tag>{runtimeLabel}</Tag> : null}
                </Space>
                <Title level={3} style={{ margin: 0 }}>
                  {task.name}
                </Title>
                <Paragraph type="secondary" style={{ margin: 0 }}>
                  {task.description}
                </Paragraph>
                {hasStartedTask ? (
                  <Text type="secondary">
                    {t('task.workspaceHeaderMeta', {
                      project: project.name,
                      session: sessionInfo?.title || task.name,
                    })}
                  </Text>
                ) : null}
              </Space>
            </Card>

            <Layout style={{ background: 'transparent', gap: 16, flexWrap: 'wrap' }}>
              <Content style={{ minWidth: 0 }}>
                <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                  <Card title={t('task.workspaceRequestTitle')}>
                    {hasInitialRequest ? (
                      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                        <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                          {submittedRequest}
                        </Paragraph>
                        <Space size={12} wrap>
                          <Button
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            onClick={() => void handleStartTask(submittedRequest)}
                            loading={isStartingRun}
                            disabled={!submittedRequest.trim()}
                          >
                            {t('task.workspaceRerunAction')}
                          </Button>
                          <Text type="secondary">{t('task.workspaceRerunHint')}</Text>
                        </Space>
                      </Space>
                    ) : (
                      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                          {t('task.workspaceRequestDescription')}
                        </Paragraph>
                        <TextArea
                          value={requestDraft}
                          onChange={(event) => {
                            setRequestDraft(event.target.value);
                            setDraftSavedAt(new Date().toISOString());
                          }}
                          placeholder={t('task.composerPlaceholder')}
                          autoSize={{ minRows: 4, maxRows: 8 }}
                          onPressEnter={(event) => {
                            if ((event.ctrlKey || event.metaKey) && !event.shiftKey) {
                              event.preventDefault();
                              void handleStartTask();
                            }
                          }}
                        />
                        <Space size={12} wrap>
                          <Button
                            type="primary"
                            icon={<PlayCircleOutlined />}
                            onClick={() => void handleStartTask()}
                            loading={isStartingRun}
                          >
                            {t('task.workspaceStartAction')}
                          </Button>
                          <Text type="secondary">{t('task.hotkeyHint')}</Text>
                        </Space>
                      </Space>
                    )}
                  </Card>

                  {hasStartedTask ? (
                    <Card title={t('task.workspaceStatusTitle')}>
                      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                        <Space size={12} wrap>
                          <Tag icon={<ClockCircleOutlined />} color={workflowStatusColor}>
                            {workflowStatusLabel || t('task.workspaceStatusIdle')}
                          </Tag>
                          <Tag icon={<ExperimentOutlined />}>
                            {t('task.workspaceStepCount', { count: workflowSteps.length })}
                          </Tag>
                          <Tag icon={<MessageOutlined />}>
                            {t('task.workspaceMessageCount', { count: messages.length })}
                          </Tag>
                        </Space>

                        {sessionEnsuring ? (
                          <Alert type="info" showIcon message={t('task.workspaceSessionPreparing')} />
                        ) : null}
                        {workflowRun?.status === 'failed' && workflowRun.error_message ? (
                          <Alert type="error" showIcon message={workflowRun.error_message} />
                        ) : null}
                        {workflowRun?.status === 'waiting_for_checkpoint' ? (
                          <Alert type="warning" showIcon message={t('task.workspaceCheckpointHint')} />
                        ) : null}
                        <Alert
                          type="info"
                          showIcon
                          message={t('task.workspaceProjectContextActive')}
                          description={t('task.workspaceProjectContextDescription')}
                        />
                      </Space>
                    </Card>
                  ) : null}

                  {hasStartedTask ? (
                    <Card title={t('task.workspaceResultsTitle')}>
                    <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                      {latestResultContent ? (
                        <Card size="small" styles={{ body: { padding: 16 } }}>
                          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                            <Text strong>{t('task.workspaceLatestResult')}</Text>
                            <Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                              {latestResultContent}
                            </Paragraph>
                            {validationDetail ? (
                              <Collapse
                                ghost
                                size="small"
                                items={[
                                  {
                                    key: 'validation',
                                    label: validationDetail.isValid === false
                                      ? t('task.validationNeedsReview')
                                      : t('task.validationDetails'),
                                    children: (
                                      <Paragraph
                                        type="secondary"
                                        style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}
                                      >
                                        {validationDetail.detail}
                                      </Paragraph>
                                    ),
                                  },
                                ]}
                              />
                            ) : null}
                          </Space>
                        </Card>
                      ) : null}

                      {visibleTaskMessages.length > 0 ? (
                        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                          {visibleTaskMessages.map((item) => (
                            <ChatMessage
                              key={item.id}
                              id={`task-message-${item.id}`}
                              role={item.role === 'assistant' ? 'assistant' : 'user'}
                              content={item.content}
                              renderMarkdown={item.role === 'assistant'}
                              timestamp={new Date(item.created_at).toLocaleString(
                                i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US',
                              )}
                            />
                          ))}
                        </Space>
                      ) : (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={(
                            <Text type="secondary">
                              {sessionMessagesLoadedRef.current
                                ? t('task.workspaceMessagesEmpty')
                                : t('task.workspaceMessagesLoading')}
                            </Text>
                          )}
                        />
                      )}
                    </Space>
                    </Card>
                  ) : null}

                  {hasStartedTask ? (
                    <Card title={t('task.deliveryTitle')}>
                      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                          {t('task.deliveryDescription')}
                        </Paragraph>

                        {!canDeliverResult ? (
                          <Alert type="info" showIcon message={t('task.deliveryPendingHint')} />
                        ) : null}

                        {memoryObjectId ? (
                          <Alert
                            type="success"
                            showIcon
                            message={t('task.deliverySavedTitle')}
                            description={t('task.deliverySavedDescription')}
                          />
                        ) : null}

                        {task.id !== PROJECT_QA_TASK_ID ? (
                          <Card size="small" title={t('task.deliveryMemoryTitle')}>
                            <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                              <Radio.Group
                                value={memorySaveType}
                                onChange={(event) => setMemorySaveType(event.target.value)}
                                disabled={!canDeliverResult || isSavingMemory}
                                optionType="button"
                                buttonStyle="solid"
                                options={[
                                  { label: t('task.deliveryTypeDiscussion'), value: 'discussion' },
                                  { label: t('task.deliveryTypeHypothesis'), value: 'hypothesis' },
                                ]}
                              />
                              <Input
                                value={memoryTitleDraft}
                                onChange={(event) => setMemoryTitleDraft(event.target.value)}
                                disabled={!canDeliverResult || isSavingMemory}
                                placeholder={t('task.deliveryMemoryTitlePlaceholder')}
                              />
                              <Space size={12} wrap>
                                <Button
                                  type="primary"
                                  icon={<SaveOutlined />}
                                  onClick={() => void handleSaveToMemory()}
                                  loading={isSavingMemory}
                                  disabled={!canDeliverResult}
                                >
                                  {memoryObjectId ? t('task.deliverySaveAgain') : t('task.deliverySaveAction')}
                                </Button>
                                {memoryObjectId && sessionInfo?.id ? (
                                  <Button onClick={() => navigate(`/sessions/${sessionInfo.id}`)}>
                                    {t('task.deliveryOpenMemory')}
                                  </Button>
                                ) : null}
                              </Space>
                            </Space>
                          </Card>
                        ) : null}

                        <Card size="small" title={t('task.deliveryReportTitle')}>
                          <Space orientation="vertical" size={12} style={{ width: '100%' }}>
                            <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                              {t('task.deliveryReportDescription')}
                            </Paragraph>
                            <Space size={12} wrap>
                              <Button
                                icon={<CopyOutlined />}
                                onClick={() => void handleCopyMarkdown()}
                                disabled={!canDeliverResult}
                              >
                                {t('task.deliveryCopyMarkdown')}
                              </Button>
                              <Button
                                icon={<DownloadOutlined />}
                                onClick={handleDownloadMarkdown}
                                disabled={!canDeliverResult}
                              >
                                {t('task.deliveryDownloadMarkdown')}
                              </Button>
                            </Space>
                          </Space>
                        </Card>
                      </Space>
                    </Card>
                  ) : null}

                  {hasStartedTask ? (
                    <Card title={t('task.workspaceStepsTitle')}>
                      {stepItems.length > 0 ? (
                        <Timeline items={stepItems} />
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('task.workspaceStepsEmpty')} />
                      )}
                    </Card>
                  ) : null}

                  {hasStartedTask ? (
                    <Card title={t('task.runHistoryTitle')}>
                      {recentWorkflowRuns.length > 0 ? (
                        <Space orientation="vertical" size={8} style={{ width: '100%' }}>
                          {recentWorkflowRuns.map((run) => (
                            <Button
                              key={run.id}
                              block
                              type={run.id === workflowRun?.id ? 'primary' : 'default'}
                              onClick={() => {
                                activeRunIdRef.current = run.id;
                                setWorkflowRun(run);
                                if (task.id === PROJECT_QA_TASK_ID) {
                                  setWorkflowSteps([]);
                                  void apiClient.get<OrchestrationRun>(`/orchestration-runs/${run.id}`)
                                    .then((response) => {
                                      if (
                                        activeRunIdRef.current !== run.id
                                        || sessionInfoRef.current?.id !== run.session_id
                                        || task.id !== PROJECT_QA_TASK_ID
                                      ) {
                                        return;
                                      }
                                      setWorkflowRun(toProjectQaWorkspaceRun(response.data));
                                    })
                                    .catch(() => message.warning(t('task.runHistoryStepsLoadFailed')));
                                } else {
                                  void apiClient.get<StepRunResponse[]>(`/workflow-runs/${run.id}/steps`)
                                    .then((response) => setWorkflowSteps(response.data))
                                    .catch(() => message.warning(t('task.runHistoryStepsLoadFailed')));
                                }
                                if (runStorageKey) {
                                  sessionStorage.setItem(runStorageKey, run.id);
                                }
                              }}
                              style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}
                            >
                              <Space orientation="vertical" size={2} style={{ width: '100%' }}>
                                <Space size={8} wrap>
                                  <Tag color={getWorkflowStatusColor(run.status)}>
                                    {t(`workflow.status.${run.status}`)}
                                  </Tag>
                                  <Text type={run.id === workflowRun?.id ? undefined : 'secondary'}>
                                    {run.created_at
                                      ? new Date(run.created_at).toLocaleString(i18n.language === 'zh-CN' ? 'zh-CN' : 'en-US')
                                      : t('task.runHistoryTimeUnknown')}
                                  </Text>
                                </Space>
                                <Text
                                  type={run.id === workflowRun?.id ? undefined : 'secondary'}
                                  style={{ fontSize: 12 }}
                                >
                                  {t('task.runHistoryRunId', { id: run.id.slice(0, 8) })}
                                </Text>
                              </Space>
                            </Button>
                          ))}
                        </Space>
                      ) : (
                        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('task.runHistoryEmpty')} />
                      )}
                    </Card>
                  ) : null}

                  {hasStartedTask ? (
                    <Card title={hasInitialRequest ? t('task.workspaceFollowUpTitle') : t('task.workspaceNextStepTitle')}>
                      {hasInitialRequest ? (
                      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
                        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                          {t('task.workspaceFollowUpDescription')}
                        </Paragraph>
                        <TextArea
                          value={followUpDraft}
                          onChange={(event) => setFollowUpDraft(event.target.value)}
                          placeholder={t('task.workspaceFollowUpPlaceholder')}
                          autoSize={{ minRows: 3, maxRows: 6 }}
                        />
                        <Text type="secondary">{t('task.workspaceFollowUpNote')}</Text>
                        <Button
                          type="primary"
                          onClick={() => sessionInfo?.id && navigate(`/sessions/${sessionInfo.id}`)}
                          disabled={!sessionInfo?.id}
                        >
                          {t('task.workspaceOpenSession')}
                        </Button>
                      </Space>
                      ) : (
                        <Text type="secondary">{t('task.workspaceNextStepDescription')}</Text>
                      )}
                    </Card>
                  ) : null}
                </Space>
              </Content>

              <Sider
                width={320}
                theme="light"
                style={{
                  background: 'transparent',
                  flex: '0 0 320px',
                  maxWidth: '100%',
                }}
              >
                <TaskSidebar
                  projectName={project.name}
                  projectDescription={project.description}
                  taskName={task.name}
                  taskIdLabel={task.id}
                  sessionId={sessionInfo?.id || null}
                  sessionTitle={sessionInfo?.title || task.name}
                  sessionMessageCount={sessionInfo?.message_count ?? messages.length}
                  runStatusLabel={workflowStatusLabel}
                  runStatusColor={workflowStatusColor}
                  hasDraft={Boolean(requestDraft.trim()) || Boolean(draftSavedAt)}
                  draftSavedAtLabel={formattedDraftSavedAt
                    ? t('task.workspaceDraftSavedAt', { time: formattedDraftSavedAt })
                    : null}
                  sessionReady={Boolean(sessionInfo?.id)}
                  openSessionLabel={t('task.workspaceOpenSession')}
                  backLabel={t('common.back')}
                  projectLabel={t('task.projectContextLabel')}
                  projectMaterialsLabel={t('task.workspaceProjectMaterialsTitle')}
                  taskParametersLabel={t('task.workspaceTaskParametersTitle')}
                  outputTargetLabel={t('task.workspaceOutputTargetTitle')}
                  saveResultsLabel={t('task.workspaceSaveResultsTitle')}
                  fullConversationLabel={t('task.workspaceFullConversationTitle')}
                  requestSummaryLabel={t('task.workspaceRequestSummaryLabel')}
                  requiredInputsLabel={t('task.workspaceRequiredInputsLabel')}
                  inputRequiredNoneLabel={t('task.workspaceInputRequiredNone')}
                  taskNameLabel={t('task.workspaceTaskLabel')}
                  taskIdTextLabel={t('task.workspaceTaskIdLabel')}
                  runLabel={t('task.workspaceRunLabel')}
                  progressDetailLabel={progressDetailLabel}
                  draftSavedLabel={t('task.workspaceDraftReady')}
                  draftEmptyLabel={t('task.workspaceDraftEmpty')}
                  sessionPendingLabel={t('task.workspaceSessionPreparingShort')}
                  projectHint={t('task.workspaceSidebarProjectHint')}
                  projectMaterialsSummary={projectMaterialsSummary}
                  projectMaterialsHint={t('task.workspaceSidebarMaterialsHint')}
                  requestSummary={requestSummary}
                  requiredInputsSummary={requiredInputKeys}
                  outputTargetSummary={outputTargetSummary}
                  outputTargetHint={t('task.workspaceSidebarOutputHint')}
                  saveResultsHint={t('task.workspaceSidebarSaveHint')}
                  sessionHint={t('task.workspaceSidebarSessionHint')}
                  draftHint={t('task.workspaceSidebarDraftHint')}
                  showRuntimeSections={hasStartedTask}
                  onOpenSession={() => sessionInfo?.id && navigate(`/sessions/${sessionInfo.id}`)}
                  onBackHome={() => navigate('/')}
                />
              </Sider>
            </Layout>
          </Space>
        </div>
      </Content>
    </Layout>
  );
}
