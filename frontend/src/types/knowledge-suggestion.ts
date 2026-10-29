export type KnowledgeSuggestionStatus = 'pending' | 'approved' | 'rejected';

export interface KnowledgeSuggestion {
  id: string;
  target_type: string;
  target_id: string | null;
  action: string;
  payload_json: Record<string, unknown>;
  evidence_json: Record<string, unknown>;
  status: KnowledgeSuggestionStatus;
  submitted_by: string | null;
  submitted_by_type: string;
  reviewer_id: string | null;
  decision_reason: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSuggestionAudit {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor_id: string | null;
  suggestion_id: string | null;
  before_json: Record<string, unknown>;
  after_json: Record<string, unknown>;
  created_at: string;
}

export interface KnowledgeInbox {
  review_items: KnowledgeSuggestion[];
  decision_items: KnowledgeSuggestion[];
  unread_decision_count: number;
}
