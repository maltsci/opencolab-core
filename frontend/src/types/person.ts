export interface PersonDirectionSummary {
  id: string;
  name: string;
  role: 'lead' | 'contributor' | 'advisor' | string;
}

export interface PersonDirectoryEntry {
  id: string;
  username: string;
  display_name: string | null;
  role: 'admin' | 'pi' | 'researcher' | string;
  bio: string | null;
  consultation_topics: string[];
  current_directions: PersonDirectionSummary[];
  archived_at: string | null;
}

export interface PersonDirectionHistoryEntry extends PersonDirectionSummary {
  member_direction_id: string;
  valid_from: string;
  valid_until: string | null;
}

export interface PersonDetail extends PersonDirectoryEntry {
  show_recent_activity: boolean;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  is_stale: boolean;
  direction_history: PersonDirectionHistoryEntry[];
}

export interface PersonRecentWorkEntry {
  id: string;
  project_id: string;
  project_name: string;
  action: string;
  created_at: string;
}

export interface PersonRecentWorkResponse {
  visible: boolean;
  items: PersonRecentWorkEntry[];
}

export interface PersonResponsibility {
  asset_id: string;
  title: string;
  description: string | null;
  asset_type: string;
}

export interface MemberProfileUpdateInput {
  bio?: string | null;
  consultation_topics?: string[];
  show_recent_activity?: boolean;
  last_confirmed_at?: string | null;
  review_due_at?: string | null;
}

export interface MemberProfileMaintenanceItem {
  user_id: string;
  display_name: string | null;
  last_confirmed_at: string | null;
  review_due_at: string | null;
  issue: 'review_missing' | 'review_overdue';
}

export interface ResearchDirectionOption {
  id: string;
  name: string;
}
