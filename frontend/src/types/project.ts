export interface Project {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  task_ids: string[];
  archived: boolean;
  member_count: number;
  owner_name: string | null;
  is_owner: boolean;
  research_group_id?: string | null;
}

export interface ProjectMember {
  id: string;
  researcher_id: string;
  role: string;
  username: string | null;
  display_name: string | null;
}

export interface UserOption {
  id: string;
  username: string;
  display_name: string | null;
}

export interface ProjectSession {
  id: string;
  project_id: string | null;
  task_id?: string | null;
  title: string | null;
  created_at: string;
  message_count: number;
  owner_id: string | null;
  owner_name: string | null;
}

export type PlanPriority = 'low' | 'medium' | 'high';
export type PlanStatus = 'todo' | 'in_progress' | 'done';

export interface ProjectPlan {
  id: string;
  project_id: string;
  title: string;
  content: string | null;
  start_date: string | null;
  due_date: string | null;
  priority: PlanPriority;
  tags: string[];
  assignee_id: string | null;
  assignee_name: string | null;
  status: PlanStatus;
  created_by: string | null;
  creator_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectActivity {
  id: string;
  project_id: string;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  target_title: string | null;
  created_at: string;
}
