from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


StageCategoryLiteral = Literal[
    "problem_framing",
    "baseline_reproduction",
    "innovation_feasibility",
    "experiment_iteration",
    "manuscript_writing",
]

AcceptModeLiteral = Literal["auto", "observe", "off"]


class ProactiveRuleSchema(BaseModel):
    id: str
    stage_category: StageCategoryLiteral
    name: str
    description: str
    trigger_events: list[str]
    is_enabled: bool = True


class ProjectPolicyResponse(BaseModel):
    project_id: str
    accept_mode: AcceptModeLiteral
    version: int
    rules: list[ProactiveRuleSchema]
    enabled_plugins: list[str]
    updated_by: str | None = None
    updated_at: datetime | None = None


class ProjectPolicyUpdateRequest(BaseModel):
    accept_mode: AcceptModeLiteral | None = None
    rules: list[ProactiveRuleSchema] | None = None
    enabled_plugins: list[str] | None = None


class TargetMetricItem(BaseModel):
    metric: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=100)


class ResearchQuestionCreateRequest(BaseModel):
    question_object_id: str | None = None
    theme: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=2000)
    sub_questions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    target_metrics: list[TargetMetricItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    plugin_id: str | None = Field(default=None, max_length=100)
    trigger_baseline: bool = True


class ResearchCharterSuggestResponse(BaseModel):
    theme: str
    question: str
    sub_questions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class TicketAttentionSchema(BaseModel):
    kind: Literal["decision", "wetlab_upload"] = "decision"
    question: str
    options: list[str] = Field(default_factory=list)
    recommended: str | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    template_data: dict[str, Any] | None = None


class TicketDeliverableSchema(BaseModel):
    title: str
    kind: str
    markdown_report: str
    metrics_table: list[dict[str, Any]] = Field(default_factory=list)
    diff_summary: dict[str, Any] | None = None
    proposed_objects: list[dict[str, Any]] = Field(default_factory=list)
    artifact_asset_ids: list[str] = Field(default_factory=list)
    merged_at: str | None = None
    planner_plan: dict[str, Any] | None = None
    literature_memory_cards: list[dict[str, Any]] = Field(default_factory=list)
    data_cross_validation: dict[str, Any] | None = None
    writer_output: dict[str, Any] | None = None
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_stage: str | None = None
    idea_evaluation: dict[str, Any] | None = None
    peer_review: dict[str, Any] | None = None
    critic_check: dict[str, Any] | None = None


class DeepResearchLaunchRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)
    citation_style: Literal["IEEE", "APA"] = "IEEE"
    allow_external_search: bool = True
    enable_hitl_checkpoints: bool = True
    assignee_id: str | None = None


class TicketThreadMessageSchema(BaseModel):
    id: str
    author_id: str | None = None
    author_name: str
    role: Literal["human", "agent", "system"]
    content: str
    trigger_kind: str | None = None
    created_at: str


class ResearchTicketResponse(BaseModel):
    id: str
    project_id: str
    short_key: str
    title: str
    stage_category: str
    iteration_round: int | None = None
    parent_ticket_id: str | None = None
    status: str
    report_state: str
    stage: str
    needs_person: bool
    ended_outcome: str | None = None
    mandate: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    attention: TicketAttentionSchema | None = None
    deliverable: TicketDeliverableSchema | None = None
    thread_messages: list[TicketThreadMessageSchema] = Field(default_factory=list)
    execution_log: list[dict[str, Any]] = Field(default_factory=list)
    plugin_id: str | None = None
    created_by: str | None = None
    creator_name: str | None = None
    assignee_id: str | None = None
    assignee_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ResearchTicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    stage_category: StageCategoryLiteral = "baseline_reproduction"
    goal: str | None = Field(default=None, max_length=4000)
    assignee_id: str | None = None
    plugin_id: str | None = None
    iteration_round: int | None = None
    parent_ticket_id: str | None = None


class TicketAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    selected_option: str | None = None


class WetlabMeasurementRow(BaseModel):
    sample_id: str = Field(min_length=1, max_length=200)
    condition: str | None = None
    predicted_value: float | str | None = None
    measured_value: float | str
    secondary_metric: float | str | None = None
    notes: str | None = None


class TicketWetlabUploadRequest(BaseModel):
    experiment_note: str | None = Field(default=None, max_length=2000)
    measurements: list[WetlabMeasurementRow] = Field(default_factory=list)
    csv_content: str | None = None
    asset_id: str | None = None


class TicketApproveRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)
    mark_milestone_verified: bool = False


class TicketNextRoundRequest(BaseModel):
    direction_note: str = Field(min_length=1, max_length=2000)
    assignee_id: str | None = None


class TicketThreadMessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    invoke_agent: bool = True


class ProjectTriggerResponse(BaseModel):
    id: str
    project_id: str
    source_kind: str
    event_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    disposition: str
    decision_reason: str | None = None
    matched_rule_id: str | None = None
    ticket_id: str | None = None
    created_at: datetime


class PipelineStageSummary(BaseModel):
    stage_category: StageCategoryLiteral
    object_type: str
    accepted_count: int
    open_ticket_count: int
    person_ticket_count: int
    latest_round: int | None = None
    status: Literal["empty", "active", "needs_person", "completed"]
    items: list[dict[str, Any]] = Field(default_factory=list)


class SuperagentOverviewResponse(BaseModel):
    project_id: str
    needs_person: list[ResearchTicketResponse]
    pipeline_stages: list[PipelineStageSummary]
    executor: dict[str, int]
    flow_24h: dict[str, int]
    policy: ProjectPolicyResponse
    recent_triggers: list[ProjectTriggerResponse] = Field(default_factory=list)


class TriggerEmitRequest(BaseModel):
    source_kind: str = Field(default="manual", min_length=1, max_length=64)
    event_type: str = Field(default="sources_ready", min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class TriggerEmitResponse(BaseModel):
    trigger: ProjectTriggerResponse
    ticket: ResearchTicketResponse | None = None


class ResearchQuestionCreateResponse(BaseModel):
    research_object: dict[str, Any]
    ticket: ResearchTicketResponse | None = None


class TicketApproveResponse(BaseModel):
    ticket: ResearchTicketResponse
    created_objects: list[dict[str, Any]] = Field(default_factory=list)
    next_ticket: ResearchTicketResponse | None = None

