export type StageCategory =
  | 'problem_framing'
  | 'baseline_reproduction'
  | 'innovation_feasibility'
  | 'experiment_iteration'
  | 'manuscript_writing';

export type AcceptMode = 'auto' | 'observe' | 'off';

export interface ProactiveRule {
  id: string;
  stage_category: StageCategory;
  name: string;
  description: string;
  trigger_events: string[];
  is_enabled: boolean;
}

export interface ProjectPolicy {
  project_id: string;
  accept_mode: AcceptMode;
  version: number;
  rules: ProactiveRule[];
  enabled_plugins: string[];
  updated_by?: string | null;
  updated_at?: string | null;
}

export interface TargetMetricItem {
  metric: string;
  target: string;
  unit?: string | null;
}

export interface TicketAttention {
  kind: 'decision' | 'wetlab_upload';
  question: string;
  options: string[];
  recommended?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  template_data?: {
    filename?: string;
    columns?: string[];
    rows?: Record<string, unknown>[];
    csv_text?: string;
    checkpoint?: string;
    planner_subtasks?: {
      id?: string;
      assigned_to?: string;
      title?: string;
      description?: string;
    }[];
  } | null;
}

export interface LiteratureMemoryCard {
  source_id: string;
  title: string;
  authors?: string[];
  year?: string;
  doi?: string | null;
  record_url?: string | null;
  venue?: string | null;
  citation_count?: number;
  origin?: string;
  core_claims?: string;
  experimental_setup?: {
    baseline?: string;
    dataset?: string;
    metrics?: string;
  };
  key_results?: string;
  card_summary_500w?: string;
  word_count?: number;
}

export interface DataCrossValidation {
  has_internal_data?: boolean;
  data_source_summary?: string;
  python_script?: string;
  chart_svg?: string;
  alignment_table?: Record<string, unknown>[];
  sota_analysis?: string;
}

export interface WriterOutput {
  manuscript_draft?: string;
  citation_style?: string;
  bibtex?: string;
  references?: {
    source_id?: string;
    title?: string;
    authors?: string[];
    year?: string;
    venue?: string;
    doi?: string;
    record_url?: string;
  }[];
  provenance_audit?: {
    strict_binding_enforced?: boolean;
    total_assertions_checked?: number;
    verified_assertions_count?: number;
    dropped_ungrounded_assertions_count?: number;
    dropped_examples?: string[];
    valid_source_ids?: string[];
  };
}

export interface NoveltyCheckResult {
  novel?: boolean;
  decision_made?: boolean;
  rounds_used?: number;
  queries?: string[];
  outbound_used?: boolean;
}

export interface IdeaEvaluation {
  status: 'scored' | 'unavailable';
  reason?: string;
  scores?: {
    interestingness?: number | null;
    feasibility?: number | null;
    novelty?: number | null;
  };
  composite_score?: number | null;
  thought?: string;
  archive_size?: number;
  novelty_check?: NoveltyCheckResult | null;
}

export interface PeerReviewScorecard {
  Summary?: string;
  Strengths?: string[];
  Weaknesses?: string[];
  Questions?: string[];
  Soundness?: number;
  Presentation?: number;
  Contribution?: number;
  Overall?: number;
  Confidence?: number;
  Decision?: 'Accept' | 'Reject';
}

export interface PeerReview extends PeerReviewScorecard {
  status: 'reviewed' | 'unavailable';
  reason?: string;
  ensemble_size?: number;
  individual_reviews?: PeerReviewScorecard[];
}

export interface TicketDeliverable {
  title: string;
  kind: string;
  markdown_report: string;
  metrics_table: Record<string, unknown>[];
  diff_summary?: {
    round?: number;
    best_sample_id?: string;
    best_measured_value?: number | string;
    prior_round_best?: number | string;
    delta_vs_prior_round?: number | string;
    baseline_value?: number | string;
    key_insight?: string;
    recommended_next_direction?: string;
  } | null;
  proposed_objects: Record<string, unknown>[];
  artifact_asset_ids: string[];
  merged_at?: string | null;
  planner_plan?: {
    agent_role?: string;
    intent_summary?: string;
    environment_perception?: Record<string, unknown>;
    search_queries?: string[];
    subtasks?: {
      id: string;
      assigned_to: string;
      title: string;
      description: string;
    }[];
  } | null;
  literature_memory_cards?: LiteratureMemoryCard[];
  data_cross_validation?: DataCrossValidation | null;
  writer_output?: WriterOutput | null;
  idea_evaluation?: IdeaEvaluation | null;
  peer_review?: PeerReview | null;
  agent_trace?: {
    agent?: string;
    node?: string;
    iteration?: number;
    status?: string;
    at?: string;
    summary?: string;
  }[];
  checkpoint_stage?: string | null;
}

export interface TicketThreadMessage {
  id: string;
  author_id?: string | null;
  author_name: string;
  role: 'human' | 'agent' | 'system';
  content: string;
  trigger_kind?: string | null;
  created_at: string;
}

export interface ResearchTicket {
  id: string;
  project_id: string;
  short_key: string;
  title: string;
  stage_category: StageCategory;
  iteration_round?: number | null;
  parent_ticket_id?: string | null;
  status: string;
  report_state: string;
  stage: string;
  needs_person: boolean;
  ended_outcome?: string | null;
  mandate: Record<string, unknown>;
  summary?: string | null;
  attention?: TicketAttention | null;
  deliverable?: TicketDeliverable | null;
  thread_messages: TicketThreadMessage[];
  execution_log: Record<string, unknown>[];
  plugin_id?: string | null;
  created_by?: string | null;
  creator_name?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectTriggerItem {
  id: string;
  project_id: string;
  source_kind: string;
  event_type: string;
  actor_id?: string | null;
  actor_name?: string | null;
  title: string;
  payload: Record<string, unknown>;
  disposition: string;
  decision_reason?: string | null;
  matched_rule_id?: string | null;
  ticket_id?: string | null;
  created_at: string;
}

export interface PipelineStageSummary {
  stage_category: StageCategory;
  object_type: string;
  accepted_count: number;
  open_ticket_count: number;
  person_ticket_count: number;
  latest_round?: number | null;
  status: 'empty' | 'active' | 'needs_person' | 'completed';
  items: {
    id: string;
    type: string;
    title?: string | null;
    content?: string | null;
    content_json?: Record<string, unknown> | null;
    created_at?: string | null;
  }[];
}

export interface SuperagentOverview {
  project_id: string;
  needs_person: ResearchTicket[];
  pipeline_stages: PipelineStageSummary[];
  executor: {
    running: number;
    queued: number;
    idle: number;
    ended: number;
    max_workers: number;
  };
  flow_24h: {
    received: number;
    accepted: number;
    observed: number;
    completed: number;
  };
  policy: ProjectPolicy;
  recent_triggers: ProjectTriggerItem[];
}
