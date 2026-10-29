export type BuiltInAgentName = 'literature_synthesizer' | 'reviewer_assistant';

export interface AgentDefinition {
  name: BuiltInAgentName;
  labelKey: string;
  inputKey: 'query' | 'review_comments';
  inputLabelKey: string;
  inputPlaceholderKey: string;
  minimumSourceCount: number;
}

export interface AgentRunRequest {
  session_id: string;
  agent: BuiltInAgentName;
  source_ids: string[];
  input: Record<string, unknown>;
}

export interface AgentRunStepResponse {
  name: string;
  status: string;
  summary: string;
}

export interface AgentRunTracePayload {
  id?: string | null;
  trace_id?: string | null;
  traceId?: string | null;
  inputs: Record<string, unknown>;
  retrieval: Array<Record<string, unknown>>;
  citations: Array<Record<string, unknown>>;
  summary_steps?: string[];
  summarySteps?: string[];
}

export interface AgentRunResponse {
  id: string;
  session_id: string;
  workflow_run_id?: string | null;
  agent_name: BuiltInAgentName;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  steps: AgentRunStepResponse[];
  trace: AgentRunTracePayload | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AgentRunSaveMemoryRequest {
  type: 'hypothesis' | 'discussion';
  title: string;
  content: string;
  relation: {
    enabled: boolean;
    relation_type?: 'supports' | 'contradicts';
    target_object_id?: string;
    note?: string;
  };
}

export interface AgentRunSaveMemoryResponse {
  research_object: {
    id: string;
    session_id?: string | null;
    message_id?: string | null;
    type: string;
    title: string | null;
    content: string | null;
    content_json: Record<string, unknown>;
    created_at: string;
    updated_at?: string | null;
  };
  relation: {
    id: string;
    relation_type: 'supports' | 'contradicts';
    source_object_id: string;
    target_object_id: string;
    metadata_json: Record<string, unknown>;
    created_by: string | null;
    created_by_type: string;
    target_object: {
      id: string;
      type: string;
      title: string | null;
    };
    created_at: string;
  } | null;
}

export const BUILT_IN_AGENTS: AgentDefinition[] = [
  {
    name: 'literature_synthesizer',
    labelKey: 'agent.literatureSynthesizer',
    inputKey: 'query',
    inputLabelKey: 'agent.query',
    inputPlaceholderKey: 'agent.queryPlaceholder',
    minimumSourceCount: 2,
  },
  {
    name: 'reviewer_assistant',
    labelKey: 'agent.reviewerAssistant',
    inputKey: 'review_comments',
    inputLabelKey: 'agent.reviewComments',
    inputPlaceholderKey: 'agent.reviewCommentsPlaceholder',
    minimumSourceCount: 0,
  },
];
