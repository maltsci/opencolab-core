export interface TaskDefinition {
  id: string;
  version: number;
  name: string;
  description: string;
  workflow_id: string;
  skill_pack_id: string | null;
  input_schema: Record<string, unknown>;
  starter_prompts: string[];
  project_context_policy: Record<string, unknown>;
  result_presentation: Record<string, unknown>;
  is_enabled: boolean;
  project_ids: string[];
  created_at: string | null;
  updated_at: string | null;
  is_builtin: boolean;
}

export function getTaskRuntimeKind(task: TaskDefinition): 'codex' | 'platform' {
  if (task.skill_pack_id) {
    return 'codex';
  }

  if (task.workflow_id.startsWith('installed-')) {
    return 'codex';
  }

  const runtime = task.result_presentation.runtime || task.project_context_policy.runtime;
  return runtime === 'codex' ? 'codex' : 'platform';
}
