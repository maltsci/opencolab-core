export type ResearchDirectionStatus = 'active' | 'archived' | 'merged';

export interface ResearchDirection {
  id: string;
  name: string;
  summary: string | null;
  background: string | null;
  scope: string | null;
  status: ResearchDirectionStatus;
  owner_id: string | null;
  merged_into_id: string | null;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ResearchDirectionPage {
  items: ResearchDirection[];
  next_cursor: string | null;
}

export interface ResearchDirectionCreateInput {
  name: string;
  summary?: string;
  background?: string;
  scope?: string;
  owner_id?: string;
}

export interface ResearchDirectionUpdateInput {
  name: string;
  summary: string | null;
  background: string | null;
  scope: string | null;
  owner_id?: string | null;
  last_confirmed_at: string | null;
  review_due_at: string | null;
}

export interface ResearchDirectionMergeInput {
  target_direction_id: string;
  reason: string;
}

export interface ResearchDirectionRelation {
  id: string;
  direction_a_id: string;
  direction_b_id: string;
  relation_type: 'related';
  reason: string;
  evidence_json: Record<string, unknown>;
  created_by: string;
  created_at: string;
}

export interface DirectionResource {
  asset_id: string;
  title: string;
  description: string | null;
  asset_type: string;
  steward_name: string | null;
  purpose: string | null;
}

export interface DirectionLearningResource extends DirectionResource {
  learning_order: number;
}

export interface DirectionResearchObject {
  asset_id: string;
  research_object_id: string;
  title: string | null;
  object_type: string;
  relation_type: string;
  reason: string | null;
}

export interface DirectionProject {
  project_id: string;
  name: string;
  description: string | null;
  reason: string | null;
  created_at: string;
}

export interface DirectionActivity {
  id: string;
  project_id: string;
  project_name: string;
  action: string;
  created_at: string;
  is_pinned: boolean;
}

export interface DirectionMember {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
  direction_role: 'lead' | 'contributor' | 'advisor' | string;
}

export interface DirectionSteward {
  id: string;
  direction_id: string;
  user_id: string;
  created_by: string;
  created_at: string;
  revoked_at: string | null;
}

export interface DirectionMaintenanceItem {
  direction_id: string;
  name: string;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  issue: 'review_missing' | 'review_overdue';
}
