export type OrchestrationRunStatus =
  | 'planning'
  | 'running'
  | 'waiting_for_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface OrchestrationRun {
  id: string;
  session_id: string;
  task_id: string;
  turn_index: number;
  status: OrchestrationRunStatus;
  final_message_id?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}
