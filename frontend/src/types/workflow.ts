export type WorkflowRunStatus =
  | 'pending'
  | 'running'
  | 'waiting_for_checkpoint'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type StepRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'waiting_for_checkpoint';

export interface WorkflowStepDefinition {
  id: string;
  type: string;
  ref: string;
  depends_on: string[];
  retry_policy: Record<string, unknown>;
  validation_rule?: string | null;
  output_key: string;
}

export interface WorkflowDefinition {
  id: string;
  version: number;
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  steps: WorkflowStepDefinition[];
  checkpoint_policy: Record<string, unknown>;
  writeback_policy: Record<string, unknown>;
}

export interface WorkflowRunCreateRequest {
  session_id: string;
  input: Record<string, unknown>;
  replace_message_id?: string;
}

export interface WorkflowRunResponse {
  id: string;
  workflow_id: string;
  workflow_version: number;
  session_id: string;
  status: WorkflowRunStatus;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  created_by?: string | null;
  created_by_type: string;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface StepRunResponse {
  id: string;
  workflow_run_id: string;
  step_id: string;
  step_type: string;
  ref: string;
  status: StepRunStatus;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error_message?: string | null;
  attempt_count: number;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface WorkflowRunSaveMemoryRequest {
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

export interface WorkflowRunSaveMemoryResponse {
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
